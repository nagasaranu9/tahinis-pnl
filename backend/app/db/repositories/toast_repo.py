from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.toast import (
    ToastEmployee,
    ToastMenu,
    ToastMenuItem,
    ToastOrder,
    ToastOrderItem,
    ToastPayment,
    ToastSyncConfig,
    ToastSyncJob,
    ToastTimeEntry,
)


class ToastRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # SyncConfig
    # ------------------------------------------------------------------

    async def get_sync_config(
        self, tenant_id: uuid.UUID, location_id: uuid.UUID
    ) -> Optional[ToastSyncConfig]:
        result = await self._db.execute(
            select(ToastSyncConfig).where(
                ToastSyncConfig.tenant_id == tenant_id,
                ToastSyncConfig.location_id == location_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_sync_config(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
        integration_credential_id: uuid.UUID,
        toast_restaurant_guid: str,
        historical_import_from: Optional[datetime] = None,
    ) -> ToastSyncConfig:
        existing = await self.get_sync_config(tenant_id, location_id)
        if existing:
            existing.integration_credential_id = integration_credential_id
            existing.toast_restaurant_guid = toast_restaurant_guid
            existing.is_active = True
            if historical_import_from:
                existing.historical_import_from = historical_import_from
            await self._db.flush()
            return existing
        config = ToastSyncConfig(
            tenant_id=tenant_id,
            location_id=location_id,
            integration_credential_id=integration_credential_id,
            toast_restaurant_guid=toast_restaurant_guid,
            historical_import_from=historical_import_from,
        )
        self._db.add(config)
        await self._db.flush()
        return config

    async def update_last_synced(
        self, tenant_id: uuid.UUID, location_id: uuid.UUID, synced_at: datetime
    ) -> None:
        await self._db.execute(
            update(ToastSyncConfig)
            .where(
                ToastSyncConfig.tenant_id == tenant_id,
                ToastSyncConfig.location_id == location_id,
            )
            .values(last_synced_at=synced_at)
        )

    async def mark_historical_complete(
        self, tenant_id: uuid.UUID, location_id: uuid.UUID
    ) -> None:
        await self._db.execute(
            update(ToastSyncConfig)
            .where(
                ToastSyncConfig.tenant_id == tenant_id,
                ToastSyncConfig.location_id == location_id,
            )
            .values(historical_import_complete=True)
        )

    async def get_latest_historical_job(
        self, tenant_id: uuid.UUID, location_id: uuid.UUID
    ) -> Optional[ToastSyncJob]:
        result = await self._db.execute(
            select(ToastSyncJob)
            .where(
                ToastSyncJob.tenant_id == tenant_id,
                ToastSyncJob.location_id == location_id,
                ToastSyncJob.job_type == "historical",
            )
            .order_by(ToastSyncJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_active_configs(self) -> Sequence[ToastSyncConfig]:
        result = await self._db.execute(
            select(ToastSyncConfig).where(ToastSyncConfig.is_active.is_(True))
        )
        return result.scalars().all()

    # ------------------------------------------------------------------
    # SyncJob
    # ------------------------------------------------------------------

    async def create_sync_job(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
        job_type: str,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        triggered_by: Optional[uuid.UUID] = None,
    ) -> ToastSyncJob:
        job = ToastSyncJob(
            tenant_id=tenant_id,
            location_id=location_id,
            job_type=job_type,
            status="pending",
            date_from=date_from,
            date_to=date_to,
            triggered_by=triggered_by,
        )
        self._db.add(job)
        await self._db.flush()
        return job

    async def get_sync_job(
        self, tenant_id: uuid.UUID, job_id: uuid.UUID
    ) -> Optional[ToastSyncJob]:
        result = await self._db.execute(
            select(ToastSyncJob).where(
                ToastSyncJob.tenant_id == tenant_id,
                ToastSyncJob.id == job_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_sync_jobs(
        self,
        tenant_id: uuid.UUID,
        location_id: Optional[uuid.UUID] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[ToastSyncJob], int]:
        q = select(ToastSyncJob).where(ToastSyncJob.tenant_id == tenant_id)
        if location_id:
            q = q.where(ToastSyncJob.location_id == location_id)
        q = q.order_by(ToastSyncJob.created_at.desc()).limit(limit).offset(offset)
        result = await self._db.execute(q)
        rows = result.scalars().all()

        from sqlalchemy import func, select as sa_select
        count_q = sa_select(func.count()).select_from(ToastSyncJob).where(
            ToastSyncJob.tenant_id == tenant_id
        )
        if location_id:
            count_q = count_q.where(ToastSyncJob.location_id == location_id)
        total = (await self._db.execute(count_q)).scalar_one()
        return rows, total

    async def update_job_status(
        self,
        job_id: uuid.UUID,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
        orders_synced: int = 0,
        employees_synced: int = 0,
        time_entries_synced: int = 0,
    ) -> None:
        values: dict = {"status": status}
        if started_at:
            values["started_at"] = started_at
        if completed_at:
            values["completed_at"] = completed_at
        if error_message is not None:
            values["error_message"] = error_message
        if orders_synced:
            values["orders_synced"] = orders_synced
        if employees_synced:
            values["employees_synced"] = employees_synced
        if time_entries_synced:
            values["time_entries_synced"] = time_entries_synced
        await self._db.execute(
            update(ToastSyncJob).where(ToastSyncJob.id == job_id).values(**values)
        )

    async def increment_orders_synced(self, job_id: uuid.UUID, delta: int) -> None:
        """Atomically add delta to orders_synced for live progress during historical import."""
        if delta <= 0:
            return
        await self._db.execute(
            update(ToastSyncJob)
            .where(ToastSyncJob.id == job_id)
            .values(orders_synced=ToastSyncJob.orders_synced + delta)
        )

    # ------------------------------------------------------------------
    # Orders — upsert on (tenant_id, toast_guid)
    # ------------------------------------------------------------------

    async def upsert_order(self, row: dict) -> uuid.UUID:
        update_fields = {
            k: row[k]
            for k in (
                "is_void", "amount", "net_amount", "void_amount",
                "tax_amount", "tip_amount", "discount_amount", "refund_amount",
                "status", "closed_at", "paid_at", "raw_data",
            )
            if k in row
        }
        stmt = (
            pg_insert(ToastOrder)
            .values(**row)
            .on_conflict_do_update(
                constraint="uq_toast_order_guid",
                set_=update_fields,
            )
            .returning(ToastOrder.id)
        )
        result = await self._db.execute(stmt)
        returned = result.fetchone()
        if returned:
            return returned[0]
        existing = await self._db.execute(
            select(ToastOrder.id).where(
                ToastOrder.tenant_id == row["tenant_id"],
                ToastOrder.toast_guid == row["toast_guid"],
            )
        )
        return existing.scalar_one()

    async def upsert_order_item(self, row: dict) -> None:
        stmt = pg_insert(ToastOrderItem).values(**row)
        # Update money/qty/name on re-sync so price-mapping fixes self-heal
        # historical rows (previously do_nothing left stale values behind).
        stmt = stmt.on_conflict_do_update(
            constraint="uq_toast_order_item_guid",
            set_={
                "name": stmt.excluded.name,
                "quantity": stmt.excluded.quantity,
                "unit_price": stmt.excluded.unit_price,
                "pre_discount_price": stmt.excluded.pre_discount_price,
                "tax_amount": stmt.excluded.tax_amount,
                "discount_amount": stmt.excluded.discount_amount,
                "is_void": stmt.excluded.is_void,
                "void_reason": stmt.excluded.void_reason,
                "menu_item_guid": stmt.excluded.menu_item_guid,
            },
        )
        await self._db.execute(stmt)

    async def upsert_payment(self, row: dict) -> None:
        stmt = (
            pg_insert(ToastPayment)
            .values(**row)
            .on_conflict_do_nothing(constraint="uq_toast_payment_guid")
        )
        await self._db.execute(stmt)

    # ------------------------------------------------------------------
    # Employees + Time entries
    # ------------------------------------------------------------------

    async def upsert_employee(self, row: dict) -> uuid.UUID:
        stmt = (
            pg_insert(ToastEmployee)
            .values(**row)
            .on_conflict_do_update(
                constraint="uq_toast_employee_guid",
                set_={
                    "first_name": row["first_name"],
                    "last_name": row["last_name"],
                    "email": row.get("email"),
                    "job_codes": row.get("job_codes"),
                    "is_deleted": row.get("is_deleted", False),
                },
            )
            .returning(ToastEmployee.id)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def upsert_time_entry(self, row: dict) -> None:
        stmt = (
            pg_insert(ToastTimeEntry)
            .values(**row)
            .on_conflict_do_nothing(constraint="uq_toast_time_entry_guid")
        )
        await self._db.execute(stmt)

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    async def upsert_menu(self, row: dict) -> uuid.UUID:
        stmt = (
            pg_insert(ToastMenu)
            .values(**row)
            .on_conflict_do_update(
                constraint="uq_toast_menu_guid",
                set_={"name": row["name"], "description": row.get("description"), "is_active": row.get("is_active", True)},
            )
            .returning(ToastMenu.id)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def upsert_menu_item(self, row: dict) -> None:
        stmt = (
            pg_insert(ToastMenuItem)
            .values(**row)
            .on_conflict_do_update(
                constraint="uq_toast_menu_item_guid",
                set_={
                    "name": row["name"],
                    "description": row.get("description"),
                    "price": row.get("price"),
                    "category": row.get("category"),
                    "is_active": row.get("is_active", True),
                },
            )
        )
        await self._db.execute(stmt)
