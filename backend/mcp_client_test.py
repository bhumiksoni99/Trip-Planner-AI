import os
import asyncio
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# The remote server takes the API key as a query parameter
client = MultiServerMCPClient({
    "tavily": {
        "transport": "streamable_http",
        "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}",
    }
})


_tool_cache = {}


async def get_tavily_search_tool(name: str = "tavily_search"):
    if name in _tool_cache:
        return _tool_cache[name]

    tools = await client.get_tools()

    for tool in tools:
        if tool.name == name:
            _tool_cache[name] = tool
            return tool

    available = ", ".join(tool.name for tool in tools)
    raise RuntimeError(f"{name} is not on the MCP server. Available tools: {available}")


async def tavily_search(query: str, max_results: int = 5) -> str:
    tool = await get_tavily_search_tool()
    content = await tool.ainvoke({"query": query, "max_results": max_results})

    # The tool answers with a list of content blocks; the search results are the text ones
    if isinstance(content, str):
        return content
    return "\n".join(block.get("text", "") for block in content if isinstance(block, dict))


async def get_all_tools():
    tools = await client.get_tools()

    print("Tools on the server:")
    for tool in tools:
        print(f"- {tool.name}: {(tool.description or '').splitlines()[0][:90]}")

