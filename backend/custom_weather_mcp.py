from mcp.server.fastmcp import FastMCP

from tools.weather_tool import get_forecast, get_weather

mcp = FastMCP("Weather MCP server")

# The agents call these two functions directly (see tools/weather_tool.py for why);
# this server exposes the same ones to any MCP client
mcp.tool()(get_weather)
mcp.tool()(get_forecast)


if __name__ == "__main__":
    mcp.run()
