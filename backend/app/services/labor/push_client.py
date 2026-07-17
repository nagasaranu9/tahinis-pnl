"""
PushOperations platform API client.

Auth: static partner-issued bearer token (settings.PUSH_API_TOKEN). Unlike
Toast there is no OAuth exchange and no token refresh — the token is long-lived
and issued out-of-band by PushOperations to approved partners.

Two API constraints drive this design:

1. Labour endpoints reject any range wider than 2 days apart
   ("The start and end dates must not be more than 2 days apart"), so a
   historical backfill must be chunked. `iter_date_chunks` does that.
2. Rate limits are 50 requests/minute and 600/hour, enforced per token unless
   a `Push-Company-Uuid` header scopes them per company — so we always send it.
   `_RateLimiter` keeps us under the minute cap; 429s are retried honoring the
   `X-RateLimit-Retry-After` header.

The token scope issued to this tenant does NOT include the department-level
endpoints (`/analytics/summary/labour-actuals`, `/departments`), which return
"Insufficient permissions". Labor is therefore built up from `/labour/employee`
and grouped by position rather than department.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterator

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

PUSH_API_BASE = "https://api.pushoperations.com/platform/api/v1"

# Hard API limit: start and end must be <= 2 days apart, so a request window
# covers at most 3 calendar dates (start, start+1, start+2).
MAX_LABOUR_RANGE_DAYS = 2

# Documented limits: 50/min, 600/hr. We pace against the minute window and
# leave headroom so a concurrent manual sync cannot tip us over.
_MAX_REQUESTS_PER_MINUTE = 40


class PushAuthError(Exception):
    """Token missing, rejected, or lacking scope for the requested endpoint."""


class PushAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class LabourRow:
    """One employee/day/labour-type row from GET /labour/employee."""

    business_date: date
    employee_id: int
    employee_name: str | None
    # 0 sentinel rather than None — this field is part of the storage upsert key.
    position_id: int
    position_name: str | None
    labour_type: str
    cost: Decimal
    hours: Decimal


def _to_money(value: Any) -> Decimal:
    """
    Convert an API numeric to 2dp Decimal.

    The API returns unrounded floats (153.84615384615). Going through str()
    rather than Decimal(float) avoids binary float artifacts before quantizing.
    """
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_hours(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def iter_date_chunks(
    start: date, end: date, max_span_days: int = MAX_LABOUR_RANGE_DAYS
) -> Iterator[tuple[date, date]]:
    """
    Split [start, end] into windows the labour endpoints accept.

    Each yielded window has (chunk_end - chunk_start).days <= max_span_days.
    Windows are inclusive and contiguous — no date is skipped or covered twice.
    """
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=max_span_days), end)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


class _RateLimiter:
    """Sliding-window limiter keeping us under the per-minute request cap."""

    def __init__(self, max_per_minute: int = _MAX_REQUESTS_PER_MINUTE) -> None:
        self._max = max_per_minute
        self._hits: deque[float] = deque()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            while self._hits and now - self._hits[0] >= 60:
                self._hits.popleft()
            if len(self._hits) < self._max:
                self._hits.append(now)
                return
            await asyncio.sleep(60 - (now - self._hits[0]) + 0.05)


class PushClient:
    """
    PushOperations API client for one company.

    Usage:
        async with PushClient(company_id=27336, company_uuid="3ce9...") as c:
            rows = await c.get_labour_by_employee(date(2026, 1, 1), date(2026, 1, 3))
    """

    def __init__(
        self,
        company_id: int,
        company_uuid: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._company_id = company_id
        self._company_uuid = company_uuid
        self._token = token or settings.PUSH_API_TOKEN
        if not self._token:
            raise PushAuthError("PUSH_API_TOKEN is not configured")
        self._timeout = timeout
        self._limiter = _RateLimiter()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "PushClient":
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        # Scopes rate limits per company instead of per token, so a second
        # company's backfill cannot starve this one.
        if self._company_uuid:
            headers["Push-Company-Uuid"] = self._company_uuid
        self._client = httpx.AsyncClient(
            base_url=PUSH_API_BASE, headers=headers, timeout=self._timeout
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: dict[str, Any], attempt: int = 0) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("PushClient must be used as an async context manager")

        await self._limiter.acquire()
        resp = await self._client.get(path, params=params)

        if resp.status_code == 429:
            if attempt >= 3:
                raise PushAPIError("Push rate limit exceeded after 3 retries", 429)
            # The API tells us exactly how long to wait; trust it over backoff.
            retry_after = int(resp.headers.get("X-RateLimit-Retry-After", "60"))
            logger.warning("push_rate_limited", path=path, retry_after=retry_after)
            await asyncio.sleep(retry_after + 1)
            return await self._get(path, params, attempt + 1)

        if resp.status_code in (401, 403):
            raise PushAuthError(f"Push auth failed on {path}: {resp.status_code}")

        if resp.status_code >= 500:
            if attempt >= 3:
                raise PushAPIError(f"Push server error on {path}", resp.status_code)
            await asyncio.sleep(2 ** attempt)
            return await self._get(path, params, attempt + 1)

        if resp.status_code >= 400:
            raise PushAPIError(f"Push error on {path}: {resp.text[:300]}", resp.status_code)

        body = resp.json()
        # The API returns HTTP 200 with a failure envelope for scope errors,
        # so status alone is not enough to tell success from denial.
        if isinstance(body, dict) and body.get("status") == "failed":
            message = body.get("message", "unknown error")
            if "permission" in message.lower():
                raise PushAuthError(f"Push token lacks scope for {path}: {message}")
            raise PushAPIError(f"Push returned failure on {path}: {message}")
        if isinstance(body, dict) and "errors" in body:
            raise PushAPIError(f"Push validation error on {path}: {body['errors']}")
        return body

    async def get_companies(self) -> list[dict[str, Any]]:
        body = await self._get(
            "/companies", {"include": "organization,location", "page": 1, "limit": 50}
        )
        return body.get("data", [])

    async def get_labour_by_employee(self, start: date, end: date) -> list[LabourRow]:
        """
        Fetch employee-grain labour for a range no wider than MAX_LABOUR_RANGE_DAYS.

        Callers backfilling a long period should drive this via iter_date_chunks.
        """
        if (end - start).days > MAX_LABOUR_RANGE_DAYS:
            raise ValueError(
                f"Push labour range {start}..{end} exceeds the {MAX_LABOUR_RANGE_DAYS}-day API limit"
            )
        body = await self._get(
            "/labour/employee",
            {
                "company": self._company_id,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "earnings-deductions": "true",
            },
        )
        rows: list[LabourRow] = []
        for item in body.get("data", []):
            rows.append(
                LabourRow(
                    business_date=date.fromisoformat(item["date"]),
                    employee_id=int(item["employeeId"]),
                    employee_name=item.get("employeeName"),
                    position_id=int(item.get("positionId") or 0),
                    position_name=item.get("positionName"),
                    labour_type=item.get("labourType") or "unknown",
                    cost=_to_money(item.get("costs")),
                    hours=_to_hours(item.get("hours")),
                )
            )
        return rows
