import asyncio
import uuid
from datetime import datetime, timezone

import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.reviews_sync.sync_reviews",
    bind=True,
    queue="sync",
    max_retries=3,
    default_retry_delay=120,
)
def sync_reviews(self, tenant_id: str, location_id: str) -> dict:
    from app.services.google.reviews_client import GoogleAPIRateLimitError

    try:
        return asyncio.run(_sync_async(tenant_id, location_id))
    except GoogleAPIRateLimitError as exc:
        # Google's GBP quota is daily, not per-minute — back off for a long stretch
        # instead of burning retries against a quota that won't reset soon.
        countdown = exc.retry_after_seconds or 3600
        logger.warning("reviews_sync_rate_limited", tenant_id=tenant_id, retry_in=countdown)
        raise self.retry(countdown=countdown, exc=exc)


async def _sync_async(tenant_id_str: str, location_id_str: str) -> dict:
    from sqlalchemy import select

    from app.core.security import decrypt_value
    from app.db.models.integration import IntegrationCredential
    from app.db.repositories.reviews_repo import ReviewsRepository
    from app.db.session import AsyncSessionLocal
    from app.services.google.reviews_client import GoogleAPIRateLimitError, GoogleReviewsClient

    tenant_id = uuid.UUID(tenant_id_str)
    location_id = uuid.UUID(location_id_str)

    async with AsyncSessionLocal() as db:
        repo = ReviewsRepository(db)
        config = await repo.get_config(tenant_id, location_id)
        if not config or not config.is_active:
            logger.warning("reviews_sync_no_config", tenant_id=tenant_id_str)
            return {"status": "skipped", "reason": "no_config"}

        cred_row = (await db.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.tenant_id == tenant_id,
                IntegrationCredential.provider == "google_business",
            ).order_by(IntegrationCredential.created_at.desc()).limit(1)
        )).scalar_one_or_none()

        if not cred_row:
            logger.warning("reviews_sync_no_cred", tenant_id=tenant_id_str)
            return {"status": "skipped", "reason": "no_credential"}

        access_token = decrypt_value(cred_row.access_token_encrypted)
        refresh_token = decrypt_value(cred_row.refresh_token_encrypted)
        account_name = config.account_name
        location_name = config.location_name

        # account_name/location_name are set manually via PATCH /reviews/config/location
        # (owner copies them from the business.google.com dashboard URL). We never call
        # the accounts/locations discovery API here — it shares Google's daily quota with
        # everything else and a 429 there used to block sync indefinitely.
        if not account_name or not location_name:
            logger.warning("reviews_sync_no_location_name", tenant_id=tenant_id_str)
            return {"status": "skipped", "reason": "no_location_name"}

        total_imported = 0
        page_token = None

        async with GoogleReviewsClient(access_token, refresh_token) as client:
            while True:
                try:
                    data = await client.list_reviews(account_name, location_name, page_token)
                except GoogleAPIRateLimitError:
                    # Commit whatever reviews were already imported this run before
                    # propagating, so a quota hit mid-pagination doesn't lose progress.
                    await db.commit()
                    raise
                except Exception as exc:
                    logger.error("reviews_sync_api_error", error=str(exc))
                    break

                for review in data.get("reviews", []):
                    review_id = review.get("reviewId") or review.get("name", "")
                    author = (review.get("reviewer") or {}).get("displayName")
                    star_str = review.get("starRating", "")
                    rating = _star_to_int(star_str)
                    comment = review.get("comment")
                    published_at = _parse_dt(review.get("createTime"))
                    update_time = _parse_dt(review.get("updateTime"))
                    reply = review.get("reviewReply") or {}
                    reply_comment = reply.get("comment")
                    reply_update = _parse_dt(reply.get("updateTime"))

                    await repo.upsert_review(
                        tenant_id=tenant_id,
                        location_id=location_id,
                        review_id=review_id,
                        author_name=author,
                        rating=rating,
                        comment=comment,
                        published_at=published_at,
                        update_time=update_time,
                        reply_comment=reply_comment,
                        reply_update_time=reply_update,
                    )
                    total_imported += 1

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        summary = await repo.get_summary(tenant_id, location_id)
        star_counts = {
            5: summary["five_star"],
            4: summary["four_star"],
            3: summary["three_star"],
            2: summary["two_star"],
            1: summary["one_star"],
        }
        await repo.save_snapshot(
            tenant_id=tenant_id,
            location_id=location_id,
            snapshot_date=datetime.now(timezone.utc),
            average_rating=summary["average_rating"],
            total_review_count=summary["total_review_count"],
            star_counts=star_counts,
        )
        await repo.mark_synced(config.id)
        await db.commit()

        logger.info("reviews_sync_complete", tenant_id=tenant_id_str, imported=total_imported)
        return {"status": "ok", "imported": total_imported}


def _star_to_int(star: str) -> int | None:
    return {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}.get(star)


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except Exception:
        return None


@celery_app.task(name="reviews.daily_sync_all_tenants")
def daily_reviews_sync_all_tenants() -> None:
    asyncio.run(_sync_all_async())


async def _sync_all_async() -> None:
    from sqlalchemy import select
    from app.db.models.google_reviews import GoogleReviewConfig
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(GoogleReviewConfig).where(GoogleReviewConfig.is_active == True)
        )).scalars().all()

    for cfg in rows:
        sync_reviews.apply_async(
            kwargs={"tenant_id": str(cfg.tenant_id), "location_id": str(cfg.location_id)},
            queue="sync",
        )
    logger.info("reviews_daily_dispatched", count=len(rows))


# ---------------------------------------------------------------------------
# Places API (New) hourly refresh — works with just GOOGLE_PLACES_API_KEY, no
# Business Profile allowlisting. Keeps the dashboard/marketing reviews dynamic
# (rating + total count + up to 5 recent reviews) while GBP access is pending.
# ---------------------------------------------------------------------------


@celery_app.task(name="reviews.places_refresh_all_tenants")
def places_refresh_all_tenants() -> None:
    asyncio.run(_places_refresh_all_async())


async def _places_refresh_all_async() -> None:
    from sqlalchemy import select
    from app.db.models.google_reviews import GoogleReviewConfig
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(GoogleReviewConfig).where(GoogleReviewConfig.is_active == True)
        )).scalars().all()

    for cfg in rows:
        # Only refresh configs with a resolved Place ID; others need the
        # one-time Places "Import reviews now" (search) on the Reviews tab first.
        if cfg.place_id and cfg.place_id.startswith(("ChIJ", "places/")):
            refresh_reviews_places.apply_async(
                kwargs={"tenant_id": str(cfg.tenant_id), "location_id": str(cfg.location_id)},
                queue="sync",
            )
    logger.info("reviews_places_refresh_dispatched", count=len(rows))


@celery_app.task(
    name="app.workers.tasks.reviews_sync.refresh_reviews_places",
    bind=True,
    queue="sync",
    max_retries=2,
    default_retry_delay=300,
)
def refresh_reviews_places(self, tenant_id: str, location_id: str) -> dict:
    return asyncio.run(_places_refresh_one_async(tenant_id, location_id))


async def _places_refresh_one_async(tenant_id_str: str, location_id_str: str) -> dict:
    from app.core.config import settings
    from app.db.repositories.reviews_repo import ReviewsRepository
    from app.db.session import AsyncSessionLocal
    from app.services.google.places_client import PlacesAPIError, get_place_reviews

    api_key = settings.GOOGLE_PLACES_API_KEY
    if not api_key:
        logger.warning("places_refresh_no_key", tenant_id=tenant_id_str)
        return {"status": "skipped", "reason": "no_api_key"}

    tenant_id = uuid.UUID(tenant_id_str)
    location_id = uuid.UUID(location_id_str)

    async with AsyncSessionLocal() as db:
        repo = ReviewsRepository(db)
        config = await repo.get_config(tenant_id, location_id)
        if not config or not config.is_active:
            return {"status": "skipped", "reason": "no_config"}
        if not (config.place_id and config.place_id.startswith(("ChIJ", "places/"))):
            return {"status": "skipped", "reason": "no_place_id"}

        try:
            details = await get_place_reviews(config.place_id, api_key)
        except PlacesAPIError as exc:
            logger.error("places_refresh_failed", status=exc.status, body=exc.body[:200])
            return {"status": "error", "http": exc.status}

        imported = 0
        sampled_stars: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in details["reviews"]:
            if not r.get("name"):
                continue
            rating = int(r["rating"]) if r.get("rating") is not None else None
            published = _parse_dt(r.get("publish_time"))
            await repo.upsert_review(
                tenant_id=tenant_id,
                location_id=location_id,
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
            if isinstance(r.get("rating"), (int, float)) and 1 <= int(r["rating"]) <= 5:
                sampled_stars[int(r["rating"])] += 1

        await repo.save_snapshot(
            tenant_id=tenant_id,
            location_id=location_id,
            snapshot_date=datetime.now(timezone.utc),
            average_rating=details.get("rating"),
            total_review_count=details.get("user_rating_count") or 0,
            star_counts=sampled_stars,
        )
        await repo.mark_synced(config.id)
        await db.commit()

        logger.info(
            "reviews_places_refreshed",
            tenant_id=tenant_id_str,
            imported=imported,
            rating=details.get("rating"),
            count=details.get("user_rating_count"),
        )
        return {"status": "ok", "imported": imported}
