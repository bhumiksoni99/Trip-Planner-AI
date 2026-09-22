"""Checks the graph's wiring with every external call faked: no API calls, nothing written to Postgres.

Each faked I/O call sleeps 1s, so the timings show what really ran in parallel. Run from backend/:

    python -m evals.wiring
"""
import os

# Before agent is imported, so these fake runs never reach the LangSmith project
os.environ["LANGSMITH_TRACING"] = "false"

import sys
import threading
import time
from collections import Counter

from langgraph.checkpoint.memory import MemorySaver

import agent

calls = Counter()
lock = threading.Lock()
failures = []

# What the faked supervisor picks and the faked intake extracts; each scenario sets these
SELECTED: list = []
CONSTRAINTS = None


def count(name):
    with lock:
        calls[name] += 1


class Fake:
    """Stands in for a structured-output model; returns a fixed value, or builds one"""

    def __init__(self, name, value):
        self.name, self.value = name, value

    def invoke(self, *_args, **_kwargs):
        count(self.name)
        return self.value() if callable(self.value) else self.value


def slow(name, value):
    """Stands in for an API call that takes 1s"""
    def fn(*args, **_kwargs):
        count(name)
        time.sleep(1)
        return value(*args) if callable(value) else value
    return fn


def full_constraints():
    return agent.TripConstraints(
        destination="Tokyo", departure_city="Delhi", travel_dates="May", duration="5 days",
        budget="2 lakhs", vibe="relaxed", interests="food",
    )


def fake_search(query, *_args):
    stem = query.replace(" ", "-")[:40]
    return {"images": [], "results": [
        {"title": f"Hotel {i} {query.split()[-1]}", "url": f"https://example.com/{stem}/{i}", "content": "nice"}
        for i in range(2)
    ]}


# Model calls are instant, so the timings reflect only the I/O
agent.guardrail_checker = Fake("guardrail", agent.Guardrail(allowed=True, travel_request="5 days in Japan", off_topic=None, reason="travel"))
agent.agent_selector = Fake("selector", lambda: agent.AgentPlan(agents=SELECTED, reasoning="test"))
agent.constraints_extractor = Fake("constraints", lambda: CONSTRAINTS())
agent.destination_extractor = Fake("destination", agent.Destination(city="Tokyo"))
agent.itinerary_writer = Fake("itinerary", agent.Itinerary(
    overview="Tokyo then Kyoto then Osaka",
    days=[agent.ItineraryDay(label="Day 1", heading="Arrive", items=[agent.DayItem(time="Morning", text="Land")])],
))
agent.stay_extractor = Fake("stays", agent.Stays(stays=[agent.Stay(city=c, area=None, nights=2) for c in ("Tokyo", "Kyoto", "Osaka")]))
agent.hotel_picker = Fake("picker", agent.HotelShortlist(stays=[]))  # empty, so the top-up from search results runs
agent.budget_writer = Fake("budget", agent.BudgetEstimate(lines=[], total=None, total_value=None, ceiling_value=None, ceiling_label=None, analysis="fits"))
agent.final_plan_writer = Fake("final", agent.FinalPlan(summary="Five days.", plan="## Trip Overview\nplan"))
agent.intent_classifier = Fake("intent", agent.MessageIntent(is_travel=True, is_refinement=True, trip_request=None, travel_change="cheaper hotels", off_topic=None, reason="change"))
agent.replan_selector = Fake("replan", agent.ReplanPlan(agents=["hotel_agent"], reasoning="hotels change"))

# API calls take 1s each
agent.search_flights = slow("flights_api", "flights")
agent.weather_report = slow("weather_api", "weather")
agent.destination_photo = slow("photo_api", lambda destination: f"https://example.com/{destination.lower()}.jpg")
agent.search_place = slow("tavily", fake_search)

graph = agent.graph.compile(checkpointer=MemorySaver())
agent.travel_graph = graph  # _progress_events reads the final state through this


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{f'  ({detail})' if detail else ''}")
    if not ok:
        failures.append(label)


def run(thread, query, selected, constraints=full_constraints):
    global SELECTED, CONSTRAINTS
    SELECTED, CONSTRAINTS = selected, constraints
    calls.clear()
    start = time.time()
    events = list(agent.stream_travel_agent(query, thread))
    return events, time.time() - start


def started(events):
    return [e["data"]["agent"] for e in events if e["event"] == "agent_started"]


FIRST_STAGE = ("flight_agent", "weather_agent", "photo_agent")

print("\n1. New trip, every agent selected")
events, took = run("t1", "5 days in Japan", list(agent.AGENT_ORDER))
done = events[-1]["data"]
names = started(events)
first_finish = next(i for i, e in enumerate(events) if e["event"] == "agent_finished" and e["data"]["agent"] in FIRST_STAGE)
first_starts = [i for i, e in enumerate(events) if e["event"] == "agent_started" and e["data"]["agent"] in FIRST_STAGE]
check("flights, weather and photo all start before any of them finishes", len(first_starts) == 3 and max(first_starts) < first_finish)
check("itinerary runs exactly once", names.count("itinerary_agent") == 1)
check("then itinerary, hotels, budget, write-up in order",
      [n for n in names if n in ("itinerary_agent", "hotel_agent", "budget_agent", "final_response_agent")]
      == ["itinerary_agent", "hotel_agent", "budget_agent", "final_response_agent"])
check("3 stay searches + 6 link lookups", calls["tavily"] == 9, f"{calls['tavily']} searches")
check("well under the 12s it takes one call at a time", took < 5.5, f"{took:.1f}s")
check("llm_calls sums to 10", done["llm_calls"] == 10, f"got {done['llm_calls']}")
check("header card has the photo", (done.get("header") or {}).get("image") == "https://example.com/tokyo.jpg")
check("six hotels, in trip order", [h["city"] for h in done.get("hotels", [])] == ["Tokyo", "Tokyo", "Kyoto", "Kyoto", "Osaka", "Osaka"])

print("\n2. Supervisor picks only weather and the itinerary")
events, took = run("t2", "weather-led day trip", ["weather_agent", "itinerary_agent"])
names = started(events)
check("finishes instead of hanging", events[-1]["event"] == "done", f"{took:.1f}s")
check("flights, hotels and budget skipped", not {"flight_agent", "hotel_agent", "budget_agent"} & set(names), str(names))
check("weather and photo still run side by side", {"weather_agent", "photo_agent"} <= set(names))

print("\n3. Missing trip details: intake pauses, then resumes")
def partial_constraints():
    return agent.TripConstraints(destination="Tokyo", departure_city=None, travel_dates=None, duration="5 days", budget=None, vibe=None, interests=None)
events, _ = run("t3", "Japan trip", list(agent.AGENT_ORDER), partial_constraints)
check("pauses for intake", events[-1]["data"]["pause_type"] == "intake")
check("no specialist ran before the answers", not set(FIRST_STAGE) & set(started(events)))
resumed = list(agent.stream_resume_travel_agent("t3", {"departure_city": "Mumbai", "travel_dates": "June"}))
check("resume runs the plan to the end", resumed[-1]["data"].get("final_response", "").startswith("## Trip Overview"))
check("resume fans out too", set(FIRST_STAGE) <= set(started(resumed)))

print("\n4. Follow-up that refines the plan")
events, _ = run("t1", "make the hotels cheaper", list(agent.AGENT_ORDER))
names = started(events)
done = events[-1]["data"]
header = done.get("header") or {}
check("reworks itinerary and hotels only", {"itinerary_agent", "hotel_agent"} <= set(names) and not {"flight_agent", "weather_agent"} & set(names), str(names))
check("doesn't fetch the photo again", "photo_agent" not in names and calls["photo_api"] == 0)
check("keeps its header card and photo", header.get("destination") == "Tokyo" and header.get("image") == "https://example.com/tokyo.jpg")
check("keeps its brief", any(t["label"] == "Budget" for t in done.get("brief", [])))
check("llm_calls counts this run only", done["llm_calls"] == 6, f"got {done['llm_calls']}")

print("\n5. Follow-up that asks for a different trip in the same thread")
agent.intent_classifier = Fake("intent", agent.MessageIntent(is_travel=True, is_refinement=False, trip_request="3 days in Paris", travel_change=None, off_topic=None, reason="new trip"))
def paris():
    return agent.TripConstraints(destination="Paris", departure_city="Mumbai", travel_dates="June", duration="3 days", budget="1 lakh", vibe="culture", interests="museums")
events, _ = run("t1", "actually, 3 days in Paris instead", list(agent.AGENT_ORDER), paris)
header = events[-1]["data"].get("header") or {}
check("gets its own terms, not the previous trip's", header.get("destination") == "Paris" and header.get("origin") == "Mumbai")
check("fetches its own photo", header.get("image") == "https://example.com/paris.jpg")

print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILED: {failures}'}")
sys.exit(1 if failures else 0)
