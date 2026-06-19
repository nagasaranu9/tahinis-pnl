"""Pipeboard repository — DB ops for accounts, campaigns, metrics."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.external_platform import (
    PipeboardAccount,
    PipeboardAlert,
    PipeboardAuditLog,
    PipeboardCampaign,
    PipeboardCategoryMapping,
    PipeboardDailyMetric,
    PipeboardSyncJob,
)


class PipeboardRepository:
    """CRUD operations for Pipeboard tables."""

    def __init__(self, db: AsyncSession):
        self._db = db

    # Account operations

    async def upsert_pipeboard_account(
        self,
        tenant_id: uuid.UUID,
        pipeboard_account_id: str,
        access_token_encrypted: str,
        refresh_token_encrypted: Optional[str],
        token_expiry: datetime,
        is_active: bool = True,
    ) -> PipeboardAccount:
        """Create or update Pipeboard account."""
        stmt = select(PipeboardAccount).filter(
            PipeboardAccount.tenant_id == tenant_id,
            PipeboardAccount.pipeboard_account_id == pipeboard_account_id,
        )
        result = await self._db.execute(stmt)
        account = result.scalar_one_or_none()

        if account:
            account.access_token_encrypted = access_token_encrypted
            account.refresh_token_encrypted = refresh_token_encrypted
            account.token_expiry = token_expiry
            account.is_active = is_active
        else:
            from datetime import UTC, datetime
            now = datetime.now(UTC)
            account = PipeboardAccount(
                tenant_id=tenant_id,
                pipeboard_account_id=pipeboard_account_id,
                access_token_encrypted=access_token_encrypted,
                refresh_token_encrypted=refresh_token_encrypted,
                token_expiry=token_expiry,
                is_active=is_active,
                created_at=now,
                updated_at=now,
            )
            self._db.add(account)

        await self._db.commit()
        await self._db.refresh(account)
        return account

    async def get_pipeboard_account(
        self,
        account_id: uuid.UUID,
    ) -> Optional[PipeboardAccount]:
        """Get account by ID."""
        stmt = select(PipeboardAccount).filter(PipeboardAccount.id == account_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_pipeboard_account(
        self,
        tenant_id: uuid.UUID,
    ) -> Optional[PipeboardAccount]:
        """Get active account for tenant."""
        stmt = (
            select(PipeboardAccount)
            .filter(
                PipeboardAccount.tenant_id == tenant_id,
                PipeboardAccount.is_active is True,
            )
            .order_by(PipeboardAccount.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_active_accounts(self) -> list[PipeboardAccount]:
        """Get all active Pipeboard accounts across all tenants."""
        stmt = (
            select(PipeboardAccount)
            .filter(PipeboardAccount.is_active is True)
            .order_by(PipeboardAccount.tenant_id, PipeboardAccount.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return result.scalars().all()

    async def update_pipeboard_account_tokens(
        self,
        account_id: uuid.UUID,
        access_token_encrypted: str,
        refresh_token_encrypted: str,
        token_expiry: datetime,
    ) -> None:
        """Update tokens on account."""
        stmt = select(PipeboardAccount).filter(PipeboardAccount.id == account_id)
        result = await self._db.execute(stmt)
        account = result.scalar_one_or_none()

        if account:
            account.access_token_encrypted = access_token_encrypted
            account.refresh_token_encrypted = refresh_token_encrypted
            account.token_expiry = token_expiry
            await self._db.commit()

    async def update_pipeboard_account(
        self,
        account_id: uuid.UUID,
        is_active: Optional[bool] = None,
        last_sync_at: Optional[datetime] = None,
        last_sync_error: Optional[str] = None,
    ) -> None:
        """Update account status."""
        stmt = select(PipeboardAccount).filter(PipeboardAccount.id == account_id)
        result = await self._db.execute(stmt)
        account = result.scalar_one_or_none()

        if account:
            if is_active is not None:
                account.is_active = is_active
            if last_sync_at is not None:
                account.last_sync_at = last_sync_at
            if last_sync_error is not None:
                account.last_sync_error = last_sync_error
            await self._db.commit()

    async def delete_pipeboard_account(
        self,
        account_id: uuid.UUID,
    ) -> None:
        """Delete account and cascade-delete related records."""
        stmt = select(PipeboardAccount).filter(PipeboardAccount.id == account_id)
        result = await self._db.execute(stmt)
        account = result.scalar_one_or_none()

        if account:
            await self._db.delete(account)
            await self._db.commit()

    # Campaign operations

    async def upsert_campaign(
        self,
        tenant_id: uuid.UUID,
        location_id: Optional[uuid.UUID],
        pipeboard_platform: str,
        pipeboard_campaign_id: str,
        name: str,
        status: str,
        campaign_type: Optional[str],
        daily_budget_limit: Optional[object],
        lifetime_budget_limit: Optional[object],
        spend_to_date: Optional[object],
    ) -> PipeboardCampaign:
        """Create or update campaign."""
        stmt = select(PipeboardCampaign).filter(
            PipeboardCampaign.tenant_id == tenant_id,
            PipeboardCampaign.pipeboard_platform == pipeboard_platform,
            PipeboardCampaign.pipeboard_campaign_id == pipeboard_campaign_id,
        )
        result = await self._db.execute(stmt)
        campaign = result.scalar_one_or_none()

        if campaign:
            campaign.name = name
            campaign.status = status
            campaign.campaign_type = campaign_type
            campaign.daily_budget_limit = daily_budget_limit
            campaign.lifetime_budget_limit = lifetime_budget_limit
            campaign.spend_to_date = spend_to_date
        else:
            campaign = PipeboardCampaign(
                tenant_id=tenant_id,
                location_id=location_id,
                pipeboard_platform=pipeboard_platform,
                pipeboard_campaign_id=pipeboard_campaign_id,
                name=name,
                status=status,
                campaign_type=campaign_type,
                daily_budget_limit=daily_budget_limit,
                lifetime_budget_limit=lifetime_budget_limit,
                spend_to_date=spend_to_date,
            )
            self._db.add(campaign)

        await self._db.commit()
        await self._db.refresh(campaign)
        return campaign

    # Metric operations

    async def upsert_daily_metric(
        self,
        tenant_id: uuid.UUID,
        campaign_id: uuid.UUID,
        metric_date: str,
        spend: object,
        impressions: int,
        clicks: int,
        conversions: Optional[object],
        conversion_value: Optional[object],
        ctr: Optional[object],
        cpc: Optional[object],
        roas: Optional[object],
        currency_code: str,
    ) -> PipeboardDailyMetric:
        """Create or update daily metric (idempotent)."""
        stmt = select(PipeboardDailyMetric).filter(
            PipeboardDailyMetric.tenant_id == tenant_id,
            PipeboardDailyMetric.campaign_id == campaign_id,
            PipeboardDailyMetric.metric_date == metric_date,
        )
        result = await self._db.execute(stmt)
        metric = result.scalar_one_or_none()

        if metric:
            metric.spend = spend
            metric.impressions = impressions
            metric.clicks = clicks
            metric.conversions = conversions
            metric.conversion_value = conversion_value
            metric.ctr = ctr
            metric.cpc = cpc
            metric.roas = roas
        else:
            metric = PipeboardDailyMetric(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                metric_date=metric_date,
                spend=spend,
                impressions=impressions,
                clicks=clicks,
                conversions=conversions,
                conversion_value=conversion_value,
                ctr=ctr,
                cpc=cpc,
                roas=roas,
                currency_code=currency_code,
            )
            self._db.add(metric)

        await self._db.commit()
        await self._db.refresh(metric)
        return metric

    # Sync job operations

    async def create_sync_job(
        self,
        tenant_id: uuid.UUID,
        job_type: str,
        pipeboard_platform: Optional[str],
        date_from: Optional[str],
        date_to: Optional[str],
        triggered_by: Optional[uuid.UUID],
    ) -> PipeboardSyncJob:
        """Create sync job."""
        job = PipeboardSyncJob(
            tenant_id=tenant_id,
            job_type=job_type,
            status="pending",
            pipeboard_platform=pipeboard_platform,
            date_from=date_from,
            date_to=date_to,
            triggered_by=triggered_by,
        )
        self._db.add(job)
        await self._db.commit()
        await self._db.refresh(job)
        return job

    async def update_sync_job(
        self,
        job_id: uuid.UUID,
        status: Optional[str] = None,
        metrics_synced: Optional[int] = None,
        campaigns_synced: Optional[int] = None,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        """Update sync job."""
        stmt = select(PipeboardSyncJob).filter(PipeboardSyncJob.id == job_id)
        result = await self._db.execute(stmt)
        job = result.scalar_one_or_none()

        if job:
            if status is not None:
                job.status = status
            if metrics_synced is not None:
                job.metrics_synced = metrics_synced
            if campaigns_synced is not None:
                job.campaigns_synced = campaigns_synced
            if error_message is not None:
                job.error_message = error_message
            if started_at is not None:
                job.started_at = started_at
            if completed_at is not None:
                job.completed_at = completed_at
            await self._db.commit()

    async def get_sync_jobs(
        self,
        tenant_id: uuid.UUID,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[PipeboardSyncJob]:
        """Get sync jobs for tenant, optionally filtered by status."""
        conds = [PipeboardSyncJob.tenant_id == tenant_id]
        if status:
            conds.append(PipeboardSyncJob.status == status)

        stmt = (
            select(PipeboardSyncJob)
            .where(*conds)
            .order_by(PipeboardSyncJob.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return result.scalars().all()

    # Category mapping operations

    async def upsert_category_mapping(
        self,
        tenant_id: uuid.UUID,
        pipeboard_platform: str,
        pipeboard_campaign_type: Optional[str],
        expense_category: str,
    ) -> PipeboardCategoryMapping:
        """Create or update category mapping."""
        stmt = select(PipeboardCategoryMapping).filter(
            PipeboardCategoryMapping.tenant_id == tenant_id,
            PipeboardCategoryMapping.pipeboard_platform == pipeboard_platform,
            PipeboardCategoryMapping.pipeboard_campaign_type == pipeboard_campaign_type,
        )
        result = await self._db.execute(stmt)
        mapping = result.scalar_one_or_none()

        if mapping:
            mapping.expense_category = expense_category
        else:
            mapping = PipeboardCategoryMapping(
                tenant_id=tenant_id,
                pipeboard_platform=pipeboard_platform,
                pipeboard_campaign_type=pipeboard_campaign_type,
                expense_category=expense_category,
            )
            self._db.add(mapping)

        await self._db.commit()
        await self._db.refresh(mapping)
        return mapping

    async def get_category_mapping(
        self,
        tenant_id: uuid.UUID,
        pipeboard_platform: str,
        campaign_type: Optional[str],
    ) -> Optional[PipeboardCategoryMapping]:
        """Get category mapping, falling back to platform-only if campaign_type not found."""
        # Try exact match first
        stmt = select(PipeboardCategoryMapping).filter(
            PipeboardCategoryMapping.tenant_id == tenant_id,
            PipeboardCategoryMapping.pipeboard_platform == pipeboard_platform,
            PipeboardCategoryMapping.pipeboard_campaign_type == campaign_type,
        )
        result = await self._db.execute(stmt)
        mapping = result.scalar_one_or_none()

        if mapping:
            return mapping

        # Fall back to platform-only (campaign_type = None)
        stmt = select(PipeboardCategoryMapping).filter(
            PipeboardCategoryMapping.tenant_id == tenant_id,
            PipeboardCategoryMapping.pipeboard_platform == pipeboard_platform,
            PipeboardCategoryMapping.pipeboard_campaign_type.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_category_mappings_for_tenant(
        self,
        tenant_id: uuid.UUID,
    ) -> list[PipeboardCategoryMapping]:
        """Get all category mappings for tenant."""
        stmt = (
            select(PipeboardCategoryMapping)
            .filter(PipeboardCategoryMapping.tenant_id == tenant_id)
            .order_by(PipeboardCategoryMapping.pipeboard_platform, PipeboardCategoryMapping.pipeboard_campaign_type)
        )
        result = await self._db.execute(stmt)
        return result.scalars().all()

    async def delete_category_mapping(
        self,
        mapping_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> None:
        """Delete category mapping (tenant-scoped)."""
        stmt = select(PipeboardCategoryMapping).filter(
            PipeboardCategoryMapping.id == mapping_id,
            PipeboardCategoryMapping.tenant_id == tenant_id,
        )
        result = await self._db.execute(stmt)
        mapping = result.scalar_one_or_none()

        if mapping:
            await self._db.delete(mapping)
            await self._db.commit()

    # Alert operations

    async def create_alert(
        self,
        tenant_id: uuid.UUID,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        account_id: Optional[uuid.UUID] = None,
    ) -> PipeboardAlert:
        """Create dashboard alert."""
        alert = PipeboardAlert(
            tenant_id=tenant_id,
            account_id=account_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
        )
        self._db.add(alert)
        await self._db.commit()
        await self._db.refresh(alert)
        return alert

    async def get_active_alerts(
        self,
        tenant_id: uuid.UUID,
    ) -> list[PipeboardAlert]:
        """Get non-dismissed alerts for tenant."""
        stmt = (
            select(PipeboardAlert)
            .filter(
                PipeboardAlert.tenant_id == tenant_id,
                PipeboardAlert.is_dismissed.is_(False),
            )
            .order_by(PipeboardAlert.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return result.scalars().all()

    async def dismiss_alert(
        self,
        alert_id: uuid.UUID,
        dismissed_by: Optional[uuid.UUID] = None,
    ) -> None:
        """Dismiss an alert."""
        stmt = select(PipeboardAlert).filter(PipeboardAlert.id == alert_id)
        result = await self._db.execute(stmt)
        alert = result.scalar_one_or_none()

        if alert:
            alert.is_dismissed = True
            alert.dismissed_at = datetime.now()
            alert.dismissed_by = dismissed_by
            await self._db.commit()

    # Audit log operations

    async def create_audit_log(
        self,
        tenant_id: uuid.UUID,
        event_type: str,
        message: str,
        severity: str = "info",
        account_id: Optional[uuid.UUID] = None,
        error_detail: Optional[str] = None,
        triggered_by: Optional[uuid.UUID] = None,
    ) -> PipeboardAuditLog:
        """Create immutable audit log entry."""
        log = PipeboardAuditLog(
            tenant_id=tenant_id,
            account_id=account_id,
            event_type=event_type,
            severity=severity,
            message=message,
            error_detail=error_detail,
            triggered_by=triggered_by,
        )
        self._db.add(log)
        await self._db.commit()
        await self._db.refresh(log)
        return log

    async def get_audit_logs(
        self,
        tenant_id: uuid.UUID,
        limit: int = 100,
    ) -> list[PipeboardAuditLog]:
        """Get recent audit logs for tenant."""
        stmt = (
            select(PipeboardAuditLog)
            .filter(PipeboardAuditLog.tenant_id == tenant_id)
            .order_by(PipeboardAuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return result.scalars().all()
