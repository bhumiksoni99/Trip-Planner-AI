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
from mcp_client import tavily_search, get_flights, run_sync, get_weather

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
    weather_results:str
    llm_calls:int   # how many llm calls we make across the workflow

class Route(BaseModel):
    origin_iata: str | None = Field(description="3-letter IATA code of the departure airport")
    destination_iata: str | None = Field(description="3-letter IATA code of the arrival airport")

class Destination(BaseModel):
    city: str | None = Field(description="Main destination city of the trip")

class Stay(BaseModel):
    city: str = Field(description="City the traveller stays overnight in")
    area: str | None = Field(description="Neighbourhood or area to stay in, if the itinerary names one")
    nights: int | None = Field(description="Number of nights spent in this city")

class Stays(BaseModel):
    stays: list[Stay] = Field(description="Every place the traveller stays overnight, in trip order")

route_extractor = llm.with_structured_output(Route)
stay_extractor = llm.with_structured_output(Stays)
destination_extractor = llm.with_structured_output(Destination)

# Caps the hotel searches per trip, one search per stay
MAX_STAYS = 5

# Used when the request names only a destination, e.g. "Plan a Japan trip"
DEFAULT_ORIGIN = os.getenv("DEFAULT_ORIGIN", "DEL")

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

def flight_agent(state:TravelState):
    user_query = state["user_query"]

    route = route_extractor.invoke(
        "Extract the departure and arrival airports from this travel request as 3-letter IATA codes.\n"
        "For a country or city, use its main international airport (e.g. India -> DEL, London -> LHR).\n"
        f"If no departure place is mentioned, use {DEFAULT_ORIGIN}.\n"
        "Use null if the destination can't be determined.\n\n"
        f"Request: {user_query}"
    )

    if route and route.origin_iata and route.destination_iata:
        flight_data = run_sync(get_flights(route.origin_iata, route.destination_iata))
    else:
        flight_data = f"Couldn't work out the departure and arrival airports from: {user_query}"

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
        weather_data = run_sync(get_weather(destination.city))
    else:
        weather_data = f"Couldn't work out the destination city from: {user_query}"

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

    if stays:
        hotel_sections = []
        for stay in stays[:MAX_STAYS]:
            location = f"{stay.area}, {stay.city}" if stay.area else stay.city
            nights = f" for {stay.nights} nights" if stay.nights else ""
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
    weather_data = state["weather_results"]
    itinerary = state["itinerary"]

    FINAL_RESPONSE_PROMPT = """You are a travel planner. Combine the user's request, flight data, hotel data, weather data and itinerary below into one clear, well-formatted travel plan in Markdown.
Use these sections: Trip Overview, Flights, Hotels, Weather, Day-by-Day Itinerary, Estimated Budget, Travel Tips. Use headings, bullet points and tables where they help.
In the Hotels section, group the hotels by each stay in the itinerary.
In the Weather section, give the current conditions and the daily forecast from the weather data, and say that the forecast covers only the next few days.
Use only the flights, hotels and weather in the data; don't make any up."""

    trip_details = f"""User request:
{user_query}

Flight data:
{flight_data}

Hotel data:
{hotels_data}

Weather Data:
{weather_data}

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
graph.add_node("weather_agent",weather_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_response_agent", final_response_agent)


graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent","weather_agent")
graph.add_edge("weather_agent", "itinerary_agent")
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
        "weather_results":"",
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

