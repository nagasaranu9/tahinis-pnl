"""
Google Places API (New) client — fallback review source.

Used when the Google Business Profile API isn't approved yet (GBP access is
allowlisted per-project and slow to grant). Places API (New) needs only a plain
API key (no OAuth, no allowlisting) and returns the place rating, total review
count, and up to 5 recent reviews. That's fewer reviews than GBP (which returns
full history), but it works the same day.

Docs: https://developers.google.com/maps/documentation/places/web-service/place-details
"""
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_PLACES_BASE = "https://places.googleapis.com/v1"


class PlacesAPIError(Exception):
    """Raised when the Places API returns a non-2xx response."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"Places API HTTP {status}: {body[:300]}")


async def search_place(query: str, api_key: str) -> list[dict[str, Any]]:
    """Text Search → place candidates. Each: {id, name, address}."""
    url = f"{_PLACES_BASE}/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, headers=headers, json={"textQuery": query})
    if resp.status_code != 200:
        raise PlacesAPIError(resp.status_code, resp.text)
    out = []
    for p in resp.json().get("places", []):
        out.append({
            "id": p.get("id", ""),
            "name": (p.get("displayName") or {}).get("text"),
            "address": p.get("formattedAddress"),
        })
    return out


async def get_place_reviews(place_id: str, api_key: str) -> dict[str, Any]:
    """Place Details → {rating, user_rating_count, reviews:[...]}.

    place_id is the bare Places ID (e.g. 'ChIJ...'); the resource path is
    'places/{place_id}'. reviews are at most 5 most-relevant, newest-ish."""
    # Accept either a bare id or a 'places/...' resource name.
    pid = place_id.split("/")[-1]
    url = f"{_PLACES_BASE}/places/{pid}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "id,rating,userRatingCount,reviews",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code != 200:
        raise PlacesAPIError(resp.status_code, resp.text)
    data = resp.json()
    reviews = []
    for r in data.get("reviews", []):
        reviews.append({
            "name": r.get("name", ""),  # resource id, unique per review
            "rating": r.get("rating"),
            "text": (r.get("text") or r.get("originalText") or {}).get("text"),
            "author": (r.get("authorAttribution") or {}).get("displayName"),
            "publish_time": r.get("publishTime"),
        })
    return {
        "place_id": pid,
        "rating": data.get("rating"),
        "user_rating_count": data.get("userRatingCount"),
        "reviews": reviews,
    }
