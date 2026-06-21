"""
ToastSyncService — orchestrates historical import and incremental sync.

Historical: chunked monthly from historical_import_from to now.
Incremental: last_synced_at cursor → now.
Upsert-safe: INSERT ... ON CONFLICT DO NOTHING on toast_guid.
Never overwrites historical records for orders.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_value
from app.db.models.integration import IntegrationCredential
from app.db.repositories.toast_repo import ToastRepository
from app.services.toast.client import ToastClient, cents_to_decimal

logger = structlog.get_logger(__name__)

CHUNK_DAYS = 30  # historical import chunk size


def _dict_get(value: object, key: str) -> object:
    """Safe nested get — returns None if value is not a dict."""
    if isinstance(value, dict):
        return value.get(key)
    return None


def _str_or_guid(value: object) -> Optional[str]:
    """Return string as-is; extract guid from dict; None otherwise."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("guid")
    return None


class ToastSyncService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ToastRepository(db)

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def run_incremental_sync(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
        job_id: uuid.UUID,
        redis_client=None,
    ) -> dict:
        config = await self._repo.get_sync_config(tenant_id, location_id)
        if not config or not config.is_active:
            raise ValueError("No active Toast config for location")

        now = datetime.now(UTC)
        date_from = config.last_synced_at or (now - timedelta(days=1))
        date_to = now

        log = logger.bind(tenant_id=str(tenant_id), location_id=str(location_id), job_id=str(job_id))
        log.info("toast_incremental_sync_start", date_from=str(date_from), date_to=str(date_to))

        creds = await self._load_credentials(config.integration_credential_id)
        counts = await self._sync_range(
            tenant_id, location_id, creds, config.toast_restaurant_guid,
            date_from, date_to, job_id, redis_client
        )

        await self._repo.update_last_synced(tenant_id, location_id, now)
        await self._db.commit()

        log.info("toast_incremental_sync_complete", **counts)
        return counts

    async def run_historical_import(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
        job_id: uuid.UUID,
        redis_client=None,
    ) -> dict:
        config = await self._repo.get_sync_config(tenant_id, location_id)
        if not config or not config.is_active:
            raise ValueError("No active Toast config for location")

        now = datetime.now(UTC)
        # Default backfill floor: Jan 1 2026 (start of current fiscal year), not a
        # rolling 365-day window. Smaller, deterministic range → less memory, no
        # re-importing stale prior-year data the operator doesn't report on.
        default_start = datetime(2026, 1, 1, tzinfo=UTC)
        start = config.historical_import_from or default_start
        # Guard: never start in the future (e.g. brand-new location created later).
        if start > now:
            start = now - timedelta(days=1)
        creds = await self._load_credentials(config.integration_credential_id)

        log = logger.bind(tenant_id=str(tenant_id), location_id=str(location_id))
        log.info("toast_historical_import_start", from_date=str(start))

        total_counts: dict = {"orders_synced": 0, "employees_synced": 0, "time_entries_synced": 0}

        # Chunk into CHUNK_DAYS windows
        chunk_start = start
        while chunk_start < now:
            chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), now)
            log.info("toast_historical_chunk", start=str(chunk_start), end=str(chunk_end))

            counts = await self._sync_range(
                tenant_id, location_id, creds, config.toast_restaurant_guid,
                chunk_start, chunk_end, job_id, redis_client,
                sync_employees=(chunk_start == start),  # only first chunk
            )
            for k in total_counts:
                total_counts[k] += counts.get(k, 0)

            # Update running total so the UI banner shows live progress every 5s.
            await self._repo.increment_orders_synced(job_id, counts.get("orders_synced", 0))
            await self._db.commit()
            chunk_start = chunk_end

        await self._repo.mark_historical_complete(tenant_id, location_id)
        await self._repo.update_last_synced(tenant_id, location_id, now)
        await self._db.commit()

        log.info("toast_historical_import_complete", **total_counts)
        return total_counts

    async def run_historical_chunk(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
        job_id: uuid.UUID,
        cursor: Optional[datetime] = None,
        redis_client=None,
    ) -> dict:
        """Sync ONE month-window of historical data, then report the next cursor.

        Returns {"counts": {...}, "next_cursor": datetime | None, "done": bool}.
        Each chunk is its own short Celery task → survives worker restarts and
        shows live progress. The task chains the next chunk until done is True.
        """
        config = await self._repo.get_sync_config(tenant_id, location_id)
        if not config or not config.is_active:
            raise ValueError("No active Toast config for location")

        now = datetime.now(UTC)
        default_start = datetime(2026, 1, 1, tzinfo=UTC)
        start = config.historical_import_from or default_start
        if start > now:
            start = now - timedelta(days=1)

        chunk_start = cursor or start
        is_first = chunk_start == start

        log = logger.bind(tenant_id=str(tenant_id), location_id=str(location_id))

        # Already past the end → nothing left, finalize.
        if chunk_start >= now:
            await self._repo.mark_historical_complete(tenant_id, location_id)
            await self._repo.update_last_synced(tenant_id, location_id, now)
            await self._db.commit()
            log.info("toast_historical_chunk_done")
            return {"counts": {}, "next_cursor": None, "done": True}

        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), now)
        log.info("toast_historical_chunk", start=str(chunk_start), end=str(chunk_end))

        creds = await self._load_credentials(config.integration_credential_id)
        counts = await self._sync_range(
            tenant_id, location_id, creds, config.toast_restaurant_guid,
            chunk_start, chunk_end, job_id, redis_client,
            sync_employees=is_first,
        )

        await self._repo.increment_orders_synced(job_id, counts.get("orders_synced", 0))
        await self._db.commit()

        done = chunk_end >= now
        if done:
            await self._repo.mark_historical_complete(tenant_id, location_id)
            await self._repo.update_last_synced(tenant_id, location_id, now)
            await self._db.commit()
            log.info("toast_historical_chunk_final", **counts)

        return {"counts": counts, "next_cursor": None if done else chunk_end, "done": done}

    # ------------------------------------------------------------------
    # Core sync
    # ------------------------------------------------------------------

    async def backfill_dining_options(
        self, tenant_id: uuid.UUID, location_id: uuid.UUID,
    ) -> dict:
        """Repopulate dining_option on existing orders (channel labels) from
        their stored raw_data, resolving guid→name via the dining-options
        config. Fixes rows synced before guid resolution existed, without
        re-hitting the orders API (upsert is ON CONFLICT DO NOTHING)."""
        from sqlalchemy import select, update as sql_update

        from app.db.models.toast import ToastOrder

        config = await self._repo.get_sync_config(tenant_id, location_id)
        if not config or not config.is_active:
            raise ValueError("No active Toast config for location")
        creds = await self._load_credentials(config.integration_credential_id)

        dining_map: dict[str, str] = {}
        async with ToastClient(
            client_id=creds["client_id"],
            client_secret=creds["client_secret"],
            restaurant_guid=config.toast_restaurant_guid,
            location_id=location_id,
        ) as client:
            for opt in await client.get_dining_options():
                if opt.get("guid") and opt.get("name"):
                    dining_map[opt["guid"]] = opt["name"]

        rows = (await self._db.execute(
            select(ToastOrder.id, ToastOrder.raw_data).where(
                ToastOrder.tenant_id == tenant_id,
                ToastOrder.location_id == location_id,
            )
        )).all()

        updated = 0
        for row in rows:
            try:
                raw = json.loads(row.raw_data) if row.raw_data else {}
            except (ValueError, TypeError):
                continue
            opt = raw.get("diningOption") or {}
            name = _dict_get(opt, "name")
            if not name:
                name = dining_map.get(_dict_get(opt, "guid") or "")
            if not name:
                continue
            await self._db.execute(
                sql_update(ToastOrder).where(ToastOrder.id == row.id).values(dining_option=name)
            )
            updated += 1

        await self._db.commit()
        logger.info("toast_backfill_dining_options", scanned=len(rows), updated=updated,
                    map_size=len(dining_map))
        return {"scanned": len(rows), "updated": updated, "dining_options": len(dining_map)}

    async def _sync_range(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
        creds: dict,
        restaurant_guid: str,
        date_from: datetime,
        date_to: datetime,
        job_id: uuid.UUID,
        redis_client=None,
        sync_employees: bool = True,
    ) -> dict:
        orders_count = 0
        employees_count = 0
        time_entries_count = 0

        async with ToastClient(
            client_id=creds["client_id"],
            client_secret=creds["client_secret"],
            restaurant_guid=restaurant_guid,
            location_id=location_id,
            redis_client=redis_client,
        ) as client:
            # Dining-option guid→name map (channel labels live here; orders
            # reference dining options by guid only).
            dining_map: dict[str, str] = {}
            try:
                for opt in await client.get_dining_options():
                    guid = opt.get("guid")
                    name = opt.get("name")
                    if guid and name:
                        dining_map[guid] = name
            except Exception as exc:  # config call is best-effort
                logger.warning("toast_dining_options_fetch_failed", error=str(exc))

            # Orders
            raw_orders = await client.get_orders(date_from, date_to)
            for raw in raw_orders:
                await self._upsert_order(tenant_id, location_id, raw, dining_map)
                orders_count += 1

            # Employees (first chunk of historical, or every incremental)
            if sync_employees:
                raw_employees = await client.get_employees()
                emp_guid_to_id: dict[str, uuid.UUID] = {}
                for raw_emp in raw_employees:
                    emp_id = await self._upsert_employee(tenant_id, location_id, raw_emp)
                    emp_guid_to_id[raw_emp.get("guid", "")] = emp_id
                    employees_count += 1

                # Time entries
                raw_entries = await client.get_time_entries(date_from, date_to)
                for raw_entry in raw_entries:
                    emp_guid = (raw_entry.get("employee") or {}).get("guid", "")
                    emp_id = emp_guid_to_id.get(emp_guid)
                    if emp_id:
                        await self._upsert_time_entry(tenant_id, location_id, emp_id, raw_entry)
                        time_entries_count += 1

        return {
            "orders_synced": orders_count,
            "employees_synced": employees_count,
            "time_entries_synced": time_entries_count,
        }

    # ------------------------------------------------------------------
    # Mappers
    # ------------------------------------------------------------------

    async def _upsert_order(
        self, tenant_id: uuid.UUID, location_id: uuid.UUID, raw: dict,
        dining_map: dict[str, str] | None = None,
    ) -> uuid.UUID:
        # Resolve channel: prefer embedded name, else guid→name from config map.
        dining_opt = raw.get("diningOption") or {}
        dining_name = _dict_get(dining_opt, "name")
        if not dining_name and dining_map:
            dining_name = dining_map.get(_dict_get(dining_opt, "guid") or "")
        order_row = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "location_id": location_id,
            "toast_guid": raw.get("guid", ""),
            "toast_restaurant_guid": raw.get("restaurantGuid", ""),
            "opened_at": _parse_ts(raw.get("openedDate")),
            "closed_at": _parse_ts(raw.get("closedDate")),
            "paid_at": _parse_ts(raw.get("paidDate")),
            "business_date": str(raw.get("businessDate", "")),
            "display_number": raw.get("displayNumber"),
            "order_source": _dict_get(raw.get("source"), "sourceType"),
            "dining_option": dining_name,
            "table_name": raw.get("tableName"),
            "server_guid": _dict_get(raw.get("server"), "guid"),
            "amount": _sum_check_field(raw, "totalAmount"),
            "tax_amount": _sum_check_field(raw, "taxAmount"),
            "tip_amount": _sum_payment_field(raw, "tipAmount"),
            "discount_amount": _sum_applied_discounts(raw),
            "refund_amount": _sum_payment_refunds(raw),
            "void_amount": _sum_voided_selections(raw),
            "net_amount": _net_amount_after_voids(raw),
            "is_void": bool(raw.get("voided") or False),
            "guest_count": raw.get("numberOfGuests"),
            "raw_data": json.dumps(raw),
        }
        order_id = await self._repo.upsert_order(order_row)

        # Items — only first check's selections
        checks = raw.get("checks") or []
        first_check = checks[0] if isinstance(checks, list) and checks and isinstance(checks[0], dict) else {}
        for item in first_check.get("selections", []) or []:
            if not isinstance(item, dict):
                continue
            await self._repo.upsert_order_item({
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "order_id": order_id,
                "location_id": location_id,
                "toast_guid": item.get("guid", ""),
                "menu_item_guid": _dict_get(item.get("itemGroup"), "guid"),
                "name": item.get("displayName", ""),
                "quantity": item.get("quantity"),
                "unit_price": cents_to_decimal(item.get("unitOfMeasure")),
                "pre_discount_price": cents_to_decimal(item.get("preDiscountPrice")),
                "tax_amount": cents_to_decimal(item.get("tax")),
                "discount_amount": cents_to_decimal(item.get("appliedDiscountAmount")),
                "void_reason": _str_or_guid(item.get("voidReason")),
                "is_void": bool(item.get("voided") or False),
            })

        # Payments
        for check in checks:
            if not isinstance(check, dict):
                continue
            for payment in check.get("payments", []) or []:
                if not isinstance(payment, dict):
                    continue
                await self._repo.upsert_payment({
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "order_id": order_id,
                    "location_id": location_id,
                    "toast_guid": payment.get("guid", ""),
                    "payment_type": payment.get("type"),
                    "card_type": payment.get("cardType"),
                    "amount": cents_to_decimal(payment.get("amount")),
                    "tip_amount": cents_to_decimal(payment.get("tipAmount")),
                    "refund_amount": cents_to_decimal(payment.get("refundAmount")),
                    "paid_at": _parse_ts(payment.get("paidDate")),
                    "is_refund": bool(payment.get("refund") or False),
                })

        return order_id

    async def _upsert_employee(
        self, tenant_id: uuid.UUID, location_id: uuid.UUID, raw: dict
    ) -> uuid.UUID:
        job_codes = json.dumps([j.get("guid") for j in raw.get("jobReferences", [])])
        row = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "location_id": location_id,
            "toast_guid": raw.get("guid", ""),
            "first_name": raw.get("firstName"),
            "last_name": raw.get("lastName"),
            "email": raw.get("email"),
            "job_codes": job_codes,
            "is_deleted": raw.get("deleted", False),
        }
        return await self._repo.upsert_employee(row)

    async def _upsert_time_entry(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
        employee_id: uuid.UUID,
        raw: dict,
    ) -> None:
        row = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "employee_id": employee_id,
            "location_id": location_id,
            "toast_guid": raw.get("guid", ""),
            "in_date": _parse_ts(raw.get("inDate")),
            "out_date": _parse_ts(raw.get("outDate")),
            "business_date": str(raw.get("businessDate", "")),
            "job_code": (raw.get("jobReference") or {}).get("guid"),
            "hours_regular": raw.get("regularHours"),
            "hours_overtime": raw.get("overtimeHours"),
            "declared_cash_tips": cents_to_decimal(raw.get("declaredCashTips")),
            "non_cash_tips": cents_to_decimal(raw.get("nonCashTips")),
            "hourly_wage": raw.get("hourlyWage"),
            "auto_clocked_out": raw.get("autoClockedOut", False),
        }
        await self._repo.upsert_time_entry(row)

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    async def _load_credentials(self, credential_id: Optional[uuid.UUID]) -> dict:
        if not credential_id:
            raise ValueError("No integration credential linked to Toast config")
        from sqlalchemy import select
        result = await self._db.execute(
            select(IntegrationCredential).where(IntegrationCredential.id == credential_id)
        )
        cred = result.scalar_one_or_none()
        if not cred:
            raise ValueError(f"IntegrationCredential {credential_id} not found")
        return {
            "client_id": decrypt_value(cred.access_token_encrypted),
            "client_secret": decrypt_value(cred.refresh_token_encrypted),
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_ts(value: Optional[str | int]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=UTC)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _sum_check_field(raw: dict, field: str) -> Optional[Decimal]:
    """Sum a dollar-valued field across all checks."""
    total = Decimal("0")
    found = False
    for check in raw.get("checks", []) or []:
        if not isinstance(check, dict):
            continue
        val = check.get(field)
        if val is not None:
            total += Decimal(str(val))
            found = True
    return total if found else None


def _sum_payment_field(raw: dict, field: str) -> Optional[Decimal]:
    """Sum a dollar-valued field across all payments in all checks."""
    total = Decimal("0")
    found = False
    for check in raw.get("checks", []) or []:
        if not isinstance(check, dict):
            continue
        for payment in check.get("payments", []) or []:
            if not isinstance(payment, dict):
                continue
            val = payment.get(field)
            if val is not None:
                total += Decimal(str(val))
                found = True
    return total if found else None


def _sum_applied_discounts(raw: dict) -> Optional[Decimal]:
    """Sum discountAmount from check-level and selection-level appliedDiscounts."""
    total = Decimal("0")
    found = False
    for check in raw.get("checks", []) or []:
        if not isinstance(check, dict):
            continue
        for disc in check.get("appliedDiscounts", []) or []:
            if isinstance(disc, dict):
                val = disc.get("discountAmount") or disc.get("amount")
                if val is not None:
                    total += Decimal(str(val))
                    found = True
        for sel in check.get("selections", []) or []:
            if not isinstance(sel, dict):
                continue
            for disc in sel.get("appliedDiscounts", []) or []:
                if isinstance(disc, dict):
                    val = disc.get("discountAmount") or disc.get("amount")
                    if val is not None:
                        total += Decimal(str(val))
                        found = True
    return total if found else None


def _sum_payment_refunds(raw: dict) -> Optional[Decimal]:
    """Sum refundAmount across payments that are refunds."""
    total = Decimal("0")
    found = False
    for check in raw.get("checks", []) or []:
        if not isinstance(check, dict):
            continue
        for payment in check.get("payments", []) or []:
            if not isinstance(payment, dict):
                continue
            if payment.get("refund"):
                val = payment.get("refundAmount")
                if val is not None:
                    total += Decimal(str(val))
                    found = True
    return total if found else None


def _extract_refund_amount(raw: dict) -> Optional[int]:
    total = 0
    for check in raw.get("checks", []) or []:
        if not isinstance(check, dict):
            continue
        for payment in check.get("payments", []) or []:
            if not isinstance(payment, dict):
                continue
            if payment.get("refund"):
                total += payment.get("refundAmount", 0) or 0
    return total if total else None


def _extract_void_amount(raw: dict) -> Optional[int]:
    if raw.get("voided"):
        return raw.get("amount")
    return None


def _net_amount_after_voids(raw: dict) -> Optional[Decimal]:
    """checks[].amount includes voided selections; subtract them to match Toast net sales."""
    gross = _sum_check_field(raw, "amount")
    if gross is None:
        return None
    voids = _sum_voided_selections(raw)
    return gross - (voids or Decimal("0"))


def _sum_voided_selections(raw: dict) -> Optional[Decimal]:
    """Sum preDiscountPrice for all voided selections across all checks."""
    total = Decimal("0")
    found = False
    for check in raw.get("checks", []) or []:
        if not isinstance(check, dict):
            continue
        for sel in check.get("selections", []) or []:
            if not isinstance(sel, dict):
                continue
            if sel.get("voided"):
                val = sel.get("preDiscountPrice")
                if val is not None:
                    total += Decimal(str(val))
                    found = True
    return total if found else None
