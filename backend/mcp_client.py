import os
import sys
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATIONSTACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

logger = logging.getLogger("travel.mcp")

# Absolute path, so the server starts whatever directory the app runs from
WEATHER_SERVER = str(Path(__file__).parent / "custom_weather_mcp.py")


# The remote server takes the API key as a query parameter
client = MultiServerMCPClient({
    "tavily": {
        "transport": "streamable_http",
        "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}",
    },
    # Flights come from tools/flight_tool.py instead: AviationStack's free plan only serves
    # /v1/flights, so the MCP server's route tools return nothing. It also needed `uvx`, which
    # isn't in the deployment image, and one failing server stopped the other two loading.
    # Our own server, run by the same Python as this app
    "weather": {
        "transport": "stdio",
        "command": sys.executable,
        "args": [WEATHER_SERVER],
        "env": {"OPENWEATHER_API_KEY": OPENWEATHER_API_KEY},
    },
})


async def get_all_tools():
    tools = await client.get_tools()

    print("Tools on the server:")
    for tool in tools:
        print(f"- {tool.name}: {(tool.description or '').splitlines()[0][:90]}")


search_tool = None
weather_tools = {}


async def load_mcp_tools():
    """Fetch every server's tools once and keep them; returns (search_tool, weather_tools)."""
    global search_tool, weather_tools

    if search_tool is not None and weather_tools:
        return search_tool, weather_tools

    tavily_tools = await client.get_tools(server_name="tavily")
    weather = await client.get_tools(server_name="weather")

    search = next((tool for tool in tavily_tools if tool.name == "tavily_search"), None)
    if search is None:
        available = ", ".join(tool.name for tool in tavily_tools)
        raise RuntimeError(f"tavily_search is not on the Tavily MCP server. Available tools: {available}")

    search_tool = search
    weather_tools = {tool.name: tool for tool in weather}
    logger.info("loaded tools | tavily=%s weather=%s", len(tavily_tools), len(weather_tools))
    return search_tool, weather_tools


# For calling from sync code, such as the LangGraph nodes in agent.py
def initialize_mcp():
    return run_sync(load_mcp_tools())


def run_sync(coro):
    """Run an async call from sync code, such as the LangGraph nodes in agent.py."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # A loop is already running (Jupyter, FastAPI's async endpoints), so give the call its own thread
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def tavily_search(query: str, max_results: int = 5) -> str:
    tool, _ = await load_mcp_tools()
    logger.info("tavily_search | query=%r max_results=%s", query, max_results)
    content = await tool.ainvoke({"query": query, "max_results": max_results})

    # The tool answers with a list of content blocks; the search results are the text ones
    if isinstance(content, str):
        return content
    return "\n".join(block.get("text", "") for block in content if isinstance(block, dict))


async def get_weather(city: str, forecast_days: int = 5) -> str:
    """Current weather and the days ahead for a city, e.g. get_weather("Barcelona")."""
    _, tools = await load_mcp_tools()

    logger.info("weather | city=%s forecast_days=%s", city, forecast_days)
    current = await tools["get_weather"].ainvoke({"city": city})
    forecast = await tools["get_forecast"].ainvoke({"city": city, "days": forecast_days})

    sections = []
    for content in (current, forecast):
        if isinstance(content, str):
            sections.append(content)
        else:
            sections.append("\n".join(block.get("text", "") for block in content if isinstance(block, dict)))

    return "\n\n".join(sections)