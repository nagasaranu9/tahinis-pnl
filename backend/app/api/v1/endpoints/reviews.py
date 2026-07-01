"""
Google Business Profile Reviews endpoints.

OAuth flow:
  GET  /reviews/auth-url      → OAuth consent URL
  GET  /reviews/callback      → exchange code, store tokens, redirect
  GET  /reviews/status        → list connected configs
  GET  /reviews/summary       → aggregate rating + star breakdown + recent reviews
  GET  /reviews/list          → paginated reviews
  POST /reviews/sync          → manual sync trigger
  DELETE /reviews/disconnect  → deactivate config
"""
import secrets
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from app.core.deps import CurrentUserDep, ManagerDep, OwnerDep
from app.core.exceptions import NotFoundError
from app.core.security import decrypt_value, encrypt_value
from app.db.models.integration import IntegrationCredential
from app.db.repositories.reviews_repo import ReviewsRepository
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse, PaginatedMeta, PaginatedResponse
from app.schemas.google_reviews import (
    GoogleReviewConfigResponse,
    GoogleReviewLocationOverride,
    GoogleReviewResponse,
    ReviewsSummaryResponse,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


def _frontend_url(path: str) -> str:
    from app.core.config import settings
    return f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}{path}"


def _api_callback_url() -> str:
    from app.core.config import settings
    return f"{getattr(settings, 'API_BASE_URL', 'http://localhost:8000')}/api/v1/reviews/callback"


@router.get("/auth-url", response_model=APIResponse[dict])
async def reviews_auth_url(user: OwnerDep) -> dict:
    from app.services.google.reviews_client import build_reviews_auth_url
    state = f"{user.tenant_id}:{user.user_id}:{secrets.token_urlsafe(16)}"
    url = build_reviews_auth_url(redirect_uri=_api_callback_url(), state=state)
    return {"data": {"url": url}, "errors": None}


@router.get("/callback")
async def reviews_callback(code: str, state: str, db: AsyncSessionDep):
    from app.services.google.reviews_client import exchange_reviews_code

    try:
        parts = state.split(":")
        tenant_id = uuid.UUID(parts[0])

        token_data = await exchange_reviews_code(code, _api_callback_url())
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")

        # Account/location are no longer auto-discovered here — that lookup hits Google's
        # daily-quota-limited accounts/locations API and blocks indefinitely on 429.
        # The owner sets account_name/location_name via PATCH /reviews/config/location
        # (values copied from the business.google.com dashboard URL), and sync just uses
        # those directly. See set_review_location below.
        account_name = None
        location_name = None
        place_id = "pending"

        cred = IntegrationCredential(
            tenant_id=tenant_id,
            provider="google_business",
            access_token_encrypted=encrypt_value(access_token),
            refresh_token_encrypted=encrypt_value(refresh_token),
        )
        db.add(cred)
        await db.flush()

        # Use first location in DB for this tenant
        from sqlalchemy import select
        from app.db.models.location import Location
        loc_row = (await db.execute(
            select(Location).where(Location.tenant_id == tenant_id).limit(1)
        )).scalar_one_or_none()

        if loc_row:
            repo = ReviewsRepository(db)
            await repo.upsert_config(
                tenant_id=tenant_id,
                location_id=loc_row.id,
                place_id=place_id,
                account_name=account_name,
                location_name=location_name,
                integration_credential_id=cred.id,
            )

        await db.commit()
        logger.info("google_reviews_connected", tenant_id=str(tenant_id), account=account_name)

    except Exception as e:
        logger.error("google_reviews_callback_failed", error=str(e))
        return RedirectResponse(_frontend_url("/reviews?error=google_reviews_failed"))

    return RedirectResponse(_frontend_url("/reviews?connected=google"))


@router.get("/status", response_model=APIResponse[list[GoogleReviewConfigResponse]])
async def reviews_status(user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    repo = ReviewsRepository(db)
    configs = await repo.list_configs(user.tenant_id)
    return {"data": [GoogleReviewConfigResponse.model_validate(c) for c in configs], "errors": None}


@router.get("/summary", response_model=APIResponse[ReviewsSummaryResponse])
async def reviews_summary(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    date_from: str | None = Query(None, description="YYYY-MM-DD"),
    date_to: str | None = Query(None, description="YYYY-MM-DD"),
) -> dict:
    repo = ReviewsRepository(db)
    summary = await repo.get_summary(user.tenant_id, location_id, date_from=date_from, date_to=date_to)
    recent, _ = await repo.list_reviews(user.tenant_id, location_id, page=1, limit=5, date_from=date_from, date_to=date_to)
    return {
        "data": ReviewsSummaryResponse(
            **summary,
            recent_reviews=[GoogleReviewResponse.model_validate(r) for r in recent],
        ),
        "errors": None,
    }


@router.get("/list", response_model=PaginatedResponse[GoogleReviewResponse])
async def reviews_list(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    date_from: str | None = Query(None, description="YYYY-MM-DD"),
    date_to: str | None = Query(None, description="YYYY-MM-DD"),
) -> dict:
    repo = ReviewsRepository(db)
    rows, total = await repo.list_reviews(user.tenant_id, location_id, page=page, limit=limit, date_from=date_from, date_to=date_to)
    return {
        "data": [GoogleReviewResponse.model_validate(r) for r in rows],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }


@router.post("/sync", response_model=APIResponse[dict])
async def reviews_sync(
    user: ManagerDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    from app.workers.tasks.reviews_sync import sync_reviews

    repo = ReviewsRepository(db)
    configs = await repo.list_configs(user.tenant_id)
    if not configs:
        return {"data": {"queued": 0}, "errors": None}

    targets = [c for c in configs if not location_id or c.location_id == location_id]
    for cfg in targets:
        sync_reviews.apply_async(
            kwargs={"tenant_id": str(user.tenant_id), "location_id": str(cfg.location_id)},
            queue="sync",
        )

    return {"data": {"queued": len(targets)}, "errors": None}


@router.post("/discover-location", response_model=APIResponse[dict])
async def discover_review_location(
    user: OwnerDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """One-time auto-discovery of the Google Business account/location names.

    The owner usually can't get the GBP account id from public Search/Maps URLs —
    it only comes from the My Business Account Management API, which needs the
    OAuth token granted at connect. This calls accounts.list + locations.list once
    (quota-gated, so it's a manual button, not part of sync), auto-pins the result
    on the config, and returns the candidates for transparency."""
    from sqlalchemy import select
    from app.services.google.reviews_client import GoogleAPIRateLimitError, GoogleReviewsClient

    repo = ReviewsRepository(db)
    configs = await repo.list_configs(user.tenant_id)
    config = next(
        (c for c in configs if (not location_id or c.location_id == location_id) and c.is_active),
        None,
    )
    if config is None:
        raise NotFoundError("Google reviews not connected")

    cred_row = (await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.tenant_id == user.tenant_id,
            IntegrationCredential.provider == "google_business",
        ).order_by(IntegrationCredential.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if cred_row is None:
        raise NotFoundError("No Google credential on file — reconnect Google")

    access_token = decrypt_value(cred_row.access_token_encrypted)
    refresh_token = decrypt_value(cred_row.refresh_token_encrypted)

    try:
        async with GoogleReviewsClient(access_token, refresh_token) as client:
            accounts = await client.get_accounts()
            if not accounts:
                return {"data": {"error": "no_accounts", "accounts": []}, "errors": None}

            # Prefer an account that actually has locations; collect candidates.
            chosen_account = None
            chosen_location = None
            all_locations: list[dict] = []
            for acct in accounts:
                acct_name = acct.get("name", "")
                locs = await client.get_locations(acct_name)
                for loc in locs:
                    all_locations.append({
                        "account_name": acct_name,
                        "location_name": loc.get("name", ""),
                        "title": loc.get("title"),
                    })
                if locs and chosen_location is None:
                    chosen_account = acct_name
                    # Match on the business title when possible, else first location.
                    match = next(
                        (l for l in locs if "tahini" in (l.get("title") or "").lower()),
                        locs[0],
                    )
                    chosen_location = match.get("name", "")
    except GoogleAPIRateLimitError:
        return {"data": {"error": "Google API daily quota hit — try again later, or paste IDs manually"}, "errors": None}
    except Exception as exc:  # surface Google's real cause instead of a blank 500
        import httpx
        detail = str(exc)
        status = None
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            body = exc.response.text[:300]
            detail = f"Google returned HTTP {status}: {body}"
        logger.error("google_reviews_discover_failed", error=detail, status=status)
        hint = ""
        if status == 403:
            hint = (
                " — likely the Business Profile APIs aren’t enabled for this Google "
                "Cloud project, or the project hasn’t been granted GBP API access. "
                "Enable: My Business Account Management API + Business Information API + "
                "Google My Business API, and request GBP API access."
            )
        return {"data": {"error": detail + hint}, "errors": None}

    if not chosen_account or not chosen_location:
        return {"data": {"error": "no_locations", "accounts": [a.get("name") for a in accounts]}, "errors": None}

    await repo.set_manual_location(
        tenant_id=user.tenant_id,
        location_id=config.location_id,
        account_name=chosen_account,
        location_name=chosen_location,
    )
    await db.commit()
    logger.info(
        "google_reviews_location_discovered",
        tenant_id=str(user.tenant_id),
        account=chosen_account,
        location=chosen_location,
    )
    return {
        "data": {
            "account_name": chosen_account,
            "location_name": chosen_location,
            "candidates": all_locations,
        },
        "errors": None,
    }


def _parse_iso(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


@router.post("/places-sync", response_model=APIResponse[dict])
async def reviews_places_sync(
    user: ManagerDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    place_id: str | None = Query(None, description="Google Place ID (ChIJ...). Optional if a query is given or already stored."),
    query: str | None = Query(None, description="Business search text, e.g. 'Tahini's Shawarma Church St Toronto'"),
) -> dict:
    """Fallback review sync via Places API (New) — no GBP allowlisting needed.

    Imports rating + total count + up to 5 recent reviews into the same tables the
    Reviews tab/dashboard already read, so it lights up immediately while the full
    Business Profile API access request is pending."""
    from app.core.config import settings
    from app.services.google.places_client import (
        PlacesAPIError,
        get_place_reviews,
        search_place,
    )

    api_key = settings.GOOGLE_PLACES_API_KEY
    if not api_key:
        raise NotFoundError("GOOGLE_PLACES_API_KEY not configured on the server")

    repo = ReviewsRepository(db)
    configs = await repo.list_configs(user.tenant_id)
    config = next(
        (c for c in configs if (not location_id or c.location_id == location_id) and c.is_active),
        None,
    )
    if config is None:
        raise NotFoundError("Google reviews not connected for this location")

    # Resolve the Place ID: explicit param > text search > already stored.
    resolved = place_id or None
    if not resolved and query:
        try:
            candidates = await search_place(query, api_key)
        except PlacesAPIError as exc:
            return {"data": {"error": f"Place search failed (HTTP {exc.status})", "candidates": []}, "errors": None}
        if not candidates:
            return {"data": {"error": "no_place_found", "candidates": []}, "errors": None}
        resolved = candidates[0]["id"]
    if not resolved and config.place_id and config.place_id.startswith(("ChIJ", "places/")):
        resolved = config.place_id
    if not resolved:
        return {"data": {"error": "need_place_id_or_query"}, "errors": None}

    try:
        details = await get_place_reviews(resolved, api_key)
    except PlacesAPIError as exc:
        logger.error("places_sync_failed", status=exc.status, body=exc.body[:300])
        hint = " — enable 'Places API (New)' and check the API key/billing." if exc.status in (403, 400) else ""
        return {"data": {"error": f"Places API HTTP {exc.status}{hint}"}, "errors": None}

    imported = 0
    for r in details["reviews"]:
        if not r.get("name"):
            continue
        rating = int(r["rating"]) if r.get("rating") is not None else None
        published = _parse_iso(r.get("publish_time"))
        await repo.upsert_review(
            tenant_id=user.tenant_id,
            location_id=config.location_id,
            review_id=r["name"],
            author_name=r.get("author"),
            rating=rating,
            comment=r.get("text"),
            published_at=published,
            update_time=published,
            reply_comment=None,
            reply_update_time=None,
        )
        imported += 1

    # Persist the TRUE aggregate (rating + full count) as a snapshot so the
    # summary/dashboard headline shows 4.8 / 1995, not the 5-review sample avg.
    sampled_stars: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in details["reviews"]:
        rv = r.get("rating")
        if isinstance(rv, (int, float)) and 1 <= int(rv) <= 5:
            sampled_stars[int(rv)] += 1
    await repo.save_snapshot(
        tenant_id=user.tenant_id,
        location_id=config.location_id,
        snapshot_date=datetime.now(UTC),
        average_rating=details.get("rating"),
        total_review_count=details.get("user_rating_count") or 0,
        star_counts=sampled_stars,
    )

    # Persist the resolved Place ID for next time + stamp the sync.
    config.place_id = details["place_id"]
    await repo.mark_synced(config.id)
    await db.commit()

    logger.info(
        "reviews_places_synced",
        tenant_id=str(user.tenant_id),
        place_id=details["place_id"],
        imported=imported,
        rating=details.get("rating"),
        count=details.get("user_rating_count"),
    )
    return {
        "data": {
            "place_id": details["place_id"],
            "rating": details.get("rating"),
            "total_review_count": details.get("user_rating_count"),
            "imported": imported,
        },
        "errors": None,
    }


@router.patch("/config/location", response_model=APIResponse[GoogleReviewConfigResponse])
async def set_review_location(
    user: OwnerDep,
    db: AsyncSessionDep,
    body: GoogleReviewLocationOverride,
) -> dict:
    """Manually pin account_name/location_name (e.g. 'accounts/123', 'accounts/123/locations/456')
    so sync can skip the accounts/locations discovery calls, which are gated by Google's daily
    API quota and can block discovery indefinitely. Get these from the business.google.com
    dashboard URL when discovery is quota-blocked."""
    repo = ReviewsRepository(db)
    config = await repo.set_manual_location(
        tenant_id=user.tenant_id,
        location_id=body.location_id,
        account_name=body.account_name,
        location_name=body.location_name,
    )
    await db.commit()
    return {"data": GoogleReviewConfigResponse.model_validate(config), "errors": None}


@router.delete("/disconnect", response_model=APIResponse[None])
async def reviews_disconnect(
    user: OwnerDep,
    db: AsyncSessionDep,
    config_id: uuid.UUID = Query(...),
) -> dict:
    repo = ReviewsRepository(db)
    await repo.deactivate_config(user.tenant_id, config_id)
    await db.commit()
    return {"data": None, "errors": None}
