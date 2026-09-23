import os
import certifi
import requests
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
BASE_URL = "https://api.aviationstack.com/v1/flights"

# Used when the query names only a destination, e.g. "Plan a Japan trip"
DEFAULT_ORIGIN = os.getenv("DEFAULT_ORIGIN", "DEL")


class Route(BaseModel):
    origin_iata: str | None = Field(description="3-letter IATA code of the departure airport")
    destination_iata: str | None = Field(description="3-letter IATA code of the arrival airport")


# Reads GEMINI_API_KEY from the environment
# A short answer, so a short timeout: a hung request shouldn't hold up the flight search
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", timeout=20)
route_extractor = llm.with_structured_output(Route)


def get_route(query: str) -> Route:
    prompt = (
        "Extract the departure and arrival airports from this travel request as 3-letter IATA codes.\n"
        "For a country or city, use its main international airport (e.g. India -> DEL, London -> LHR).\n"
        "If the trip covers several places or countries, use the airport the traveller would fly into first.\n"
        f"If no departure place is mentioned, use {DEFAULT_ORIGIN}.\n"
        "Use null only if the request names no destination at all.\n\n"
        f"Request: {query}"
    )
    return route_extractor.invoke(prompt)


def format_flight(flight: dict):
    airline = flight.get("airline", {}).get("name") or "Unknown airline"
    flight_number = flight.get("flight", {}).get("iata") or "Unknown flight number"
    status = flight.get("flight_status") or "Unknown"

    dep = flight.get("departure", {}) or {}
    arr = flight.get("arrival", {}) or {}

    dep_airport = dep.get("airport") or "Unknown departure airport"
    dep_iata = dep.get("iata") or "Unknown"
    dep_terminal = dep.get("terminal") or "N/A"
    dep_gate = dep.get("gate") or "N/A"
    dep_scheduled = dep.get("scheduled") or "Unknown"
    dep_delay = dep.get("delay")
    dep_delay_text = f"{dep_delay} minutes" if dep_delay is not None else "N/A"

    arr_airport = arr.get("airport") or "Unknown arrival airport"
    arr_iata = arr.get("iata") or "Unknown"
    arr_terminal = arr.get("terminal") or "N/A"
    arr_gate = arr.get("gate") or "N/A"
    arr_scheduled = arr.get("scheduled") or "Unknown"
    arr_delay = arr.get("delay")
    arr_delay_text = f"{arr_delay} minutes" if arr_delay is not None else "N/A"

    return f"""
Airline: {airline}
Flight: {flight_number}
Status: {status}

Departure:
- Airport: {dep_airport}
- IATA: {dep_iata}
- Terminal: {dep_terminal}
- Gate: {dep_gate}
- Scheduled: {dep_scheduled}
- Delay: {dep_delay_text}

Arrival:
- Airport: {arr_airport}
- IATA: {arr_iata}
- Terminal: {arr_terminal}
- Gate: {arr_gate}
- Scheduled: {arr_scheduled}
- Delay: {arr_delay_text}
""".strip()


MISSING_KEY = (
    "Flight API error: AVIATIONSTACK_API_KEY is missing.\n"
    "Please add this in your .env file:\n"
    "AVIATIONSTACK_API_KEY=your_api_key_here"
)


def search_flights(query: str, limit: int = 10):
    """Live flights for a free-text request, working out the airports with a model call first.
    When the airport codes are already known, flights_between skips that call."""
    if not API_KEY:
        return MISSING_KEY

    route = get_route(query)
    dep_iata = route.origin_iata.upper() if route and route.origin_iata else None
    arr_iata = route.destination_iata.upper() if route and route.destination_iata else None
    return flights_between(dep_iata, arr_iata, limit)


def flights_between(dep_iata: str | None, arr_iata: str | None, limit: int = 10):
    """Live flights between two airports, by their 3-letter IATA codes. No model call."""
    if not API_KEY:
        return MISSING_KEY

    params = {
        "access_key": API_KEY,
        "limit": min(limit, 100),
    }

    if dep_iata:
        params["dep_iata"] = dep_iata

    if arr_iata:
        params["arr_iata"] = arr_iata

    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
        data = response.json()
    except requests.exceptions.RequestException as e:
        return f"Flight API request failed: {e}"
    except ValueError:
        return "Flight API returned invalid JSON."

    if "error" in data:
        error = data["error"]
        return (
            "Flight API error:\n"
            f"Code: {error.get('code', 'Unknown')}\n"
            f"Message: {error.get('message', 'Unknown error')}"
        )

    flight_data = data.get("data", [])

    if not flight_data:
        route_text = ""

        if dep_iata and arr_iata:
            route_text = f" for route {dep_iata} to {arr_iata}"
        elif dep_iata:
            route_text = f" from {dep_iata}"
        elif arr_iata:
            route_text = f" to {arr_iata}"

        return (
            f"No live flight data found{route_text}.\n\n"
            "Note: AviationStack provides live/status flight data, not ticket prices. "
            "For actual fare prices, use a flight-pricing API such as Amadeus."
        )

    route_info = "Global live flights"

    if dep_iata and arr_iata:
        route_info = f"Live flights from {dep_iata} to {arr_iata}"
    elif dep_iata:
        route_info = f"Live flights from {dep_iata}"
    elif arr_iata:
        route_info = f"Live flights to {arr_iata}"

    formatted_flights = [format_flight(flight) for flight in flight_data[:limit]]

    return f"{route_info}\n\n" + "\n\n---\n\n".join(formatted_flights)


if __name__ == "__main__":
    print(search_flights("Plan a trip from India to London"))
