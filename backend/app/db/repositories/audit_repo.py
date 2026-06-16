import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditLog


class AuditRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def log(
        self,
        tenant_id: uuid.UUID,
        action: str,
        *,
        user_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        old_value: dict | None = None,
        new_value: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        entry = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._db.add(entry)
        # No flush — committed with session transaction
