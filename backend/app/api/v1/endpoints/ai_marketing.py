"""AI Marketing — local competitor intelligence.

GET /ai-marketing/competitor-intel?location_id=&radius_km=5

Analyzes restaurants near the tenant's location using real Google Places data,
computes deterministic Threat / Opportunity scores, and (best-effort) layers a
Claude-generated strategy briefing. Tenant-scoped; owners/managers only.
"""
import uuid
from dataclasses import asdict

import structlog
from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import ManagerDep
from app.db.models.location import Location
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse
from app.services.ai.competitor_service import build_intel, synthesize
from app.services.google.places_client import (
    PlacesAPIError,
    get_place_geo,
    search_nearby_restaurants,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/competitor-intel", response_model=APIResponse[dict])
async def competitor_intel(
    user: ManagerDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    radius_km: float = Query(5.0, ge=0.5, le=25.0),
) -> dict:
    api_key = settings.GOOGLE_PLACES_API_KEY
    if not api_key:
        return {
            "data": {"available": False, "reason": "no_api_key"},
            "errors": None,
        }

    # Resolve target location, tenant-scoped.
    stmt = select(Location).where(Location.tenant_id == user.tenant_id)
    if location_id is not None:
        user.require_location_access(location_id)
        stmt = stmt.where(Location.id == location_id)
    elif user.location_id is not None:
        stmt = stmt.where(Location.id == user.location_id)
    loc = (await db.execute(stmt.limit(1))).scalar_one_or_none()

    if not loc:
        return {"data": {"available": False, "reason": "no_location"}, "errors": None}
    if not loc.google_place_id:
        return {
            "data": {"available": False, "reason": "no_place_id", "location_name": loc.name},
            "errors": None,
        }

    try:
        own = await get_place_geo(loc.google_place_id, api_key)
        if own.get("lat") is None or own.get("lng") is None:
            return {"data": {"available": False, "reason": "no_coordinates"}, "errors": None}
        nearby = await search_nearby_restaurants(
            own["lat"], own["lng"], radius_km * 1000.0, api_key
        )
    except PlacesAPIError as exc:
        logger.error("competitor_intel_places_error", status=exc.status, body=exc.body[:200])
        return {"data": {"available": False, "reason": f"places_http_{exc.status}"}, "errors": None}

    intel = build_intel(own, nearby, radius_km)
    intel.location_name = intel.location_name or loc.name
    synthesize(intel)

    data = asdict(intel)
    data["available"] = True
    return {"data": data, "errors": None}
