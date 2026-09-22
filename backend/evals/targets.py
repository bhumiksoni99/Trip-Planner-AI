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
    """Everything the graph pulls out of a request: intake's trip details, the weather agent's city,
    and the flight agent's airports. Three model calls today, which optimisations 1 and 2 cut to one."""
    request = inputs["request"]

    found = agent.extract_constraints(request)
    details = {key: getattr(found, key, None) for key in agent.TripConstraints.model_fields} if found else {}

    # Built the way flight_agent builds it, from the request and the departure city intake found
    departure = details.get("departure_city")
    route = get_route(f"{request} departing from {departure}" if departure else request)

    return {
        **details,
        "destination_city": agent.extract_destination_city(request),
        "origin_iata": (route.origin_iata or "").upper() if route else "",
        "destination_iata": (route.destination_iata or "").upper() if route else "",
        "llm_calls": 3,
    }


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

    # Only a change to this plan goes on to feedback_agent, exactly as the graph routes it
    if result["is_travel"] and result["is_refinement"]:
        replanned = agent.feedback_agent({**state, **decided})
        result["rerun"] = replanned["selected_agents"]
        result["llm_calls"] += replanned.get("llm_calls", 0)

    return result


TARGETS = {"guardrail": guardrail, "extraction": extraction, "stays": stays, "replan": replan}
