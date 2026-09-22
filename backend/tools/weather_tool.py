"""Current weather and a short forecast from OpenWeather.

weather_agent calls these directly. custom_weather_mcp.py exposes the same two functions as an MCP
server, for any MCP client. The agent doesn't go through that server because every stdio MCP call
starts a new Python subprocess, which cost up to ~6s per call when the server was cold.
"""
import os
from concurrent.futures import ThreadPoolExecutor

import requests
from dotenv import load_dotenv

load_dotenv()

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")


def get_weather(city: str) -> str:
    """Current weather for a city, e.g. get_weather("Barcelona")."""
    if not OPENWEATHER_API_KEY:
        return "Weather API error: OPENWEATHER_API_KEY is missing from .env."

    try:
        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"},
            timeout=30,
        )
        data = response.json()
    except requests.exceptions.RequestException as e:
        return f"Weather API request failed: {e}"
    except ValueError:
        return "Weather API returned invalid JSON."

    if response.status_code != 200:
        return f"Weather API error: {data.get('message', 'Unknown error')}"

    main = data.get("main", {})
    wind = data.get("wind", {})
    conditions = data["weather"][0]["description"] if data.get("weather") else "unknown"
    country = data.get("sys", {}).get("country", "")

    return (
        f"Weather in {data.get('name', city)}, {country}:\n"
        f"- Conditions: {conditions}\n"
        f"- Temperature: {main.get('temp')}°C (feels like {main.get('feels_like')}°C)\n"
        f"- Range: {main.get('temp_min')}°C to {main.get('temp_max')}°C\n"
        f"- Humidity: {main.get('humidity')}%\n"
        f"- Wind: {wind.get('speed', 'N/A')} m/s"
    )


def get_forecast(city: str, days: int = 5) -> str:
    """Daily weather forecast for a city, up to 5 days ahead, e.g. get_forecast("Barcelona")."""
    if not OPENWEATHER_API_KEY:
        return "Weather API error: OPENWEATHER_API_KEY is missing from .env."

    try:
        response = requests.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"},
            timeout=30,
        )
        data = response.json()
    except requests.exceptions.RequestException as e:
        return f"Weather API request failed: {e}"
    except ValueError:
        return "Weather API returned invalid JSON."

    if response.status_code != 200:
        return f"Weather API error: {data.get('message', 'Unknown error')}"

    # The forecast comes in 3-hour steps, so group them by date
    by_day = {}
    for entry in data.get("list", []):
        date = entry.get("dt_txt", "")[:10]
        if not date:
            continue

        temps, conditions = by_day.setdefault(date, ([], []))
        temps.append(entry.get("main", {}).get("temp"))
        if entry.get("weather"):
            conditions.append(entry["weather"][0]["description"])

    if not by_day:
        return f"No forecast data found for {city}."

    city_name = data.get("city", {}).get("name", city)
    country = data.get("city", {}).get("country", "")

    lines = [f"{days}-day forecast for {city_name}, {country}:"]
    for date, (temps, conditions) in list(by_day.items())[:days]:
        temps = [temp for temp in temps if temp is not None]
        if not temps:
            continue

        # The condition that shows up most often that day
        common = max(set(conditions), key=conditions.count) if conditions else "unknown"
        lines.append(f"- {date}: {min(temps):.0f}°C to {max(temps):.0f}°C, {common}")

    return "\n".join(lines)


def weather_report(city: str, days: int = 5) -> str:
    """Current conditions and the forecast together, as one block for the planning prompts.
    They're separate requests that don't depend on each other, so both run at once."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        current = pool.submit(get_weather, city)
        forecast = pool.submit(get_forecast, city, days)
        return f"{current.result()}\n\n{forecast.result()}"
