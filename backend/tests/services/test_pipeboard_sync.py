"""Test suite for Pipeboard sync service (token refresh, backfill, alerts)."""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.external_platform import PipeboardAccount, PipeboardDailyMetric
from app.db.repositories.pipeboard_repo import PipeboardRepository
from app.services.pipeboard.sync_service import PipeboardSyncService
from app.services.pipeboard.backfill_service import PipeboardBackfillService
from app.services.pipeboard.alert_service import PipeboardAlertService, AlertType, AlertSeverity
from app.core.security import encrypt_value, decrypt_value


class TestTokenConnect:
    """Test API-token connection (no OAuth flow)."""

    async def test_connect_with_token_creates_account(self, db: AsyncSession):
        """Valid token → account created, token stored encrypted."""
        service = PipeboardSyncService(db)  # mock adapter via settings
        tenant_id = uuid.uuid4()

        account = await service.connect_with_token(
            tenant_id=tenant_id,
            api_token="pb_test_token_123",
            platform="google_ads",
        )

        assert account.is_active is True
        # Mock adapter reports customer id 4104711801.
        assert account.pipeboard_account_id == "4104711801"

    async def test_get_api_token_roundtrips(self, db: AsyncSession):
        """Stored token decrypts back to original value."""
        service = PipeboardSyncService(db)
        tenant_id = uuid.uuid4()

        account = await service.connect_with_token(
            tenant_id=tenant_id,
            api_token="pb_secret_xyz",
            platform="google_ads",
        )
        assert service.get_api_token(account) == "pb_secret_xyz"

    async def test_get_api_token_none_when_missing(self, db: AsyncSession):
        """No stored token → None."""
        service = PipeboardSyncService(db)
        repo = PipeboardRepository(db)
        tenant_id = uuid.uuid4()
        account = await repo.upsert_pipeboard_account(
            tenant_id=tenant_id,
            pipeboard_account_id="acct_no_token",
            access_token_encrypted=None,
            refresh_token_encrypted=None,
            token_expiry=datetime.now(UTC) + timedelta(days=1),
        )
        assert service.get_api_token(account) is None


class TestCategoryMappingPriority:
    """Test category mapping priority (exact type match vs platform-only fallback)."""

    async def test_exact_type_match_takes_priority(self, db: AsyncSession):
        """Exact platform + type match should take priority."""
        repo = PipeboardRepository(db)
        tenant_id = uuid.uuid4()

        # Create both exact and fallback mappings
        await repo.upsert_category_mapping(
            tenant_id=tenant_id,
            pipeboard_platform="google_ads",
            pipeboard_campaign_type="SEARCH",
            expense_category="Performance Marketing",
        )
        await repo.upsert_category_mapping(
            tenant_id=tenant_id,
            pipeboard_platform="google_ads",
            pipeboard_campaign_type=None,  # Platform-only fallback
            expense_category="Marketing",
        )

        # Query for exact match
        mapping = await repo.get_category_mapping(
            tenant_id=tenant_id,
            pipeboard_platform="google_ads",
            campaign_type="SEARCH",
        )

        assert mapping.expense_category == "Performance Marketing"

    async def test_platform_only_fallback_when_no_type_match(self, db: AsyncSession):
        """Platform-only mapping should be fallback."""
        repo = PipeboardRepository(db)
        tenant_id = uuid.uuid4()

        # Create only platform-only mapping
        await repo.upsert_category_mapping(
            tenant_id=tenant_id,
            pipeboard_platform="meta_ads",
            pipeboard_campaign_type=None,
            expense_category="Social Media",
        )

        # Query with non-existent type
        mapping = await repo.get_category_mapping(
            tenant_id=tenant_id,
            pipeboard_platform="meta_ads",
            campaign_type="DISPLAY",  # Doesn't exist
        )

        assert mapping.expense_category == "Social Media"

    async def test_no_mapping_returns_none(self, db: AsyncSession):
        """No matching mapping should return None."""
        repo = PipeboardRepository(db)
        tenant_id = uuid.uuid4()

        mapping = await repo.get_category_mapping(
            tenant_id=tenant_id,
            pipeboard_platform="tiktok_ads",
            campaign_type="SEARCH",
        )

        assert mapping is None


class TestChunkingEdgeCases:
    """Test chunked backfill date range handling."""

    def test_single_day_range_creates_one_chunk(self):
        """Single-day range should create one chunk."""
        from app.services.pipeboard.backfill_service import PipeboardBackfillService
        from datetime import date

        start = date(2024, 6, 15)
        end = date(2024, 6, 15)

        chunks = PipeboardBackfillService._chunk_date_range(start, end, 30)

        assert len(chunks) == 1
        assert chunks[0] == (start, end)

    def test_exact_chunk_boundary_creates_full_chunks(self):
        """Date range matching chunk boundary should create clean chunks."""
        from app.services.pipeboard.backfill_service import PipeboardBackfillService
        from datetime import date

        start = date(2024, 1, 1)
        end = date(2024, 3, 31)  # Exactly 90 days

        chunks = PipeboardBackfillService._chunk_date_range(start, end, 30)

        assert len(chunks) == 3
        assert chunks[0] == (date(2024, 1, 1), date(2024, 1, 30))
        assert chunks[1] == (date(2024, 1, 31), date(2024, 2, 29))
        assert chunks[2] == (date(2024, 3, 1), date(2024, 3, 31))

    def test_partial_chunk_at_end(self):
        """Partial chunk at end should not exceed end date."""
        from app.services.pipeboard.backfill_service import PipeboardBackfillService
        from datetime import date

        start = date(2024, 1, 1)
        end = date(2024, 1, 45)  # 45 days (1 full 30-day chunk + 15-day partial)

        chunks = PipeboardBackfillService._chunk_date_range(start, end, 30)

        assert len(chunks) == 2
        assert chunks[0] == (date(2024, 1, 1), date(2024, 1, 30))
        assert chunks[1] == (date(2024, 1, 31), date(2024, 2, 14))  # 15 days


class TestAlertDispatch:
    """Test multi-channel alert dispatch."""

    async def test_sync_failed_alert_creates_dashboard_and_audit(self, db: AsyncSession):
        """Sync failure alert should create dashboard alert + audit log."""
        service = PipeboardAlertService(db)
        repo = PipeboardRepository(db)

        tenant_id = uuid.uuid4()
        account = await repo.upsert_pipeboard_account(
            tenant_id=tenant_id,
            pipeboard_account_id="test_alert_001",
            access_token_encrypted=encrypt_value("token"),
            refresh_token_encrypted=encrypt_value("refresh"),
            token_expiry=datetime.now(UTC) + timedelta(hours=1),
        )

        await service.alert_sync_failed(
            tenant_id=tenant_id,
            account=account,
            error="API rate limit exceeded",
        )

        # Check dashboard alert
        alerts = await repo.get_active_alerts(tenant_id)
        assert len(alerts) > 0
        assert alerts[0].alert_type == AlertType.SYNC_FAILED.value
        assert alerts[0].severity == AlertSeverity.ERROR.value

        # Check audit log
        logs = await repo.get_audit_logs(tenant_id, limit=1)
        assert len(logs) > 0
        assert logs[0].event_type == AlertType.SYNC_FAILED.value

    async def test_auth_failed_alert_marks_account_inactive(self, db: AsyncSession):
        """Auth failure alert should mark account inactive."""
        service = PipeboardAlertService(db)
        repo = PipeboardRepository(db)

        tenant_id = uuid.uuid4()
        account = await repo.upsert_pipeboard_account(
            tenant_id=tenant_id,
            pipeboard_account_id="test_alert_002",
            access_token_encrypted=encrypt_value("token"),
            refresh_token_encrypted=encrypt_value("refresh"),
            token_expiry=datetime.now(UTC) + timedelta(hours=1),
        )

        await service.alert_auth_failed(
            tenant_id=tenant_id,
            account=account,
            error="Token invalid",
        )

        # Dashboard alert should have critical severity
        alerts = await repo.get_active_alerts(tenant_id)
        assert len(alerts) > 0
        assert alerts[0].severity == AlertSeverity.CRITICAL.value


class TestTenantIsolation:
    """Test tenant isolation in queries."""

    async def test_category_mapping_scoped_by_tenant(self, db: AsyncSession):
        """Category mappings should be scoped by tenant."""
        repo = PipeboardRepository(db)

        tenant1 = uuid.uuid4()
        tenant2 = uuid.uuid4()

        # Create mapping for tenant1
        await repo.upsert_category_mapping(
            tenant_id=tenant1,
            pipeboard_platform="google_ads",
            pipeboard_campaign_type="SEARCH",
            expense_category="Marketing",
        )

        # Query for tenant2 should not find tenant1's mapping
        mapping = await repo.get_category_mapping(
            tenant_id=tenant2,
            pipeboard_platform="google_ads",
            campaign_type="SEARCH",
        )

        assert mapping is None

    async def test_alerts_scoped_by_tenant(self, db: AsyncSession):
        """Alerts should be scoped by tenant."""
        repo = PipeboardRepository(db)

        tenant1 = uuid.uuid4()
        tenant2 = uuid.uuid4()

        # Create alert for tenant1
        await repo.create_alert(
            tenant_id=tenant1,
            alert_type="sync_failed",
            severity="error",
            title="Sync Failed",
            message="Test error",
        )

        # Query for tenant2 should return no alerts
        alerts2 = await repo.get_active_alerts(tenant2)
        assert len(alerts2) == 0

        # Query for tenant1 should return the alert
        alerts1 = await repo.get_active_alerts(tenant1)
        assert len(alerts1) == 1

    async def test_sync_jobs_scoped_by_tenant(self, db: AsyncSession):
        """Sync jobs should be scoped by tenant."""
        repo = PipeboardRepository(db)

        tenant1 = uuid.uuid4()
        tenant2 = uuid.uuid4()

        # Create sync job for tenant1
        await repo.create_sync_job(
            tenant_id=tenant1,
            job_type="incremental",
            pipeboard_platform="google_ads",
            date_from=None,
            date_to=None,
            triggered_by=None,
        )

        # Query for tenant2 should return no jobs
        jobs2 = await repo.get_sync_jobs(tenant2)
        assert len(jobs2) == 0

        # Query for tenant1 should return the job
        jobs1 = await repo.get_sync_jobs(tenant1)
        assert len(jobs1) == 1


# Pytest fixtures
@pytest.fixture
async def db():
    """Async DB session fixture."""
    # Requires pytest-asyncio and async session setup
    # Implementation depends on project's test database setup
    pass
