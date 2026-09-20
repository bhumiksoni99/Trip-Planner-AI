from tavily import TavilyClient
import os
from dotenv import load_dotenv

load_dotenv()

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

SNIPPET_LENGTH = 300

def search_tavily(query: str) -> str:
    response = tavily_client.search(query, max_results=5)
    results = []
    for i, result in enumerate(response.get("results", []), start=1):
        title = result.get("title", "")
        url = result.get("url", "")
        snippet = (result.get("content") or "")[:SNIPPET_LENGTH]
        results.append(f"[{i}] {title}\nURL: {url}\nSnippet: {snippet}")
    return "\n\n".join(results)