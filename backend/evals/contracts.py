"""Checks our parsing against the shapes the outside APIs actually return.

The graph evals fake every API, so they agree with our code by construction: wiring.py fakes
destination_photo outright, and a change that made Tavily answer in a different shape passed all of
them while quietly returning no photo at all. This is the check that would have caught it.

Run from backend/:

    python -m evals.contracts            # parse the recorded shapes, no network
    python -m evals.contracts --live     # also ask Tavily, and fail if its shape moved

The recorded responses below are trimmed copies of real answers. --live is what keeps them honest:
if Tavily starts answering differently, that run fails and the recordings get updated.
"""
import argparse
import os
import sys
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import place_preview  # noqa: E402  (after load_dotenv, so it sees the Tavily key)

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{f'  ({detail})' if detail else ''}")
    if not ok:
        failures.append(label)


# Recorded 2026-09-24 from api.tavily.com/search. Captions on gives an object per image;
# captions off gives a bare URL string, which is the difference that broke the header photo
CAPTIONED = {
    "images": [
        {"url": "https://example.com/kyoto-1.jpg", "title": "Kyoto", "description": "A temple at dusk"},
        {"url": "https://example.com/kyoto-2.jpg", "title": "Gion", "description": "A lantern-lit lane"},
    ],
    "results": [{"title": "Kyoto guide", "url": "https://example.com/guide", "content": "text"}],
}

PLAIN = {
    "images": ["https://example.com/kyoto-1.jpg", "https://example.com/kyoto-2.jpg"],
    "results": [{"title": "Kyoto guide", "url": "https://example.com/guide", "content": "text"}],
}


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def first(images):
    """The first image, or an empty one. A check that finds nothing should read FAIL, not crash and
    take the rest of the run with it — which is exactly what it did the first time it caught a bug."""
    return images[0] if images else {}


def parsed(payload, **kwargs):
    """What search_place makes of a given Tavily answer, with the cache bypassed"""
    place_preview._cache.clear()
    with patch.object(place_preview.requests, "post", return_value=FakeResponse(payload)):
        return place_preview.search_place("kyoto scenic view", **kwargs)


print("\nTavily's two image shapes")
captioned = parsed(CAPTIONED)
check("captions on: both images come through", len(captioned["images"]) == 2,
      f"{len(captioned['images'])} images")
check("captions on: the caption is kept for the preview panel's alt text",
      first(captioned["images"]).get("description") == "A temple at dusk")

plain = parsed(PLAIN, describe_images=False)
check("captions off: bare URL strings still come through", len(plain["images"]) == 2,
      f"{len(plain['images'])} images")
check("captions off: each one is a usable url",
      bool(plain["images"]) and all(image["url"].startswith("https://") for image in plain["images"]))
check("captions off: the caption is simply empty", first(plain["images"]).get("description") == "")

print("\nJunk in the image list is dropped, not crashed on")
messy = parsed({"images": ["", "   ", None, {"description": "no url"}, {"url": "https://example.com/ok.jpg"}], "results": []})
check("only the usable one survives", [i["url"] for i in messy["images"]] == ["https://example.com/ok.jpg"],
      str([i["url"] for i in messy["images"]]))

print("\nThe cache tells the two shapes apart")
place_preview._cache.clear()
with patch.object(place_preview.requests, "post", return_value=FakeResponse(CAPTIONED)):
    place_preview.search_place("kyoto scenic view")
with patch.object(place_preview.requests, "post", return_value=FakeResponse(PLAIN)):
    uncaptioned = place_preview.search_place("kyoto scenic view", describe_images=False)
check("a caption-less result is never served to the preview panel",
      first(uncaptioned["images"]).get("description") == "",
      "would have served the captioned copy from cache")

if "--live" in sys.argv:
    print("\nAgainst the real Tavily")
    if not os.getenv("TAVILY_API_KEY"):
        check("TAVILY_API_KEY is set", False)
    else:
        place_preview._cache.clear()
        live_captioned = place_preview.search_place("Kyoto skyline landmark scenic view", max_results=3)
        live_plain = place_preview.search_place("Kyoto skyline landmark scenic view", max_results=3,
                                                describe_images=False)
        check("captions on still returns images", len(live_captioned["images"]) > 0,
              f"{len(live_captioned['images'])} images")
        check("captions off still returns images", len(live_plain["images"]) > 0,
              f"{len(live_plain['images'])} images — the header photo depends on this")
        check("captions on still carries captions",
              any(image["description"] for image in live_captioned["images"]))

print(f"\n{f'{len(failures)} FAILED: {failures}' if failures else 'ALL PASSED'}")
sys.exit(1 if failures else 0)
