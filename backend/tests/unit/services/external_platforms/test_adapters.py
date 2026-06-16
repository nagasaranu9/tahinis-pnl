"""Unit tests for mock Google Reviews and Ads adapters."""
from datetime import date
from decimal import Decimal

import pytest

from app.services.external_platforms.google_reviews_adapter import (
    MockGoogleReviewsAdapter,
    GoogleReviewsAdapterFactory,
)
from app.services.external_platforms.google_ads_adapter import (
    MockGoogleAdsAdapter,
    GoogleAdsAdapterFactory,
)


# ---------------------------------------------------------------------------
# Google Reviews mock adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reviews_mock_returns_one_snapshot_per_day():
    adapter = MockGoogleReviewsAdapter()
    start = date(2024, 6, 1)
    end = date(2024, 6, 7)
    snapshots = await adapter.fetch_snapshots("place_abc", start, end)
    assert len(snapshots) == 7


@pytest.mark.asyncio
async def test_reviews_mock_dates_are_sequential():
    adapter = MockGoogleReviewsAdapter()
    start = date(2024, 6, 1)
    end = date(2024, 6, 5)
    snapshots = await adapter.fetch_snapshots("place_abc", start, end)
    dates = [s.snapshot_date for s in snapshots]
    assert dates == sorted(dates)
    assert dates[0] == "2024-06-01"
    assert dates[-1] == "2024-06-05"


@pytest.mark.asyncio
async def test_reviews_mock_rating_within_bounds():
    adapter = MockGoogleReviewsAdapter()
    snapshots = await adapter.fetch_snapshots("place_xyz", date(2024, 1, 1), date(2024, 3, 31))
    for s in snapshots:
        assert Decimal("1.0") <= s.rating_average <= Decimal("5.0")


@pytest.mark.asyncio
async def test_reviews_mock_count_monotonically_non_decreasing():
    adapter = MockGoogleReviewsAdapter()
    snapshots = await adapter.fetch_snapshots("place_abc", date(2024, 6, 1), date(2024, 6, 30))
    for i in range(1, len(snapshots)):
        # review_count_total should never decrease
        assert snapshots[i].review_count_total >= snapshots[i - 1].review_count_total


@pytest.mark.asyncio
async def test_reviews_mock_is_deterministic():
    adapter = MockGoogleReviewsAdapter()
    start = date(2024, 6, 1)
    end = date(2024, 6, 5)
    run1 = await adapter.fetch_snapshots("place_test", start, end)
    run2 = await adapter.fetch_snapshots("place_test", start, end)
    assert [s.rating_average for s in run1] == [s.rating_average for s in run2]


@pytest.mark.asyncio
async def test_reviews_mock_single_day():
    adapter = MockGoogleReviewsAdapter()
    snapshots = await adapter.fetch_snapshots("p", date(2024, 6, 15), date(2024, 6, 15))
    assert len(snapshots) == 1
    assert snapshots[0].snapshot_date == "2024-06-15"


def test_reviews_factory_creates_mock():
    adapter = GoogleReviewsAdapterFactory.create("mock")
    assert isinstance(adapter, MockGoogleReviewsAdapter)


def test_reviews_factory_raises_for_google():
    with pytest.raises(NotImplementedError):
        GoogleReviewsAdapterFactory.create("google")


# ---------------------------------------------------------------------------
# Google Ads mock adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ads_mock_returns_two_campaigns():
    adapter = MockGoogleAdsAdapter()
    data = await adapter.fetch_data("cust_001", date(2024, 6, 1), date(2024, 6, 7))
    assert len(data.campaigns) == 2


@pytest.mark.asyncio
async def test_ads_mock_metrics_per_campaign_per_day():
    adapter = MockGoogleAdsAdapter()
    data = await adapter.fetch_data("cust_001", date(2024, 6, 1), date(2024, 6, 5))
    # 2 campaigns × 5 days = 10 metric rows
    assert len(data.daily_metrics) == 10


@pytest.mark.asyncio
async def test_ads_mock_spend_non_negative():
    adapter = MockGoogleAdsAdapter()
    data = await adapter.fetch_data("cust_x", date(2024, 1, 1), date(2024, 1, 31))
    for m in data.daily_metrics:
        assert m.spend >= Decimal("0")


@pytest.mark.asyncio
async def test_ads_mock_roas_non_negative():
    adapter = MockGoogleAdsAdapter()
    data = await adapter.fetch_data("cust_x", date(2024, 1, 1), date(2024, 1, 10))
    for m in data.daily_metrics:
        if m.roas is not None:
            assert m.roas >= Decimal("0")


@pytest.mark.asyncio
async def test_ads_mock_metric_campaign_ids_match_campaigns():
    adapter = MockGoogleAdsAdapter()
    data = await adapter.fetch_data("cust_001", date(2024, 6, 1), date(2024, 6, 3))
    campaign_ids = {c.google_campaign_id for c in data.campaigns}
    metric_ids = {m.campaign_id for m in data.daily_metrics}
    assert metric_ids.issubset(campaign_ids)


@pytest.mark.asyncio
async def test_ads_mock_is_deterministic():
    adapter = MockGoogleAdsAdapter()
    d1 = await adapter.fetch_data("cust_det", date(2024, 6, 1), date(2024, 6, 5))
    d2 = await adapter.fetch_data("cust_det", date(2024, 6, 1), date(2024, 6, 5))
    spends_1 = [m.spend for m in d1.daily_metrics]
    spends_2 = [m.spend for m in d2.daily_metrics]
    assert spends_1 == spends_2


def test_ads_factory_creates_mock():
    adapter = GoogleAdsAdapterFactory.create("mock")
    assert isinstance(adapter, MockGoogleAdsAdapter)


def test_ads_factory_raises_for_google():
    with pytest.raises(NotImplementedError):
        GoogleAdsAdapterFactory.create("google")
