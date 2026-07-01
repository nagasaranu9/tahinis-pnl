import uuid
from datetime import datetime, timezone
from decimal import Decimal

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.google_reviews import GoogleReview, GoogleReviewConfig
from app.db.models.external_platform import GoogleReviewSnapshot

logger = structlog.get_logger(__name__)


class ReviewsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Configs
    # ------------------------------------------------------------------

    async def upsert_config(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
        place_id: str,
        account_name: str | None,
        location_name: str | None,
        integration_credential_id: uuid.UUID,
    ) -> GoogleReviewConfig:
        existing = await self.get_config(tenant_id, location_id)
        if existing:
            existing.place_id = place_id
            existing.account_name = account_name
            existing.location_name = location_name
            existing.is_active = True
            await self._db.flush()
            return existing

        config = GoogleReviewConfig(
            tenant_id=tenant_id,
            location_id=location_id,
            place_id=place_id,
            account_name=account_name,
            location_name=location_name,
            is_active=True,
        )
        self._db.add(config)
        await self._db.flush()
        return config

    async def get_config(
        self, tenant_id: uuid.UUID, location_id: uuid.UUID
    ) -> GoogleReviewConfig | None:
        result = await self._db.execute(
            select(GoogleReviewConfig).where(
                and_(
                    GoogleReviewConfig.tenant_id == tenant_id,
                    GoogleReviewConfig.location_id == location_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_configs(self, tenant_id: uuid.UUID) -> list[GoogleReviewConfig]:
        result = await self._db.execute(
            select(GoogleReviewConfig).where(
                and_(
                    GoogleReviewConfig.tenant_id == tenant_id,
                    GoogleReviewConfig.is_active == True,
                )
            )
        )
        return list(result.scalars().all())

    async def deactivate_config(self, tenant_id: uuid.UUID, config_id: uuid.UUID) -> None:
        result = await self._db.execute(
            select(GoogleReviewConfig).where(
                and_(
                    GoogleReviewConfig.tenant_id == tenant_id,
                    GoogleReviewConfig.id == config_id,
                )
            )
        )
        config = result.scalar_one_or_none()
        if config:
            config.is_active = False
            await self._db.flush()

    async def set_manual_location(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
        account_name: str,
        location_name: str,
    ) -> GoogleReviewConfig:
        """Manually pin account_name/location_name, bypassing the accounts/locations
        discovery calls (which are gated by Google's daily quota)."""
        config = await self.get_config(tenant_id, location_id)
        if config is None:
            from app.core.exceptions import NotFoundError
            raise NotFoundError(f"No review config for location {location_id}")
        config.account_name = account_name
        config.location_name = location_name
        config.place_id = account_name
        await self._db.flush()
        return config

    async def mark_synced(self, config_id: uuid.UUID) -> None:
        result = await self._db.execute(
            select(GoogleReviewConfig).where(GoogleReviewConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config:
            config.last_synced_at = datetime.now(timezone.utc)
            await self._db.flush()

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------

    async def upsert_review(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
        review_id: str,
        author_name: str | None,
        rating: int | None,
        comment: str | None,
        published_at: datetime | None,
        update_time: datetime | None,
        reply_comment: str | None,
        reply_update_time: datetime | None,
    ) -> None:
        stmt = (
            pg_insert(GoogleReview)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                location_id=location_id,
                review_id=review_id,
                author_name=author_name,
                rating=rating,
                comment=comment,
                published_at=published_at,
                update_time=update_time,
                reply_comment=reply_comment,
                reply_update_time=reply_update_time,
            )
            .on_conflict_do_update(
                constraint="uq_google_review_tenant",
                set_={
                    "author_name": author_name,
                    "rating": rating,
                    "comment": comment,
                    "update_time": update_time,
                    "reply_comment": reply_comment,
                    "reply_update_time": reply_update_time,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
        )
        await self._db.execute(stmt)

    async def list_reviews(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[list[GoogleReview], int]:
        conditions = [GoogleReview.tenant_id == tenant_id]
        if location_id:
            conditions.append(GoogleReview.location_id == location_id)
        if date_from:
            conditions.append(GoogleReview.published_at >= datetime.fromisoformat(date_from))
        if date_to:
            conditions.append(GoogleReview.published_at <= datetime.fromisoformat(date_to).replace(hour=23, minute=59, second=59))

        total = (
            await self._db.execute(
                select(func.count()).select_from(GoogleReview).where(and_(*conditions))
            )
        ).scalar_one()

        rows = (
            await self._db.execute(
                select(GoogleReview)
                .where(and_(*conditions))
                .order_by(GoogleReview.published_at.desc().nullslast())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).scalars().all()
        return list(rows), total

    async def get_summary(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        conditions = [GoogleReview.tenant_id == tenant_id]
        if location_id:
            conditions.append(GoogleReview.location_id == location_id)
        if date_from:
            conditions.append(GoogleReview.published_at >= datetime.fromisoformat(date_from))
        if date_to:
            conditions.append(GoogleReview.published_at <= datetime.fromisoformat(date_to).replace(hour=23, minute=59, second=59))

        rows = (
            await self._db.execute(
                select(GoogleReview.rating).where(and_(*conditions))
            )
        ).scalars().all()

        total = len(rows)
        if total == 0:
            return {
                "average_rating": None,
                "total_review_count": 0,
                "five_star": 0,
                "four_star": 0,
                "three_star": 0,
                "two_star": 0,
                "one_star": 0,
            }

        star_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in rows:
            if r and 1 <= r <= 5:
                star_counts[r] += 1

        avg = round(sum(r for r in rows if r) / total, 2) if total else None
        # Date filters: use calculated avg from rows (don't prefer snapshot for time ranges)
        if date_from or date_to:
            return {
                "average_rating": avg,
                "total_review_count": total,
                "five_star": star_counts[5],
                "four_star": star_counts[4],
                "three_star": star_counts[3],
                "two_star": star_counts[2],
                "one_star": star_counts[1],
            }
        # No date filter: prefer the true aggregate (Places API gives real rating + full count)
        snap = await self.get_latest_snapshot(tenant_id, location_id)
        if snap is not None and snap.review_count_total:
            avg = float(snap.rating_average) if snap.rating_average is not None else avg
            total = snap.review_count_total
        return {
            "average_rating": avg,
            "total_review_count": total,
            "five_star": star_counts[5],
            "four_star": star_counts[4],
            "three_star": star_counts[3],
            "two_star": star_counts[2],
            "one_star": star_counts[1],
        }

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    async def save_snapshot(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
        snapshot_date: datetime,
        average_rating: float | None,
        total_review_count: int,
        star_counts: dict,
    ) -> None:
        # Existing GoogleReviewSnapshot uses YYYY-MM-DD string + pos/neu/neg counts
        date_str = snapshot_date.strftime("%Y-%m-%d")
        positive = star_counts.get(5, 0) + star_counts.get(4, 0)
        neutral = star_counts.get(3, 0)
        negative = star_counts.get(2, 0) + star_counts.get(1, 0)
        stmt = (
            pg_insert(GoogleReviewSnapshot)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                location_id=location_id,
                snapshot_date=date_str,
                rating_average=Decimal(str(round(average_rating, 2))) if average_rating else None,
                review_count_total=total_review_count,
                new_reviews_count=0,
                positive_count=positive,
                neutral_count=neutral,
                negative_count=negative,
            )
            .on_conflict_do_update(
                constraint="uq_review_snapshot",
                set_={
                    "rating_average": Decimal(str(round(average_rating, 2))) if average_rating else None,
                    "review_count_total": total_review_count,
                    "positive_count": positive,
                    "neutral_count": neutral,
                    "negative_count": negative,
                },
            )
        )
        await self._db.execute(stmt)

    async def get_latest_snapshot(
        self, tenant_id: uuid.UUID, location_id: uuid.UUID | None = None
    ) -> GoogleReviewSnapshot | None:
        """Most recent snapshot — holds the TRUE aggregate rating + total count
        (e.g. from Places API: 4.8 / 1995), as opposed to the average of the
        handful of individual review rows we store."""
        conds = [GoogleReviewSnapshot.tenant_id == tenant_id]
        if location_id is not None:
            conds.append(GoogleReviewSnapshot.location_id == location_id)
        row = (await self._db.execute(
            select(GoogleReviewSnapshot)
            .where(and_(*conds))
            .order_by(GoogleReviewSnapshot.snapshot_date.desc())
            .limit(1)
        )).scalar_one_or_none()
        return row
