import os
import logging
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import TypedDict, Annotated, Any
import uuid
import requests
import operator
from functools import partial
import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, AnyMessage
from mcp_client import tavily_search, run_sync, get_weather
from place_preview import search_place
from tools.flight_tool import search_flights

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Set LOG_LEVEL=DEBUG in .env for more detail
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("travel")

# httpx logs full request URLs, and the Tavily MCP URL carries the API key
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp.client.streamable_http").setLevel(logging.WARNING)
logging.getLogger("google_genai.models").setLevel(logging.ERROR)  # repeats an AFC notice on every call


def preview(text, length: int = 120):
    """One-line snippet of a value, for log lines."""
    text = str(text).replace("\n", " ")
    return text[:length] + "…" if len(text) > length else text

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", api_key=GEMINI_API_KEY)

class TravelState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str          # the latest message, which may be a follow-up like "day 2 doesn't sound good"
    trip_request: str        # the last full trip description, kept across follow-ups
    plan_history: list[str]  # the plans finished so far in this thread, newest last
    is_refinement: bool      # this message changes the existing plan instead of starting a new trip
    intake_done: bool        # the trip details have been collected for this trip

    # Supervisor + guardrail state
    guardrail_allowed: bool
    guardrail_reason: str
    selected_agents: list[str]
    trip_constraints: dict[str, Any]
    # Which of the trip's details the planner filled in because the traveller never said
    assumed_constraints: list[str]
    supervisor_reasoning: str

    # Original specialist results
    flight_results: str
    hotel_results: str
    weather_results: str
    itinerary: str
    # The same day-by-day plan the itinerary Markdown was built from, for the UI to render as cards
    itinerary_days: list[dict]
    # The shortlisted hotels, with their links, for the UI to render as cards
    hotel_picks: list[dict]

    # New budget + HITL state
    budget_results: str
    budget_total: str         # the estimated total per person, for the plan's header card
    budget_costs: dict[str, Any]  # the cost table: its lines, total and share of a stated budget
    approval_request: str
    approved: bool
    human_feedback: str
    feedback_history: list[str]
    revision_count: int
    replan_reasoning: str
    final_response: str
    plan_summary: str        # one-line synopsis for the header card
    destination_image: str   # a photo of the destination for the header card

    llm_calls: int

class Guardrail(BaseModel):
    allowed: bool = Field(description="True if the request is about travel")
    reason: str = Field(description="One short sentence explaining the decision")

class MessageIntent(BaseModel):
    is_travel: bool = Field(description="True if the message is about travel, including a change to the plan already made")
    is_refinement: bool = Field(description="True if it asks to change the existing plan rather than start a different trip")
    trip_request: str | None = Field(description="The full trip description when this is a new trip, otherwise null")
    reason: str = Field(description="One short sentence explaining the decision")

class AgentPlan(BaseModel):
    agents: list[str] = Field(description="Names of the specialist agents to run, from the available list")
    reasoning: str = Field(description="One short sentence explaining the choice")

class ReplanPlan(BaseModel):
    agents: list[str] = Field(description="Agents whose data must change to address the feedback; empty when the write-up alone can handle it")
    reasoning: str = Field(description="One short sentence explaining the choice")

class TripConstraints(BaseModel):
    # Not one of the intake questions: it comes from the request itself, and titles the plan
    destination: str | None = Field(description="Where the trip goes: the city, or the country if no city is named")
    departure_city: str | None = Field(description="City or airport the traveller leaves from, null if not stated")
    travel_dates: str | None = Field(description="When the trip happens, e.g. 'mid-May' or '3-9 March', null if not stated")
    duration: str | None = Field(description="How long the trip is, e.g. '5 days', null if not stated")
    budget: str | None = Field(description="Budget for the trip, with its currency, null if not stated")
    vibe: str | None = Field(description="Style of trip, e.g. relaxed, adventurous, luxury, null if not stated")
    interests: str | None = Field(description="Must-do interests or things to avoid, null if not stated")

class Destination(BaseModel):
    city: str | None = Field(description="Main destination city of the trip")

class Stay(BaseModel):
    city: str = Field(description="City the traveller stays overnight in")
    area: str | None = Field(description="Neighbourhood or area to stay in, if the itinerary names one")
    nights: int | None = Field(description="Number of nights spent in this city")

class Stays(BaseModel):
    stays: list[Stay] = Field(description="Every place the traveller stays overnight, in trip order")

class HotelPick(BaseModel):
    name: str = Field(description="The hotel's name, as its search result gives it")
    url: str = Field(description="The hotel's link, copied exactly from its search result. Never write one yourself")
    why: str = Field(
        description="One or two complete sentences, in your own words, on why this hotel suits this stay: where it "
                    "is and what it is good for. Never copy a cut-off fragment from the search result"
    )

class StayHotels(BaseModel):
    stay_index: int = Field(description="Which numbered stay these hotels are for")
    hotels: list[HotelPick] = Field(description="The best hotels for that stay")

class HotelShortlist(BaseModel):
    stays: list[StayHotels] = Field(description="Hotels for every stay, in the order the stays were given")

class FinalPlan(BaseModel):
    summary: str = Field(
        description="One or two sentences on what makes this plan work: its length, whether it fits the budget, "
                    "and the one or two choices that shaped it. Like 'Five days, comfortably under budget. A "
                    "Downtown base within walking distance of your evenings, and one day kept deliberately light.'"
    )
    plan: str = Field(description="The full travel plan in Markdown, with all of its sections")

class CostLine(BaseModel):
    label: str = Field(description='What the cost covers, like "Flights" or "Stay · Downtown · 13 nights"')
    amount: str = Field(description="What that line costs, with its currency, like 'Rs 50,000 - 80,000'")
    note: str | None = Field(description="A few words on how the figure was reached, or null")

class BudgetEstimate(BaseModel):
    lines: list[CostLine] = Field(
        description="The cost broken down, one line each for flights, accommodation, food, local transport "
                    "and activities"
    )
    total: str | None = Field(
        description="The estimated total per person, as a short range with its currency, like "
                    "'Rs 1,20,000 - 1,45,000'. Null when no figure could be estimated"
    )
    total_value: int | None = Field(
        description="The middle of that total estimate as a plain number, with no currency or separators, "
                    "like 132500. Null when there is no total"
    )
    ceiling_value: int | None = Field(
        description="The budget the traveller actually stated, as a plain number with no currency or "
                    "separators. Null when they gave no budget, and never a figure you worked out yourself"
    )
    ceiling_label: str | None = Field(description="The traveller's stated budget with its currency, or null")
    analysis: str = Field(
        description="The verdict in Markdown: whether the trip fits the budget and what to cut if it doesn't. "
                    "A short paragraph, not the breakdown, which is listed separately"
    )

class DayItem(BaseModel):
    time: str = Field(description='When it happens: a clock time like "09:00", or "Morning", "Afternoon" or "Evening"')
    text: str = Field(
        description="What the traveller does, in one sentence. Every place worth visiting in it is written as a "
                    "Markdown link to a Google search, like "
                    "[Pena Palace](https://www.google.com/search?q=Pena+Palace,+Sintra)"
    )

class ItineraryDay(BaseModel):
    label: str = Field(description='Which day of the trip, like "Day 1"')
    heading: str = Field(description='At most three words naming the day, like "Alfama" or "Arrival in Tokyo"')
    items: list[DayItem] = Field(description="What happens that day, in order")

class Itinerary(BaseModel):
    overview: str = Field(
        description="A short paragraph on the shape of the trip: which area to stay in and for how many nights in "
                    "each city, and any defaults chosen because the traveller didn't say"
    )
    days: list[ItineraryDay] = Field(description="The day-by-day plan, in order")

stay_extractor = llm.with_structured_output(Stays)
itinerary_writer = llm.with_structured_output(Itinerary)
hotel_picker = llm.with_structured_output(HotelShortlist)
budget_writer = llm.with_structured_output(BudgetEstimate)
final_plan_writer = llm.with_structured_output(FinalPlan)
destination_extractor = llm.with_structured_output(Destination)
guardrail_checker = llm.with_structured_output(Guardrail)
agent_selector = llm.with_structured_output(AgentPlan)
replan_selector = llm.with_structured_output(ReplanPlan)
intent_classifier = llm.with_structured_output(MessageIntent)
constraints_extractor = llm.with_structured_output(TripConstraints)


# The specialists in the order they run; the supervisor picks a subset of these
AGENT_ORDER = ["flight_agent", "weather_agent", "itinerary_agent", "hotel_agent", "budget_agent"]

# Caps the hotel searches per trip, one search per stay
MAX_STAYS = 5

# How many hotels are shortlisted for each city the itinerary stays in
HOTELS_PER_CITY = 2

# Their previews are watermarked, so a header photo from one of these looks broken
STOCK_PHOTO_HOSTS = ("istockphoto", "gettyimages", "shutterstock", "alamy", "dreamstime", "depositphotos", "123rf")

# Used when the request names only a destination, e.g. "Plan a Japan trip"
DEFAULT_ORIGIN = os.getenv("DEFAULT_ORIGIN", "DEL")
DEFAULT_ORIGIN_CITY = os.getenv("DEFAULT_ORIGIN_CITY", "Delhi")

# Asked one at a time before planning starts, but only the ones the request didn't already answer
INTAKE_FIELDS = [
    {
        "key": "departure_city",
        "label": "From",
        "question": "Where are you travelling from?",
        "placeholder": f"e.g. {DEFAULT_ORIGIN_CITY}",
        "options": [DEFAULT_ORIGIN_CITY, "Mumbai", "Bengaluru", "Hyderabad"],
    },
    {
        "key": "travel_dates",
        "label": "Dates",
        "question": "When are you going?",
        "placeholder": "e.g. mid-May, or 3-9 March",
        "options": ["Next month", "In 2-3 months", "Later this year", "Dates are flexible"],
    },
    {
        "key": "duration",
        "label": "Length",
        "question": "How long is the trip?",
        "placeholder": "e.g. 5 days",
        "options": ["A weekend", "5 days", "1 week", "2 weeks"],
    },
    {
        "key": "budget",
        "label": "Budget",
        "question": "What's your budget per person?",
        "placeholder": "e.g. 1.5 lakhs per person",
        "options": ["Under 50k", "50k - 1 lakh", "1 - 2 lakhs", "2 lakhs+"],
    },
    {
        "key": "vibe",
        "label": "Vibe",
        "question": "What kind of trip do you want?",
        "placeholder": "e.g. relaxed, adventurous, luxury",
        "options": ["Relaxed", "Adventurous", "Culture and history", "Nightlife", "Luxury"],
    },
    {
        "key": "interests",
        "label": "Interests",
        "question": "Anything you must do, or want to avoid?",
        "placeholder": "e.g. street food, no museums",
        "options": ["Street food", "Museums and art", "Nature and hikes", "Shopping", "Beaches"],
    },
]

# What the planner falls back to when the traveller never said. The brief marks these as assumed,
# and they go into the prompts too, so the plan is built against the same terms the brief shows.
INTAKE_DEFAULTS = {
    "departure_city": DEFAULT_ORIGIN_CITY,
    "travel_dates": "flexible, no fixed dates",
    "duration": "5 days",
    "budget": "no fixed budget",
    "vibe": "a balanced mix",
    "interests": "no must-dos",
}

# Pause at hil_agent for approval before the write-up. Off by default: intake_agent now collects the
# trip's details up front, and a follow-up message refines the plan through the same feedback_agent.
REQUIRE_APPROVAL = os.getenv("REQUIRE_APPROVAL", "false").lower() == "true"

# How many times the traveller can send the plan back before the write-up is forced
MAX_REVISIONS = int(os.getenv("MAX_REVISIONS", "3"))

def get_database_connection():
    database_url = os.getenv("POSTGRES_DB")
    if not database_url:
        raise ValueError("POSTGRES_DB is missing.")
    return database_url

# def flight_agent(state:TravelState):
#     user_query = state["user_query"]
#     flight_data = get_fl(user_query)

#     return {
#         "flight_results": flight_data,
#         "messages": [
#             AIMessage(content="Flight Results Fetched"),
#         ],
#         "llm_calls": state["llm_calls"]+1
#     }

def supervisor_agent(state:TravelState):
    user_query = state["user_query"]
    existing_plan = state.get("itinerary", "")

    # A follow-up in a thread that already has a plan, e.g. "day 2 doesn't sound good"
    if existing_plan:
        return follow_up_supervisor(state, user_query, existing_plan)

    check = guardrail_checker.invoke(
        "Decide whether this request is about travel: trips, flights, hotels, destinations, itineraries or travel advice.\n"
        "Anything else, such as coding, maths, general chat or other topics, is not allowed.\n"
        "Give one short sentence saying why.\n\n"
        f"Request: {user_query}"
    )

    allowed = bool(check and check.allowed)
    reason = check.reason if check else "Couldn't tell what this request is about."
    logger.info("supervisor | query=%r allowed=%s reason=%s", preview(user_query, 60), allowed, reason)

    if allowed:
        plan = agent_selector.invoke(
            "Choose which specialist agents to run for this travel request.\n"
            "Available agents:\n"
            "- flight_agent: live flights between the departure and destination airports\n"
            "- weather_agent: current weather and a 5-day forecast for the destination\n"
            "- itinerary_agent: writes the day-by-day plan\n"
            "- hotel_agent: searches hotels for each place the itinerary stays overnight\n"
            "- budget_agent: estimates the trip's cost and whether it fits the traveller's budget\n"
            "Pick only the ones this request needs, and say why in one sentence.\n\n"
            f"Request: {user_query}"
        )

        chosen = {name for name in plan.agents if name in AGENT_ORDER} if plan else set()

        # Hotels are searched from the itinerary's overnight stays, and the budget is costed from it
        if "hotel_agent" in chosen or "budget_agent" in chosen:
            chosen.add("itinerary_agent")

        # Fall back to the full pipeline when the choice is empty or unusable
        if not chosen:
            chosen = set(AGENT_ORDER)

        selected = [name for name in AGENT_ORDER if name in chosen]
        logger.info("supervisor | selected=%s because %s", selected, plan.reasoning if plan else "")

        return {
            "guardrail_allowed": True,
            "guardrail_reason": reason,
            "trip_request": user_query,
            "is_refinement": False,
            "selected_agents": selected,
            "supervisor_reasoning": plan.reasoning if plan else "",
            "messages": [
                AIMessage(content=f"Travel request accepted, running: {', '.join(selected)}"),
            ],
            "llm_calls": state["llm_calls"]+2
        }

    refusal = (
        "I can only help with travel planning: flights, hotels, weather and itineraries.\n\n"
        f"{reason}\n\n"
        'Try something like "Plan a 5 day trip to Barcelona from Delhi".'
    )

    return {
        "guardrail_allowed": False,
        "guardrail_reason": reason,
        "final_response": refusal,
        "messages": [
            AIMessage(content=refusal),
        ],
        "llm_calls": state["llm_calls"]+1
    }


def follow_up_supervisor(state:TravelState, user_query:str, existing_plan:str):
    """Decide whether a follow-up changes the plan already made, or asks for a different trip."""
    previous_request = state.get("trip_request", "")

    intent = intent_classifier.invoke(
        "This conversation already has a travel plan. Decide what the traveller's new message means.\n"
        "A message that comments on, corrects or adds to the existing plan is a refinement, even when it is short "
        'like "day 2 doesn\'t sound good" or "make it cheaper".\n'
        "A message describing a different trip is not a refinement; give its full trip description.\n"
        "Only a message with nothing to do with travel is not travel.\n\n"
        f"Trip so far: {previous_request}\n\n"
        f"Current plan:\n{existing_plan}\n\n"
        f"New message: {user_query}"
    )

    if not (intent and intent.is_travel):
        reason = intent.reason if intent else "Couldn't tell what this request is about."
        refusal = (
            "I can only help with travel planning: flights, hotels, weather and itineraries.\n\n"
            f"{reason}\n\n"
            'Try something like "Plan a 5 day trip to Barcelona from Delhi".'
        )
        logger.info("supervisor | follow-up refused: %s", reason)
        return {
            "guardrail_allowed": False,
            "guardrail_reason": reason,
            "final_response": refusal,
            "messages": [AIMessage(content=refusal)],
            "llm_calls": state["llm_calls"]+1
        }

    # A different trip: start over, but keep the finished plans in plan_history
    if not intent.is_refinement:
        logger.info("supervisor | follow-up is a new trip: %s", preview(intent.trip_request or user_query, 60))
        return {
            "guardrail_allowed": True,
            "guardrail_reason": intent.reason,
            "trip_request": intent.trip_request or user_query,
            "is_refinement": False,
            "itinerary": "",  # don't revise the old trip's plan
            "itinerary_days": [],
            "selected_agents": list(AGENT_ORDER),
            "messages": [AIMessage(content="New trip request, planning from scratch")],
            "llm_calls": state["llm_calls"]+1
        }

    # A change to the existing plan: hand it to feedback_agent, the same path as the Request changes button
    logger.info("supervisor | follow-up refines the plan: %s", preview(user_query, 60))
    return {
        "guardrail_allowed": True,
        "guardrail_reason": intent.reason,
        "trip_request": previous_request or user_query,
        "is_refinement": True,
        "human_feedback": user_query,
        "messages": [AIMessage(content="Reworking the plan you already have")],
        "llm_calls": state["llm_calls"]+1
    }


# The next agent the supervisor picked after this one, or the write-up when none are left
def route_next(state:TravelState, current:str | None = None):
    selected = state.get("selected_agents") or AGENT_ORDER
    start = AGENT_ORDER.index(current) + 1 if current else 0

    for name in AGENT_ORDER[start:]:
        if name in selected:
            return name

    # Specialists done, so ask the traveller to approve the plan, unless approval is switched off
    return "hil_agent" if REQUIRE_APPROVAL else "final_response_agent"


# Sends the workflow on to the chosen specialists, or stops it when the guardrail said no
def route_after_supervisor(state:TravelState):
    if not state["guardrail_allowed"]:
        return END

    # A follow-up that changes the plan goes through the same agent the approval loop uses
    if state.get("is_refinement"):
        return "feedback_agent"

    # A new trip collects its missing details first
    return "intake_agent"


def intake_agent(state:TravelState):
    """Ask the traveller for the trip details their request didn't mention, before any planning starts"""
    # Follow-ups refine an existing plan, so they never get asked
    if state.get("is_refinement") or state.get("intake_done"):
        return {"intake_done": True}

    trip_request = state.get("trip_request") or state["user_query"]

    found = constraints_extractor.invoke(
        "Pull the trip details out of this travel request. Use null for anything it doesn't say; never guess.\n\n"
        f"Request: {trip_request}"
    )
    # Every field the extractor returns, not just the ones asked as questions, so destination is kept too
    constraints = {key: (getattr(found, key, None) or "").strip() for key in TripConstraints.model_fields} if found else {}

    missing = [field for field in INTAKE_FIELDS if not constraints.get(field["key"])]

    if not missing:
        logger.info("intake_agent | nothing to ask, all details given")
        return {
            **resolve_constraints(constraints),
            "intake_done": True,
            "llm_calls": state["llm_calls"]+1
        }

    logger.info("intake_agent | asking for %s", [field["key"] for field in missing])

    # Raises GraphInterrupt the first time; on resume it returns the answers the traveller gave
    answers = interrupt({
        "type": "intake",
        "intro": "A few details first, so the plan fits your trip.",
        "questions": [{**field, "value": constraints.get(field["key"], "")} for field in missing],
    })

    if isinstance(answers, dict) and not answers.get("skipped"):
        for field in INTAKE_FIELDS:
            answer = str(answers.get(field["key"], "") or "").strip()
            if answer:
                constraints[field["key"]] = answer

    logger.info("intake_agent | answered: %s", {k: v for k, v in constraints.items() if v})

    return {
        **resolve_constraints(constraints),
        "intake_done": True,
        "messages": [
            AIMessage(content="Trip details noted"),
        ],
        "llm_calls": state["llm_calls"]+1
    }


def resolve_constraints(constraints:dict):
    """Fill in what the traveller never gave, and record which details were assumed rather than stated"""
    resolved = dict(constraints)
    assumed = [key for key, fallback in INTAKE_DEFAULTS.items() if not resolved.get(key)]

    for key in assumed:
        resolved[key] = INTAKE_DEFAULTS[key]

    if assumed:
        logger.info("intake_agent | assumed %s", assumed)

    return {"trip_constraints": resolved, "assumed_constraints": assumed}


def trip_brief(state:dict):
    """The terms the plan was made against, for the strip shown above it"""
    constraints = state.get("trip_constraints") or {}
    assumed = set(state.get("assumed_constraints") or [])

    return [
        {"label": field["label"], "value": constraints[field["key"]], "assumed": field["key"] in assumed}
        for field in INTAKE_FIELDS
        if constraints.get(field["key"])
    ]


def destination_photo(destination:str):
    """A photo of the destination for the plan's header card, from the same search the preview panel uses.
    Candidates are checked first, because a dead or non-image link leaves a hole in the card."""
    images = search_place(f"{destination} skyline landmark scenic view", max_results=6).get("images") or []

    for image in images:
        url = image.get("url", "")
        # Stock libraries serve watermarked previews, which look broken on a card
        if not url or any(host in url for host in STOCK_PHOTO_HOSTS):
            continue

        try:
            response = requests.head(url, timeout=5, allow_redirects=True)
        except requests.exceptions.RequestException:
            continue

        if response.status_code == 200 and response.headers.get("content-type", "").startswith("image/"):
            logger.info("destination_photo | %s: %s", destination, preview(url, 70))
            return url

    logger.info("destination_photo | %s: nothing usable from %s candidates", destination, len(images))
    return ""


def title_case(text:str):
    """Capitalise a place the traveller typed in lower case, without flattening DXB or UAE"""
    return " ".join(word if word[:1].isupper() else word.capitalize() for word in text.split())


def trip_header(state:dict):
    """The plan's title card: where the trip goes, on what terms, and what it's estimated to cost"""
    constraints = state.get("trip_constraints") or {}
    destination = (constraints.get("destination") or "").strip()

    if not destination:
        return None

    return {
        "destination": title_case(destination),
        "summary": state.get("plan_summary", ""),
        "dates": constraints.get("travel_dates", ""),
        "duration": constraints.get("duration", ""),
        "origin": title_case(constraints.get("departure_city", "")),
        # Always an estimate: no fares come back with the flight data, and hotels rarely carry prices
        "total": state.get("budget_total", ""),
        "image": state.get("destination_image", ""),
    }


def constraints_text(state:TravelState):
    """The trip's terms as a prompt block, saying which ones the traveller never actually gave"""
    constraints = state.get("trip_constraints") or {}
    assumed = set(state.get("assumed_constraints") or [])
    lines = []

    for field in INTAKE_FIELDS:
        value = constraints.get(field["key"])
        if not value:
            continue
        note = " (assumed, the traveller didn't say)" if field["key"] in assumed else ""
        lines.append(f"- {field['question'].rstrip('?')}: {value}{note}")

    if not lines:
        return ""

    return "\n\nTrip details, to plan against:\n" + "\n".join(lines)


def flight_agent(state:TravelState):
    user_query = state.get("trip_request") or state["user_query"]
    departure_city = (state.get("trip_constraints") or {}).get("departure_city")
    if departure_city:
        user_query = f"{user_query} departing from {departure_city}"

    # The MCP list_routes tool needs a paid AviationStack plan, so this calls /flights directly.
    # search_flights works out the airports itself, with its own LLM call.
    flight_data = search_flights(user_query)
    logger.info("flight_agent | result=%s", preview(flight_data))

    return {
        "flight_results": flight_data,
        "messages": [
            AIMessage(content="Flight Results Fetched"),
        ],
        "llm_calls": state["llm_calls"]+1
    }

def weather_agent(state:TravelState):
    user_query = state.get("trip_request") or state["user_query"]

    destination = destination_extractor.invoke(
        "Name the main destination city of this travel request.\n"
        "Give a city, not a country (e.g. Japan -> Tokyo, Spain -> Madrid).\n"
        "Use null if no destination is mentioned.\n\n"
        f"Request: {user_query}"
    )

    if destination and destination.city:
        logger.info("weather_agent | city=%s", destination.city)
        weather_data = run_sync(get_weather(destination.city))
    else:
        weather_data = f"Couldn't work out the destination city from: {user_query}"
        logger.warning("weather_agent | no city found in %r", preview(user_query, 60))

    logger.info("weather_agent | result=%s", preview(weather_data))

    return {
        "weather_results": weather_data,
        "messages": [
            AIMessage(content="Weather Fetched"),
        ],
        "llm_calls": state["llm_calls"]+1
    }

def stay_location(stay:Stay):
    return f"{stay.area}, {stay.city}" if stay.area else stay.city


def shortlist_hotels(stays:list, candidates:list):
    """Pick HOTELS_PER_CITY hotels for each stay, keeping only links the search actually returned"""
    listing = []
    for index, (stay, results) in enumerate(zip(stays, candidates)):
        lines = [f"Stay {index}: {stay_location(stay)}"]
        lines += [f"- {result['title']} | {result['url']} | {result['content'][:200]}" for result in results]
        listing.append("\n".join(lines))

    shortlist = hotel_picker.invoke(
        f"Choose the {HOTELS_PER_CITY} best hotels for each stay below, from that stay's own search results.\n"
        "Prefer hotels that are well placed for the stay's area and well reviewed.\n"
        "Give each hotel's own name, like 'Rove Downtown'. Many of these results are round-up articles listing "
        "several hotels, so never use an article or category title, like 'The best hotels in Dubai', as a name.\n"
        "Copy each hotel's url exactly from the result it came from; never write a url that isn't listed.\n\n"
        + "\n\n".join(listing)
    )

    chosen = {entry.stay_index: entry.hotels for entry in shortlist.stays} if shortlist else {}
    picks = []

    for index, (stay, results) in enumerate(zip(stays, candidates)):
        allowed = {result["url"]: result for result in results}
        seen = set()
        kept = []

        for hotel in chosen.get(index, []):
            # Drop anything whose link the search didn't return, rather than show an invented one
            if hotel.url in allowed and hotel.url not in seen:
                seen.add(hotel.url)
                kept.append({"name": hotel.name, "url": hotel.url, "why": hotel.why})

        # Top up from the search results when the model returned too few, or made links up
        for result in results:
            if len(kept) >= HOTELS_PER_CITY:
                break
            if result["url"] not in seen:
                seen.add(result["url"])
                kept.append({"name": result["title"], "url": result["url"], "why": result["content"][:200]})

        for hotel in kept[:HOTELS_PER_CITY]:
            picks.append({
                **hotel,
                "url": resolve_hotel_link(hotel["name"], stay.city) or hotel["url"],
                "city": stay.city,
                "area": stay.area or "",
                "nights": stay.nights or 0,
            })

    return picks


def resolve_hotel_link(name:str, city:str):
    """The hotel's own page. Searching 'best hotels in X' returns round-up articles, not the hotels
    themselves, so the shortlisted name is looked up again to get a link that goes where it says."""
    results = search_place(f"{name} {city} hotel", max_results=3).get("results") or []
    return results[0]["url"] if results else None


def hotels_text(picks:list):
    """The shortlist as a prompt block, so the write-up and the budget can use it"""
    lines = []
    for hotel in picks:
        where = f"{hotel['area']}, {hotel['city']}" if hotel["area"] else hotel["city"]
        nights = f" for {hotel['nights']} nights" if hotel["nights"] else ""
        lines.append(f"- {hotel['name']} in {where}{nights} | {hotel['url']} | {hotel['why']}")

    return "\n".join(lines)


def hotel_agent(state:TravelState):
    user_query = state.get("trip_request") or state["user_query"]
    itinerary = state.get("itinerary", "")

    result = stay_extractor.invoke(
        "List every place the traveller stays overnight in this itinerary, in trip order.\n\n"
        f"Itinerary:\n{itinerary}"
    )
    stays = result.stays if result else []

    stays = stays[:MAX_STAYS]
    logger.info("hotel_agent | stays=%s", [stay.city for stay in stays] or "none found")

    # Couldn't read any stays from the itinerary, so search on the original request instead
    if not stays:
        stays = [Stay(city=user_query, area=None, nights=None)]

    # This uses Tavily over REST, not MCP, because the shortlist needs each hotel's own link
    # and the MCP tool flattens its results into one block of text
    candidates = []
    for stay in stays:
        location = stay_location(stay)
        logger.info("hotel_agent | searching hotels in %s", location)
        found = search_place(f"best hotels in {location}", max_results=6)
        candidates.append([result for result in found["results"] if result.get("url")])

    picks = shortlist_hotels(stays, candidates)
    logger.info("hotel_agent | shortlisted %s hotels across %s stays", len(picks), len(stays))

    return {
        "hotel_results": hotels_text(picks),
        "hotel_picks": picks,
        "messages": [
            AIMessage(content="Hotel Results Fetched"),
        ],
        "llm_calls": state["llm_calls"]+1
    }


def itinerary_markdown(plan:Itinerary):
    """The structured plan as Markdown, for the agents downstream that read the itinerary as text"""
    parts = [plan.overview.strip()] if plan.overview else []

    for day in plan.days:
        heading = f"## {day.label}: {day.heading}" if day.heading else f"## {day.label}"
        lines = [f"- **{item.time}** {item.text}" for item in day.items]
        parts.append("\n".join([heading, *lines]))

    return "\n\n".join(parts)


def itinerary_agent(state:TravelState):
    user_query = state.get("trip_request") or state["user_query"]
    flight_data = state.get("flight_results", "")
    weather_data = state.get("weather_results", "")
    human_feedback = state.get("human_feedback", "") if not state.get("approved") else ""
    feedback_history = state.get("feedback_history", []) if human_feedback else []
    previous_itinerary = state.get("itinerary", "") if human_feedback else ""

    ITINERARY_PROMPT = """You are a travel planner. Using the user's request and the flight and weather data below, plan the trip day by day.
Put in the overview which area to stay in and for how many nights in each city, and say which defaults you picked if the traveller didn't give trip length or budget.
Give every day a label like "Day 1", a short heading naming the day, and its activities in order, each with the time it happens.
When a previous version and feedback are given, revise that version: change what the feedback asks for, follow every earlier round of feedback too, and leave the rest of the plan as it was.
Don't name specific hotels; those are searched separately.
Inside each activity's text, make every place worth visiting a Markdown link to a Google search, like [Sagrada Familia](https://www.google.com/search?q=Sagrada+Familia+Barcelona): keep the place's own name as the link text, and put the place and its city in the query with spaces as +. Link each place the first time it appears, not every time. This matters: the traveller opens these links to see the place.
Never put brackets or parentheses inside a link's url, as they break the link: drop them from the query, so "Casa Mila (La Pedrera)" becomes query=Casa+Mila,+Barcelona.
Plan around the weather: put outdoor activities on the clearer days and indoor ones on wet days, and say when you do so.
The forecast only covers the next few days, so ignore it if the trip starts later.
Use only the flights in the data; don't make any up.
If the flight data is missing, empty or shows an error, still write the full itinerary. Say in the overview that live flights couldn't be fetched and that the traveller should book separately. Never refuse to plan the trip over missing flights."""


    trip_details = f"""User request:
{user_query}

Flight data:
{flight_data}

Weather data:
{weather_data}""" + constraints_text(state)

    if previous_itinerary:
        trip_details += f"""

Previous version of the itinerary, to revise:
{previous_itinerary}"""

    if feedback_history or human_feedback:
        rounds = feedback_history or [human_feedback]
        joined = "\n".join(f"- {item}" for item in rounds)
        trip_details += f"""

Traveller's feedback so far, most recent last:
{joined}"""

    messages = [
        SystemMessage(content=ITINERARY_PROMPT),
        HumanMessage(content=trip_details),
    ]
    plan = itinerary_writer.invoke(messages)

    if plan and plan.days:
        itinerary = itinerary_markdown(plan)
        days = [day.model_dump() for day in plan.days]
        logger.info("itinerary_agent | %s days, %s characters", len(days), len(itinerary))
    else:
        # Structured output can come back empty; fall back to a plain write-up so the run still finishes
        itinerary = llm.invoke(messages).text
        days = []
        logger.info("itinerary_agent | no structured days, wrote %s characters", len(itinerary))

    return {
        "itinerary": itinerary,
        "itinerary_days": days,
        "messages": [
            AIMessage(content=itinerary),
        ],
        "llm_calls": state["llm_calls"]+1
    }

def cost_summary(estimate):
    """The cost table for the plan: its lines, the total, and how much of a stated budget that uses"""
    if not estimate:
        return {"lines": [], "total": "", "ceiling": "", "percent": None}

    total, ceiling = estimate.total_value, estimate.ceiling_value
    # Worked out here rather than trusted from the model, and only against a budget the traveller gave
    percent = round(total / ceiling * 100) if total and ceiling and ceiling > 0 else None

    return {
        "lines": [
            {"label": line.label, "amount": line.amount, "note": line.note or ""}
            for line in estimate.lines
        ],
        "total": estimate.total or "",
        "ceiling": estimate.ceiling_label or "",
        "percent": percent,
    }


def budget_agent(state:TravelState):
    """Analyze whether the planned trip fits the user's budget"""
    user_query = state.get("trip_request") or state["user_query"]
    flight_data = state.get("flight_results", "")
    hotels_data = state.get("hotel_results", "")
    itinerary = state.get("itinerary", "")

    BUDGET_PROMPT = """You are a travel budget analyst. Work out roughly what the planned trip costs and whether it fits the traveller's budget.
Break the cost down into one line each for flights, accommodation, food, local transport and activities, and give a total range per person.
Make the accommodation line name the area and the number of nights, like "Stay · Downtown · 4 nights".
Use the traveller's own currency if the request names one.
Every figure is an estimate: the flight data carries no fares, and the hotel data only sometimes mentions prices.
Only fill in the traveller's budget when they actually named one. If they didn't, leave it null rather than inventing a ceiling.
The verdict says whether the trip fits that budget and what to cut if it doesn't, in one short paragraph under 120 words. Don't repeat the breakdown there: it is shown as its own table."""

    trip_details = f"""User request:
{user_query}

Flight data:
{flight_data}

Hotel data:
{hotels_data}

Itinerary:
{itinerary}""" + constraints_text(state)

    messages = [
        SystemMessage(content=BUDGET_PROMPT),
        HumanMessage(content=trip_details),
    ]
    estimate = budget_writer.invoke(messages)

    # Structured output can come back empty; fall back to a plain write-up so the run still finishes
    budget_results = estimate.analysis if estimate else llm.invoke(messages).text
    budget_total = (estimate.total or "") if estimate else ""
    budget_costs = cost_summary(estimate)
    logger.info(
        "budget_agent | total=%r lines=%s %s",
        budget_total, len(budget_costs["lines"]), preview(budget_results),
    )

    return {
        "budget_results": budget_results,
        "budget_total": budget_total,
        "budget_costs": budget_costs,
        "messages": [
            AIMessage(content="Budget Analysed"),
        ],
        "llm_calls": state["llm_calls"]+1
    }

def hil_agent(state:TravelState):
    """Pause so the traveller can approve the plan, or send it back with feedback"""
    itinerary = state.get("itinerary", "")
    budget_data = state.get("budget_results", "")

    approval_request = (
        "Here is the plan so far. Approve it, or say what you'd like changed.\n\n"
        f"Itinerary:\n{itinerary}\n\n"
        f"Budget:\n{budget_data}"
    )

    logger.info("hil_agent | pausing for approval; resume with resume_travel_agent(thread_id, ...)")

    # Raises GraphInterrupt the first time; on resume it returns whatever Command(resume=...) carried
    answer = interrupt({
        "type": "approval",
        "question": "Approve this travel plan?",
        "itinerary": itinerary,
        "budget": budget_data,
    })

    if isinstance(answer, dict):
        approved = bool(answer.get("approved"))
        feedback = answer.get("feedback", "")
    else:
        feedback = str(answer).strip()
        approved = feedback.lower() in {"yes", "y", "ok", "approve", "approved"}

    logger.info("hil_agent | resumed approved=%s feedback=%r", approved, preview(feedback, 60))

    # Keep every round's feedback, so a later revision can't undo an earlier one
    feedback_history = state.get("feedback_history", [])
    if feedback and not approved:
        feedback_history = [*feedback_history, feedback]

    return {
        "approval_request": approval_request,
        "approved": approved,
        "human_feedback": feedback,
        "feedback_history": feedback_history,
        "messages": [
            AIMessage(content="Plan approved" if approved else f"Changes requested: {feedback}"),
        ],
    }

def feedback_agent(state:TravelState):
    """Work out which specialists have to run again to answer the traveller's feedback"""
    feedback = state.get("human_feedback", "")
    itinerary = state.get("itinerary", "")

    plan = replan_selector.invoke(
        "The traveller asked for changes to their travel plan. Choose which specialist agents must run again.\n"
        "Available agents:\n"
        "- flight_agent: live flights between the departure and destination airports\n"
        "- weather_agent: current weather and a 5-day forecast for the destination\n"
        "- itinerary_agent: writes the day-by-day plan\n"
        "- hotel_agent: searches hotels for each place the itinerary stays overnight\n"
        "- budget_agent: estimates the trip's cost and whether it fits the traveller's budget\n"
        "Pick only the agents whose data must change. If the feedback is about wording, length or emphasis, "
        "return an empty list, because the plan is rewritten anyway.\n"
        "Say why in one sentence.\n\n"
        f"Feedback: {feedback}\n\n"
        f"Current itinerary:\n{itinerary}"
    )

    chosen = {name for name in plan.agents if name in AGENT_ORDER} if plan else set()

    # Hotels are searched from the itinerary's overnight stays, and the budget is costed from it
    if "hotel_agent" in chosen or "budget_agent" in chosen:
        chosen.add("itinerary_agent")

    selected = [name for name in AGENT_ORDER if name in chosen]
    revision_count = state.get("revision_count", 0) + 1
    logger.info(
        "feedback_agent | revision=%s re-running=%s because %s",
        revision_count, selected or "nothing, rewriting only", plan.reasoning if plan else "",
    )

    return {
        "selected_agents": selected,
        "replan_reasoning": plan.reasoning if plan else "",
        "revision_count": revision_count,
        "messages": [
            AIMessage(content=f"Reworking the plan: {', '.join(selected) if selected else 'rewriting the write-up'}"),
        ],
        "llm_calls": state["llm_calls"]+1
    }


# Approved plans go to the write-up; rejected ones go back for a re-plan, up to MAX_REVISIONS times
def route_after_hil(state:TravelState):
    if state.get("approved"):
        return "final_response_agent"

    if state.get("revision_count", 0) >= MAX_REVISIONS:
        logger.info("route_after_hil | revision cap of %s reached, writing the plan up", MAX_REVISIONS)
        return "final_response_agent"

    return "feedback_agent"


# Re-run the chosen specialists, or go straight to the write-up when the feedback is only about wording
def route_after_feedback(state:TravelState):
    if state.get("selected_agents"):
        return route_next(state)
    return "final_response_agent"


def final_response_agent(state:TravelState):
    user_query = state.get("trip_request") or state["user_query"]
    flight_data = state.get("flight_results", "")
    hotels_data = state.get("hotel_results", "")
    weather_data = state.get("weather_results", "")
    itinerary = state.get("itinerary", "")
    budget_data = state.get("budget_results", "")
    human_feedback = state.get("human_feedback", "") if not state.get("approved") else ""

    FINAL_RESPONSE_PROMPT = """You are a travel planner. Combine the user's request, flight data, hotel data, weather data, budget analysis and itinerary below into one clear, well-formatted travel plan in Markdown.
Write these sections in this order, and start each one with a Markdown "## " heading, exactly: "## Trip Overview", "## Flights", "## Hotels", "## Weather", "## Estimated Budget", "## Travel Tips". Use bullet points and tables where they help.
Don't write the day-by-day plan: it is rendered from the itinerary below. Instead put the line [[ITINERARY]] on its own, between the Hotels section and the Weather section, and it will be shown there.
Don't list the hotels either: they are rendered from the hotel data below. Under the "## Hotels" heading write one line on how the stays are split across the trip, then put the line [[HOTELS]] on its own, and the shortlist will be shown there.
Every place you name anywhere in the plan must be a Markdown link to a Google search, like [Sagrada Familia](https://www.google.com/search?q=Sagrada+Familia+Barcelona), with spaces as + in the query. That includes the places named in the Trip Overview and Travel Tips. Link each place the first time it appears, not every time.
Never put brackets or parentheses inside a link's url, as they break the link: drop them from the query, so "Casa Mila (La Pedrera)" becomes query=Casa+Mila,+Barcelona.
In the Weather section, give the current conditions and the daily forecast from the weather data, and say that the forecast covers only the next few days.
Under the "## Estimated Budget" heading, give the budget analysis's verdict on whether the trip fits, then put the line [[COSTS]] on its own. The cost breakdown is rendered there, so don't list the figures yourself.
When the traveller has given feedback, rework the plan to follow it and say at the top what you changed. Their feedback outweighs the itinerary above.
Use only the flights, hotels and weather in the data; don't make any up.
If any of the data is missing, empty or shows an error, still write the whole plan: say in that section only that the information wasn't available and what the traveller should do instead. Never refuse the plan because one source is missing."""

    trip_details = f"""User request:
{user_query}

Flight data:
{flight_data}

Hotel data:
{hotels_data}

Weather Data:
{weather_data}

Budget analysis:
{budget_data}

Itinerary:
{itinerary}""" + constraints_text(state)

    if human_feedback:
        trip_details += f"""

Traveller's feedback on the plan:
{human_feedback}"""

    messages = [
        SystemMessage(content=FINAL_RESPONSE_PROMPT),
        HumanMessage(content=trip_details),
    ]
    written = final_plan_writer.invoke(messages)

    # Structured output can come back empty; fall back to a plain write-up so the run still finishes
    final_response = written.plan if written and written.plan else llm.invoke(messages).text
    summary = written.summary if written else ""
    logger.info(
        "final_response_agent | wrote %s characters, feedback applied=%s, summary=%r",
        len(final_response),
        bool(human_feedback),
        preview(summary, 60),
    )

    destination = (state.get("trip_constraints") or {}).get("destination", "")
    image = destination_photo(destination) if destination else ""

    # Keep the last few finished plans, so a follow-up in this thread has something to build on
    plan_history = [*state.get("plan_history", [])[-2:], f"Request: {user_query}\n\nPlan:\n{itinerary}"]

    return {
        "final_response": final_response,
        "plan_summary": summary,
        "destination_image": image,
        "plan_history": plan_history,
        "messages": [
            AIMessage(content=final_response),
        ],
        "llm_calls": state["llm_calls"]+1
    }

graph = StateGraph(TravelState)

graph.add_node("supervisor_agent", supervisor_agent)
graph.add_node("intake_agent", intake_agent)
graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("weather_agent",weather_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("budget_agent", budget_agent)
graph.add_node("hil_agent", hil_agent)
graph.add_node("feedback_agent", feedback_agent)
graph.add_node("final_response_agent", final_response_agent)


graph.add_edge(START, "supervisor_agent")
graph.add_conditional_edges(
    "supervisor_agent",
    route_after_supervisor,
    ["intake_agent", "feedback_agent", END],
)

# Planning starts once the trip details are in
graph.add_conditional_edges("intake_agent", route_next, [*AGENT_ORDER, "hil_agent", "final_response_agent"])

# Each specialist hands over to the next one the supervisor picked, skipping the rest
for agent_name in AGENT_ORDER:
    graph.add_conditional_edges(
        agent_name,
        partial(route_next, current=agent_name),
        [*AGENT_ORDER, "hil_agent", "final_response_agent"],
    )

graph.add_conditional_edges("hil_agent", route_after_hil, ["feedback_agent", "final_response_agent"])
graph.add_conditional_edges("feedback_agent", route_after_feedback, [*AGENT_ORDER, "final_response_agent"])
graph.add_edge("final_response_agent", END)

DATABASE_URL = get_database_connection()
_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row
)

checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)

def _config(thread_id:str):
    return {
        "configurable": {
            "thread_id": thread_id
        }
    }


def _initial_state(query:str):
    # Only this run's bookkeeping is reset. The previous run's trip_request, itinerary and other
    # results stay in the thread's checkpoint, so a follow-up can build on the plan already made.
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "is_refinement": False,
        "intake_done": False,

        # Supervisor + guardrail state
        "guardrail_allowed": False,
        "guardrail_reason": "",
        "selected_agents": [],
        "trip_constraints": {},
        "assumed_constraints": [],
        "supervisor_reasoning": "",

        # Approval state
        "approval_request": "",
        "approved": False,
        "human_feedback": "",
        "feedback_history": [],
        "revision_count": 0,
        "replan_reasoning": "",
        "final_response": "",

        "llm_calls": 0,
    }


def run_travel_agent(query:str, thread_id:str| None = None):
    if not thread_id:
        thread_id = uuid.uuid4().hex

    config = _config(thread_id)

    logger.info("run | thread=%s query=%r", thread_id, preview(query, 80))
    result = travel_graph.invoke(_initial_state(query), config=config)

    return format_result(thread_id, result)


def resume_travel_agent(thread_id:str, answer:dict):
    """Answer whatever the run paused on: intake questions, or the approval question."""
    config = _config(thread_id)

    logger.info("resume | thread=%s answer=%s", thread_id, preview(answer, 100))
    result = travel_graph.invoke(Command(resume=answer), config=config)

    return format_result(thread_id, result)


def stream_travel_agent(query:str, thread_id:str | None = None):
    """Same as run_travel_agent, but yields a progress event as each agent starts and finishes."""
    if not thread_id:
        thread_id = uuid.uuid4().hex

    config = _config(thread_id)
    logger.info("stream | thread=%s query=%r", thread_id, preview(query, 80))

    yield from _progress_events(
        travel_graph.stream(_initial_state(query), config=config, stream_mode=["tasks", "updates"]),
        thread_id,
        config,
    )


def stream_resume_travel_agent(thread_id:str, answer:dict):
    """Same as resume_travel_agent, but yields progress events while the rest of the plan runs."""
    config = _config(thread_id)
    logger.info("stream resume | thread=%s answer=%s", thread_id, preview(answer, 100))

    yield from _progress_events(
        travel_graph.stream(Command(resume=answer), config=config, stream_mode=["tasks", "updates"]),
        thread_id,
        config,
    )


def _progress_events(stream, thread_id:str, config:dict):
    """Turn LangGraph's stream into progress events, ending with the plan or the question it paused on."""
    pause = None

    for mode, chunk in stream:
        if mode == "tasks":
            # The event that starts a node carries its input; the one that ends it carries a result
            if "result" in chunk:
                yield {"event": "agent_finished", "data": {"agent": chunk.get("name"), "failed": bool(chunk.get("error"))}}
            else:
                yield {"event": "agent_started", "data": {"agent": chunk.get("name")}}
            continue

        interrupts = chunk.get("__interrupt__")
        if interrupts:
            pause = interrupts[0].value
            continue

        # Both the supervisor and the feedback agent choose which specialists run
        for update in chunk.values():
            if isinstance(update, dict) and update.get("selected_agents") is not None:
                yield {"event": "agents_selected", "data": {"agents": update["selected_agents"]}}

    result = format_result(thread_id, travel_graph.get_state(config).values)

    if pause:
        result = {
            **result,
            "pause_type": pause.get("type", "approval") if isinstance(pause, dict) else "approval",
            "pause_payload": pause,
            "final_response": "",
            "days": [],
            "hotels": [],
            "brief": [],
            "costs": None,
            "header": None,
        }

    yield {"event": "done", "data": result}


def format_result(thread_id:str, result:dict):
    interrupts = result.get("__interrupt__")

    # The run paused at intake_agent or hil_agent; answer it with resume_travel_agent(thread_id, ...)
    if interrupts:
        payload = interrupts[0].value
        return {
            "thread_id": thread_id,
            "pause_type": payload.get("type", "approval") if isinstance(payload, dict) else "approval",
            "pause_payload": payload,
            "final_response": "",
            "days": [],
            "hotels": [],
            "brief": [],
            "costs": None,
            "header": None,
            "llm_calls": result.get("llm_calls", 0),
        }

    return {
        "thread_id": thread_id,
        "pause_type": None,
        "pause_payload": None,
        "final_response": result.get("final_response", ""),
        # The day-by-day plan and the hotel shortlist, which the UI renders as cards instead of prose
        "days": result.get("itinerary_days", []),
        "hotels": result.get("hotel_picks", []),
        # The terms the plan was made against, shown as a strip above it
        "brief": trip_brief(result),
        "costs": result.get("budget_costs") or None,
        # The plan's title card, under the brief
        "header": trip_header(result),
        "llm_calls": result.get("llm_calls", 0),
    }

