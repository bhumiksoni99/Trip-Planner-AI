"""What each eval runs: the production code for one step of the graph, returning what it decided.

These call the real agents and prompts, so an eval measures exactly what the app does. When an
optimisation merges or removes a model call, the target keeps returning the same fields, and the
same dataset scores the old and new versions side by side.
"""
import json
from pathlib import Path

import agent
from tools.flight_tool import get_route

BASES = json.loads((Path(__file__).parent / "datasets" / "replan_bases.json").read_text())


def guardrail(inputs: dict) -> dict:
    """The supervisor on a new trip: is it travel, what else did it ask for, which agents run"""
    out = agent.supervisor_agent({"user_query": inputs["request"]})
    return {
        "allowed": out["guardrail_allowed"],
        "off_topic": out.get("off_topic_request", ""),
        "trip_request": out.get("trip_request", ""),
        "agents": out.get("selected_agents", []),
        "llm_calls": out.get("llm_calls", 0),
    }


def extraction(inputs: dict) -> dict:
    """Everything the graph pulls out of a request: intake's trip details, and the city and airports the
    weather and flight agents end up using. Normally one model call, with the agents' fallbacks counted
    when intake leaves a gap they have to fill."""
    request = inputs["request"]

    found = agent.extract_constraints(request)
    # The trip details as stated, so the "never guess" checks see what the model actually returned
    details = {key: getattr(found, key, None) for key in agent.TripConstraints.model_fields} if found else {}
    calls = 1

    # What the agents work from: intake's details with its defaults filled in, like the departure city
    stated = {key: (value or "").strip() if isinstance(value, str) else value for key, value in details.items()}
    resolved = agent.resolve_constraints(stated)["trip_constraints"]

    # flight_agent's route, and its fallback when intake couldn't place an airport
    origin, destination = agent.flight_route(resolved)
    if not (origin and destination):
        departure = resolved.get("departure_city")
        route = get_route(f"{request} departing from {departure}" if departure else request)
        origin = (route.origin_iata or "").upper() if route else ""
        destination = (route.destination_iata or "").upper() if route else ""
        calls += 1

    # weather_agent's city, and its fallback
    city = resolved.get("destination_city")
    if not city:
        city = agent.extract_destination_city(request) or resolved.get("destination")
        calls += 1

    return {**details, "destination_city": city, "origin_iata": origin or "", "destination_iata": destination or "", "llm_calls": calls}


def stays(inputs: dict) -> dict:
    """Where hotel_agent thinks the itinerary stays overnight"""
    found = agent.extract_stays(inputs["itinerary"])
    return {"stays": [stay.model_dump() for stay in found], "llm_calls": 1}


def replan(inputs: dict) -> dict:
    """A follow-up message on an existing plan: is it a change or a new trip, and what re-runs"""
    base = BASES[inputs["base"]]
    state = {
        "user_query": inputs["message"],
        "trip_request": base["trip_request"],
        "itinerary": base["itinerary"],
        "feedback_history": [],
    }

    decided = agent.supervisor_agent(state)
    result = {
        "message": inputs["message"],
        "is_travel": decided["guardrail_allowed"],
        "is_refinement": bool(decided.get("is_refinement")),
        "off_topic": decided.get("off_topic_request", ""),
        "trip_request": decided.get("trip_request", ""),
        "rerun": None,
        "llm_calls": decided.get("llm_calls", 0),
    }

    # A change to this plan is decided in the same call, which also picks what re-runs;
    # the graph routes straight to those agents
    if result["is_travel"] and result["is_refinement"]:
        result["rerun"] = decided.get("selected_agents", [])

    return result


def itinerary(inputs: dict) -> dict:
    """The itinerary writer on a trip request, with the stays it lists for hotel_agent. Run without flight
    or weather data, which only shape the days, not where the traveller sleeps."""
    written = agent.itinerary_agent({"user_query": inputs["request"], "trip_request": inputs["request"]})
    return {
        "stays": written.get("itinerary_stays", []),
        "days": len(written.get("itinerary_days", [])),
        "text": written.get("itinerary", ""),
        "llm_calls": written.get("llm_calls", 0),
    }


TARGETS = {"guardrail": guardrail, "extraction": extraction, "stays": stays, "replan": replan, "itinerary": itinerary}
