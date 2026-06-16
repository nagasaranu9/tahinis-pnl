"""
Tests that upsert operations are idempotent — running twice produces same row count.
Uses real async DB session against test DB.
"""
import uuid
import pytest
from decimal import Decimal
from datetime import UTC, datetime

from app.db.repositories.toast_repo import ToastRepository


@pytest.mark.asyncio
async def test_upsert_order_idempotent(db_session, tenant, owner_user):
    """Inserting same toast_guid twice must not create duplicate rows."""
    from sqlalchemy import select, func
    from app.db.models.toast import ToastOrder

    repo = ToastRepository(db_session)
    location_id = uuid.uuid4()

    row = {
        "id": uuid.uuid4(),
        "tenant_id": tenant.id,
        "location_id": location_id,
        "toast_guid": "order-abc-123",
        "toast_restaurant_guid": "rest-guid",
        "amount": Decimal("42.00"),
        "currency_code": "CAD",
        "is_void": False,
    }

    await repo.upsert_order(row)
    await db_session.commit()

    # Second upsert — same guid, different id
    row2 = {**row, "id": uuid.uuid4(), "amount": Decimal("99.00")}
    await repo.upsert_order(row2)
    await db_session.commit()

    count = await db_session.scalar(
        select(func.count()).select_from(ToastOrder).where(
            ToastOrder.tenant_id == tenant.id,
            ToastOrder.toast_guid == "order-abc-123",
        )
    )
    assert count == 1  # ON CONFLICT DO NOTHING — first row wins


@pytest.mark.asyncio
async def test_upsert_employee_updates_on_conflict(db_session, tenant):
    """Employee upsert should update name on re-sync (ON CONFLICT DO UPDATE)."""
    repo = ToastRepository(db_session)
    location_id = uuid.uuid4()

    row = {
        "id": uuid.uuid4(),
        "tenant_id": tenant.id,
        "location_id": location_id,
        "toast_guid": "emp-guid-xyz",
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice@example.com",
        "job_codes": "[]",
        "is_deleted": False,
    }
    emp_id = await repo.upsert_employee(row)
    await db_session.commit()

    updated_row = {**row, "id": uuid.uuid4(), "first_name": "Alicia"}
    emp_id2 = await repo.upsert_employee(updated_row)
    await db_session.commit()

    from sqlalchemy import select
    from app.db.models.toast import ToastEmployee
    result = await db_session.execute(
        select(ToastEmployee).where(
            ToastEmployee.tenant_id == tenant.id,
            ToastEmployee.toast_guid == "emp-guid-xyz",
        )
    )
    employees = result.scalars().all()
    assert len(employees) == 1
    assert employees[0].first_name == "Alicia"


@pytest.mark.asyncio
async def test_sync_job_lifecycle(db_session, tenant):
    repo = ToastRepository(db_session)
    location_id = uuid.uuid4()

    job = await repo.create_sync_job(
        tenant_id=tenant.id,
        location_id=location_id,
        job_type="incremental",
        date_from=datetime(2024, 1, 1, tzinfo=UTC),
        date_to=datetime(2024, 1, 2, tzinfo=UTC),
    )
    await db_session.commit()
    assert job.status == "pending"

    await repo.update_job_status(
        job.id, "running", started_at=datetime.now(UTC)
    )
    await db_session.commit()

    await repo.update_job_status(
        job.id, "complete",
        completed_at=datetime.now(UTC),
        orders_synced=150,
    )
    await db_session.commit()

    fetched = await repo.get_sync_job(tenant.id, job.id)
    assert fetched is not None
    assert fetched.status == "complete"
    assert fetched.orders_synced == 150
