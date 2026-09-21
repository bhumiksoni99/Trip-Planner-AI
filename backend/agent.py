import os
import logging
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import TypedDict, Annotated, Any
import uuid
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
    user_query: str

    # Supervisor + guardrail state
    guardrail_allowed: bool
    guardrail_reason: str
    selected_agents: list[str]
    trip_constraints: dict[str, Any]
    supervisor_reasoning: str

    # Original specialist results
    flight_results: str
    hotel_results: str
    weather_results: str
    itinerary: str

    # New budget + HITL state
    budget_results: str
    approval_request: str
    approved: bool
    human_feedback: str
    final_response: str

    llm_calls: int

class Guardrail(BaseModel):
    allowed: bool = Field(description="True if the request is about travel")
    reason: str = Field(description="One short sentence explaining the decision")

class AgentPlan(BaseModel):
    agents: list[str] = Field(description="Names of the specialist agents to run, from the available list")
    reasoning: str = Field(description="One short sentence explaining the choice")

class Destination(BaseModel):
    city: str | None = Field(description="Main destination city of the trip")

class Stay(BaseModel):
    city: str = Field(description="City the traveller stays overnight in")
    area: str | None = Field(description="Neighbourhood or area to stay in, if the itinerary names one")
    nights: int | None = Field(description="Number of nights spent in this city")

class Stays(BaseModel):
    stays: list[Stay] = Field(description="Every place the traveller stays overnight, in trip order")

stay_extractor = llm.with_structured_output(Stays)
destination_extractor = llm.with_structured_output(Destination)
guardrail_checker = llm.with_structured_output(Guardrail)
agent_selector = llm.with_structured_output(AgentPlan)

# The specialists in the order they run; the supervisor picks a subset of these
AGENT_ORDER = ["flight_agent", "weather_agent", "itinerary_agent", "hotel_agent", "budget_agent"]

# Caps the hotel searches per trip, one search per stay
MAX_STAYS = 5

# Used when the request names only a destination, e.g. "Plan a Japan trip"
DEFAULT_ORIGIN = os.getenv("DEFAULT_ORIGIN", "DEL")

# Pause at hil_agent for approval before the write-up. Off until the UI can answer it.
REQUIRE_APPROVAL = os.getenv("REQUIRE_APPROVAL", "true").lower() == "true"

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
    return route_next(state)


def flight_agent(state:TravelState):
    user_query = state["user_query"]

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
    user_query = state["user_query"]

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

def hotel_agent(state:TravelState):
    user_query = state["user_query"]
    itinerary = state["itinerary"]

    result = stay_extractor.invoke(
        "List every place the traveller stays overnight in this itinerary, in trip order.\n\n"
        f"Itinerary:\n{itinerary}"
    )
    stays = result.stays if result else []

    # if stays:
    #     hotel_sections = []
    #     for stay in stays[:MAX_STAYS]:
    #         location = f"{stay.area}, {stay.city}" if stay.area else stay.city
    #         nights = f" for {stay.nights} nights" if stay.nights else ""
    #         search_results = search_tavily(f"best hotels in {location}{nights}")
    #         hotel_sections.append(f"Hotels in {location}{nights}:\n{search_results}")
    #     hotels_data = "\n\n".join(hotel_sections)
    # else:
    #     # Couldn't read any stays from the itinerary, so search on the original request
    #     hotels_data = search_tavily(f"best hotels for: {user_query}")

    logger.info("hotel_agent | stays=%s", [stay.city for stay in stays] or "none found")

    if stays:
        hotel_sections = []
        for stay in stays[:MAX_STAYS]:
            location = f"{stay.area}, {stay.city}" if stay.area else stay.city
            nights = f" for {stay.nights} nights" if stay.nights else ""
            logger.info("hotel_agent | searching hotels in %s%s", location, nights)
            search_results = run_sync(tavily_search(f"best hotels in {location}{nights}"))
            hotel_sections.append(f"Hotels in {location}{nights}:\n{search_results}")
        hotels_data = "\n\n".join(hotel_sections)
    else:
        # Couldn't read any stays from the itinerary, so search on the original request
        hotels_data = run_sync(tavily_search(f"best hotels for: {user_query}"))



    return {
        "hotel_results": hotels_data,
        "messages": [
            AIMessage(content="Hotel Results Fetched"),
        ],
        "llm_calls": state["llm_calls"]+1
    }


def itinerary_agent(state:TravelState):
    user_query = state["user_query"]
    flight_data = state["flight_results"]
    weather_data = state["weather_results"]

    ITINERARY_PROMPT = """You are a travel planner. Using the user's request and the flight and weather data below, write a day-by-day travel itinerary in Markdown.
For each city, say which area to stay in and for how many nights, but don't name specific hotels; those are searched separately.
Plan around the weather: put outdoor activities on the clearer days and indoor ones on wet days, and say when you do so.
The forecast only covers the next few days, so ignore it if the trip starts later.
Use only the flights in the data; don't make any up. If the user didn't give trip length or budget, pick sensible defaults and say so."""


    trip_details = f"""User request:
{user_query}

Flight data:
{flight_data}

Weather data:
{weather_data}"""

    response = llm.invoke([
        SystemMessage(content=ITINERARY_PROMPT),
        HumanMessage(content=trip_details),
    ])
    itinerary = response.text
    logger.info("itinerary_agent | wrote %s characters", len(itinerary))

    return {
        "itinerary": itinerary,
        "messages": [
            AIMessage(content=itinerary),
        ],
        "llm_calls": state["llm_calls"]+1
    }

def budget_agent(state:TravelState):
    """Analyze whether the planned trip fits the user's budget"""
    user_query = state["user_query"]
    flight_data = state["flight_results"]
    hotels_data = state["hotel_results"]
    itinerary = state["itinerary"]

    BUDGET_PROMPT = """You are a travel budget analyst. Work out roughly what the planned trip costs and whether it fits the traveller's budget.
Break the cost down by flights, accommodation, food, local transport and activities, and give a total range per person.
Use the traveller's own currency if the request names one.
Label every figure an estimate: the flight data carries no fares, and the hotel data only sometimes mentions prices.
If the request names a budget, say plainly whether the trip fits it, and if it doesn't, say what to cut.
If no budget is given, say so and give the estimate anyway. Answer in Markdown, under 250 words."""

    trip_details = f"""User request:
{user_query}

Flight data:
{flight_data}

Hotel data:
{hotels_data}

Itinerary:
{itinerary}"""

    response = llm.invoke([
        SystemMessage(content=BUDGET_PROMPT),
        HumanMessage(content=trip_details),
    ])
    budget_results = response.text
    logger.info("budget_agent | %s", preview(budget_results))

    return {
        "budget_results": budget_results,
        "messages": [
            AIMessage(content="Budget Analysed"),
        ],
        "llm_calls": state["llm_calls"]+1
    }

def hil_agent(state:TravelState):
    """Pause so the traveller can approve the plan, or send it back with feedback"""
    itinerary = state["itinerary"]
    budget_data = state.get("budget_results", "")

    approval_request = (
        "Here is the plan so far. Approve it, or say what you'd like changed.\n\n"
        f"Itinerary:\n{itinerary}\n\n"
        f"Budget:\n{budget_data}"
    )

    logger.info("hil_agent | pausing for approval; resume with resume_travel_agent(thread_id, ...)")

    # Raises GraphInterrupt the first time; on resume it returns whatever Command(resume=...) carried
    answer = interrupt({
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

    return {
        "approval_request": approval_request,
        "approved": approved,
        "human_feedback": feedback,
        "messages": [
            AIMessage(content="Plan approved" if approved else f"Changes requested: {feedback}"),
        ],
    }

def final_response_agent(state:TravelState):
    user_query = state["user_query"]
    flight_data = state["flight_results"]
    hotels_data = state["hotel_results"]
    weather_data = state["weather_results"]
    itinerary = state["itinerary"]
    budget_data = state.get("budget_results", "")
    human_feedback = state.get("human_feedback", "") if not state.get("approved") else ""

    FINAL_RESPONSE_PROMPT = """You are a travel planner. Combine the user's request, flight data, hotel data, weather data, budget analysis and itinerary below into one clear, well-formatted travel plan in Markdown.
Use these sections: Trip Overview, Flights, Hotels, Weather, Day-by-Day Itinerary, Estimated Budget, Travel Tips. Use headings, bullet points and tables where they help.
In the Hotels section, group the hotels by each stay in the itinerary.
In the Weather section, give the current conditions and the daily forecast from the weather data, and say that the forecast covers only the next few days.
In the Estimated Budget section, use the budget analysis when there is one, keeping its figures and its verdict on whether the trip fits the budget.
When the traveller has given feedback, rework the plan to follow it and say at the top what you changed. Their feedback outweighs the itinerary above.
Use only the flights, hotels and weather in the data; don't make any up."""

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
{itinerary}"""

    if human_feedback:
        trip_details += f"""

Traveller's feedback on the plan:
{human_feedback}"""

    response = llm.invoke([
        SystemMessage(content=FINAL_RESPONSE_PROMPT),
        HumanMessage(content=trip_details),
    ])
    final_response = response.text
    logger.info(
        "final_response_agent | wrote %s characters, feedback applied=%s",
        len(final_response),
        bool(human_feedback),
    )

    return {
        "final_response": final_response,
        "messages": [
            AIMessage(content=final_response),
        ],
        "llm_calls": state["llm_calls"]+1
    }

graph = StateGraph(TravelState)

graph.add_node("supervisor_agent", supervisor_agent)
graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("weather_agent",weather_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("budget_agent", budget_agent)
graph.add_node("hil_agent", hil_agent)
graph.add_node("final_response_agent", final_response_agent)


graph.add_edge(START, "supervisor_agent")
graph.add_conditional_edges(
    "supervisor_agent",
    route_after_supervisor,
    [*AGENT_ORDER, "hil_agent", "final_response_agent", END],
)

# Each specialist hands over to the next one the supervisor picked, skipping the rest
for agent_name in AGENT_ORDER:
    graph.add_conditional_edges(
        agent_name,
        partial(route_next, current=agent_name),
        [*AGENT_ORDER, "hil_agent", "final_response_agent"],
    )

graph.add_edge("hil_agent", "final_response_agent")
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

def run_travel_agent(query:str, thread_id:str| None = None):
    if not thread_id:
        thread_id = uuid.uuid4().hex
    
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    initial_state = {
        "messages": [HumanMessage(content=query)],
        "user_query": query,

        # Supervisor + guardrail state
        "guardrail_allowed": False,
        "guardrail_reason": "",
        "selected_agents": [],
        "trip_constraints": {},
        "supervisor_reasoning": "",

        # Specialist results
        "flight_results": "",
        "hotel_results": "",
        "weather_results": "",
        "itinerary": "",
        "budget_results": "",

        # Approval state
        "approval_request": "",
        "approved": False,
        "human_feedback": "",
        "final_response": "",

        "llm_calls": 0,
    }

    logger.info("run | thread=%s query=%r", thread_id, preview(query, 80))
    result = travel_graph.invoke(initial_state, config=config)

    return format_result(thread_id, result)


def resume_travel_agent(thread_id:str, approved:bool = True, feedback:str = ""):
    """Answer the approval question hil_agent asked, and let the run finish."""
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    logger.info("resume | thread=%s approved=%s feedback=%r", thread_id, approved, preview(feedback, 60))
    result = travel_graph.invoke(
        Command(resume={"approved": approved, "feedback": feedback}),
        config=config,
    )

    return format_result(thread_id, result)


def format_result(thread_id:str, result:dict):
    interrupts = result.get("__interrupt__")

    # The run paused at hil_agent; resume it with resume_travel_agent(thread_id, ...)
    if interrupts:
        return {
            "thread_id": thread_id,
            "awaiting_approval": True,
            "approval_request": interrupts[0].value,
            "final_response": "",
            "llm_calls": result.get("llm_calls", 0),
        }

    return {
        "thread_id": thread_id,
        "awaiting_approval": False,
        "approval_request": None,
        "final_response": result.get("final_response", ""),
        "llm_calls": result.get("llm_calls", 0),
    }

