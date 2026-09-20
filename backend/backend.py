import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import TypedDict, Annotated
import uuid
import operator
import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, AnyMessage
from tools.tavily_tool import search_tavily
from tools.flight_tool import search_flights

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", api_key=GEMINI_API_KEY)

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage],operator.add]
    user_query:str
    flight_results:str
    hotel_results:str
    itinerary:str
    final_response:str
    llm_calls:int   # how many llm calls we make across the workflow

class Stay(BaseModel):
    city: str = Field(description="City the traveller stays overnight in")
    area: str | None = Field(description="Neighbourhood or area to stay in, if the itinerary names one")
    nights: int | None = Field(description="Number of nights spent in this city")

class Stays(BaseModel):
    stays: list[Stay] = Field(description="Every place the traveller stays overnight, in trip order")

stay_extractor = llm.with_structured_output(Stays)

# Caps the hotel searches per trip, one search per stay
MAX_STAYS = 5

def get_database_connection():
    database_url = os.getenv("POSTGRES_DB")
    if not database_url:
        raise ValueError("POSTGRES_DB is missing.")
    return database_url

def flight_agent(state:TravelState):
    user_query = state["user_query"]
    flight_data = search_flights(user_query)

    return {
        "flight_results": flight_data,
        "messages": [
            AIMessage(content="Flight Results Fetched"),
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

    if stays:
        hotel_sections = []
        for stay in stays[:MAX_STAYS]:
            location = f"{stay.area}, {stay.city}" if stay.area else stay.city
            nights = f" for {stay.nights} nights" if stay.nights else ""
            search_results = search_tavily(f"best hotels in {location}{nights}")
            hotel_sections.append(f"Hotels in {location}{nights}:\n{search_results}")
        hotels_data = "\n\n".join(hotel_sections)
    else:
        # Couldn't read any stays from the itinerary, so search on the original request
        hotels_data = search_tavily(f"best hotels for: {user_query}")

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

    ITINERARY_PROMPT = """You are a travel planner. Using the user's request and the flight data below, write a day-by-day travel itinerary in Markdown.
For each city, say which area to stay in and for how many nights, but don't name specific hotels; those are searched separately.
Use only the flights in the data; don't make any up. If the user didn't give trip length or budget, pick sensible defaults and say so."""


    trip_details = f"""User request:
{user_query}

Flight data:
{flight_data}"""

    response = llm.invoke([
        SystemMessage(content=ITINERARY_PROMPT),
        HumanMessage(content=trip_details),
    ])
    itinerary = response.text

    return {
        "itinerary": itinerary,
        "messages": [
            AIMessage(content=itinerary),
        ],
        "llm_calls": state["llm_calls"]+1
    }

def final_response_agent(state:TravelState):
    user_query = state["user_query"]
    flight_data = state["flight_results"]
    hotels_data = state["hotel_results"]
    itinerary = state["itinerary"]

    FINAL_RESPONSE_PROMPT = """You are a travel planner. Combine the user's request, flight data, hotel data and itinerary below into one clear, well-formatted travel plan in Markdown.
Use these sections: Trip Overview, Flights, Hotels, Day-by-Day Itinerary, Estimated Budget, Travel Tips. Use headings, bullet points and tables where they help.
In the Hotels section, group the hotels by each stay in the itinerary.
Use only the flights and hotels in the data; don't make any up."""

    trip_details = f"""User request:
{user_query}

Flight data:
{flight_data}

Hotel data:
{hotels_data}

Itinerary:
{itinerary}"""

    response = llm.invoke([
        SystemMessage(content=FINAL_RESPONSE_PROMPT),
        HumanMessage(content=trip_details),
    ])
    final_response = response.text

    return {
        "final_response": final_response,
        "messages": [
            AIMessage(content=final_response),
        ],
        "llm_calls": state["llm_calls"]+1
    }

graph = StateGraph(TravelState)

graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_response_agent", final_response_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "hotel_agent")
graph.add_edge("hotel_agent", "final_response_agent")
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
        "flight_results": "",
        "hotel_results": "",
        "itinerary": "",
        "final_response": "",
        "llm_calls": 0,
    }

    result = travel_graph.invoke(initial_state, config=config)

    return {
        "thread_id": thread_id,
        "final_response": result["final_response"],
        "llm_calls": result["llm_calls"],
    }

