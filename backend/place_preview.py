"""Photos and links for a place, shown in the app's bottom sheet.

This calls Tavily's REST API rather than its MCP server: the MCP adapter opens a new
session per call, which costs about 6 seconds, while the same search over REST takes ~1s.
The agents still use MCP; this is only for the preview panel.
"""

import os
import logging
from collections import OrderedDict

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("travel.place")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Keeps reopened links instant; the newest CACHE_SIZE queries are kept
CACHE_SIZE = 200
_cache: OrderedDict[str, dict] = OrderedDict()


def search_place(query: str, max_results: int = 5) -> dict:
    """Returns {"images": [...], "results": [...]} for a place, cached per query."""
    key = query.strip().lower()

    if key in _cache:
        _cache.move_to_end(key)
        logger.info("place_preview | cached %r", query)
        return _cache[key]

    if not TAVILY_API_KEY:
        return {"images": [], "results": [], "error": "TAVILY_API_KEY is missing from .env."}

    try:
        response = requests.post(
            TAVILY_SEARCH_URL,
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "include_images": True,
                "include_image_descriptions": True,
            },
            timeout=20,
        )
        data = response.json()
    except requests.exceptions.RequestException as e:
        logger.warning("place_preview | request failed: %s", e)
        return {"images": [], "results": [], "error": "Couldn't reach the search service."}
    except ValueError:
        return {"images": [], "results": [], "error": "The search service returned an invalid response."}

    if response.status_code != 200:
        logger.warning("place_preview | %s: %s", response.status_code, str(data)[:120])
        return {"images": [], "results": [], "error": "The search service couldn't look this one up."}

    preview = {
        "images": [
            {"url": image["url"], "description": image.get("description", "")}
            for image in data.get("images", [])
            if isinstance(image, dict) and image.get("url")
        ],
        "results": [
            {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "content": (result.get("content") or "")[:400],
            }
            for result in data.get("results", [])
        ],
    }

    _cache[key] = preview
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)

    logger.info("place_preview | %r: %s images, %s results", query, len(preview["images"]), len(preview["results"]))
    return preview
