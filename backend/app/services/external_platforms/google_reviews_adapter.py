"""Google Business Profile reviews adapter.

Production: wraps Google Business Profile API.
Mock: returns deterministic fake snapshots for development.

Swap via GOOGLE_REVIEWS_ADAPTER env var: "mock" (default) | "google"
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass
class ReviewSnapshot:
    snapshot_date: str  # YYYY-MM-DD
    rating_average: Decimal
    review_count_total: int
    new_reviews_count: int
    positive_count: int
    neutral_count: int
    negative_count: int
    google_place_id: str | None = None


class GoogleReviewsAdapter(ABC):
    @abstractmethod
    async def fetch_snapshots(
        self,
        place_id: str,
        start_date: date,
        end_date: date,
    ) -> list[ReviewSnapshot]:
        """Return daily review snapshots between start_date and end_date inclusive."""


class MockGoogleReviewsAdapter(GoogleReviewsAdapter):
    """Deterministic mock — generates realistic review trends for development."""

    async def fetch_snapshots(
        self,
        place_id: str,
        start_date: date,
        end_date: date,
    ) -> list[ReviewSnapshot]:
        snapshots: list[ReviewSnapshot] = []
        rng = random.Random(place_id)  # deterministic per place
        total = 120  # starting review count
        rating = Decimal("4.3")

        current = start_date
        while current <= end_date:
            new_today = rng.randint(0, 3)
            total += new_today
            pos = max(0, new_today - rng.randint(0, 1))
            neg = 1 if new_today > 2 and rng.random() < 0.1 else 0
            neu = new_today - pos - neg

            # Slight rating drift
            drift = Decimal(str(rng.uniform(-0.05, 0.05))).quantize(Decimal("0.01"))
            rating = max(Decimal("1.0"), min(Decimal("5.0"), rating + drift))

            snapshots.append(
                ReviewSnapshot(
                    snapshot_date=current.strftime("%Y-%m-%d"),
                    rating_average=rating,
                    review_count_total=total,
                    new_reviews_count=new_today,
                    positive_count=pos,
                    neutral_count=max(0, neu),
                    negative_count=neg,
                    google_place_id=place_id,
                )
            )
            current += timedelta(days=1)
        return snapshots


class GoogleReviewsAdapterFactory:
    @staticmethod
    def create(adapter_type: str = "mock") -> GoogleReviewsAdapter:
        if adapter_type == "google":
            raise NotImplementedError("Google Business Profile API adapter not yet implemented")
        return MockGoogleReviewsAdapter()
