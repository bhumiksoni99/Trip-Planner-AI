"""Photos and links for a place, shown in the app's bottom sheet.

This calls Tavily's REST API rather than its MCP server: the MCP adapter opens a new
session per call, which costs about 6 seconds, while the same search over REST takes ~1s.
The agents still use MCP; this is only for the preview panel.
"""

import os
import logging
import threading
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

# The hotel agent searches from several threads at once. Reordering or trimming the cache while
# another thread does the same can corrupt it, so every cache access holds this. The search
# itself runs outside the lock, so searches never wait on each other.
_cache_lock = threading.Lock()


def search_place(query: str, max_results: int = 5, include_images: bool = True) -> dict:
    """Returns {"images": [...], "results": [...]} for a place, cached per query.

    Pass include_images=False when only the links are needed, as the hotel searches do. Tavily finds
    and describes the images on its side, which makes the search noticeably slower, and the preview
    panel fetches its own when a hotel is opened."""
    # The flag is part of the key, so an image-less result is never served to the preview panel
    key = f"{query.strip().lower()}|images={include_images}"

    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)

    if cached is not None:
        logger.info("place_preview | cached %r", query)
        return cached

    if not TAVILY_API_KEY:
        return {"images": [], "results": [], "error": "TAVILY_API_KEY is missing from .env."}

    try:
        response = requests.post(
            TAVILY_SEARCH_URL,
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "include_images": include_images,
                "include_image_descriptions": include_images,
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

    with _cache_lock:
        _cache[key] = preview
        if len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)

    logger.info("place_preview | %r: %s images, %s results", query, len(preview["images"]), len(preview["results"]))
    return preview
