"""
Toast POS API client.

Auth: client-credentials OAuth (TOAST_MACHINE_CLIENT).
Token cached in Redis with TTL = expiresIn - 60s.
All financial amounts come back in cents (integer) — converted to Decimal here.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

TOAST_API_BASE = "https://ws-api.toasttab.com"
TOAST_AUTH_URL = f"{TOAST_API_BASE}/authentication/v1/authentication/login"

# Redis key prefix for cached access tokens
_TOKEN_KEY_PREFIX = "toast_token"


class ToastAuthError(Exception):
    pass


class ToastAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class ToastClient:
    """
    Per-location Toast API client.

    Usage:
        async with ToastClient(client_id, client_secret, restaurant_guid, location_id) as client:
            orders = await client.get_orders(date_from, date_to)
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        restaurant_guid: str,
        location_id: UUID,
        redis_client: Any = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._restaurant_guid = restaurant_guid
        self._location_id = str(location_id)
        self._redis = redis_client
        self._http: Optional[httpx.AsyncClient] = None
        self._access_token: Optional[str] = None

    async def __aenter__(self) -> "ToastClient":
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=10),
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._http:
            await self._http.aclose()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _redis_token_key(self) -> str:
        return f"{_TOKEN_KEY_PREFIX}:{self._location_id}"

    async def _get_cached_token(self) -> Optional[str]:
        if self._redis is None:
            return None
        try:
            token = await self._redis.get(self._redis_token_key())
            return token.decode() if token else None
        except Exception:
            return None

    async def _cache_token(self, token: str, expires_in: int) -> None:
        if self._redis is None:
            return
        ttl = max(expires_in - 60, 30)
        try:
            await self._redis.setex(self._redis_token_key(), ttl, token)
        except Exception:
            pass  # cache miss is non-fatal

    async def _authenticate(self) -> str:
        cached = await self._get_cached_token()
        if cached:
            return cached

        assert self._http is not None
        try:
            resp = await self._http.post(
                TOAST_AUTH_URL,
                json={
                    "clientId": self._client_id,
                    "clientSecret": self._client_secret,
                    "userAccessType": "TOAST_MACHINE_CLIENT",
                },
                headers={"Content-Type": "application/json"},
            )
        except httpx.RequestError as e:
            raise ToastAuthError(f"Network error during auth: {e}") from e

        if resp.status_code != 200:
            raise ToastAuthError(
                f"Toast auth failed: HTTP {resp.status_code} — {resp.text[:200]}"
            )

        data = resp.json()
        token_data = data.get("token", {})
        access_token = token_data.get("accessToken")
        expires_in = token_data.get("expiresIn", 3600)

        if not access_token:
            raise ToastAuthError("Toast auth response missing accessToken")

        await self._cache_token(access_token, expires_in)
        return access_token

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        retries: int = 3,
    ) -> Any:
        assert self._http is not None
        token = await self._authenticate()
        headers = {
            "Authorization": f"Bearer {token}",
            "Toast-Restaurant-External-ID": self._restaurant_guid,
        }

        url = f"{TOAST_API_BASE}{path}"
        for attempt in range(retries):
            try:
                resp = await self._http.request(
                    method, url, params=params, headers=headers
                )
            except httpx.RequestError as e:
                if attempt == retries - 1:
                    raise ToastAPIError(f"Network error: {e}") from e
                await _async_sleep(2 ** attempt)
                continue

            if resp.status_code == 401:
                # Token may have expired; invalidate cache and retry once
                if self._redis:
                    try:
                        await self._redis.delete(self._redis_token_key())
                    except Exception:
                        pass
                self._access_token = None
                token = await self._authenticate()
                headers["Authorization"] = f"Bearer {token}"
                continue

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                await _async_sleep(retry_after)
                continue

            if resp.status_code >= 500 and attempt < retries - 1:
                await _async_sleep(2 ** attempt)
                continue

            if resp.status_code >= 400:
                raise ToastAPIError(
                    f"Toast API error {resp.status_code}: {resp.text[:300]}",
                    status_code=resp.status_code,
                )

            return resp.json()

        raise ToastAPIError("Toast API request failed after retries")

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def get_orders(
        self,
        date_from: datetime,
        date_to: datetime,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Paginate through orders in [date_from, date_to].
        ordersBulk may return either GUID strings or full order objects depending
        on the Toast API version/config. Handle both cases.
        """
        all_guids: list[str] = []
        all_orders: list[dict[str, Any]] = []
        page = 1

        while True:
            params = {
                "startDate": _to_toast_ts(date_from),
                "endDate": _to_toast_ts(date_to),
                "pageSize": page_size,
                "page": page,
            }
            data = await self._request("GET", "/orders/v2/ordersBulk", params=params)
            if not data:
                break
            items = data if isinstance(data, list) else data.get("orders", [])
            if not items:
                break

            for item in items:
                if isinstance(item, str):
                    all_guids.append(item)
                elif isinstance(item, dict):
                    # ordersBulk returned full order objects directly
                    all_orders.append(item)

            logger.debug(
                "toast_orders_bulk_page",
                page=page,
                items=len(items),
                guids_so_far=len(all_guids),
                orders_so_far=len(all_orders),
            )
            if len(items) < page_size:
                break
            page += 1

        # Fetch full order objects for any GUIDs collected
        for guid in all_guids:
            try:
                order = await self._request("GET", f"/orders/v2/orders/{guid}")
                if isinstance(order, dict):
                    all_orders.append(order)
                elif isinstance(order, list) and order:
                    all_orders.extend([o for o in order if isinstance(o, dict)])
            except ToastAPIError as e:
                logger.warning("toast_order_fetch_failed", guid=guid, error=str(e))
                continue

        logger.info(
            "toast_get_orders_complete",
            date_from=str(date_from),
            date_to=str(date_to),
            guids_fetched=len(all_guids),
            orders_returned=len(all_orders),
        )
        return all_orders

    # ------------------------------------------------------------------
    # Labor
    # ------------------------------------------------------------------

    async def get_time_entries(
        self,
        date_from: datetime,
        date_to: datetime,
    ) -> list[dict[str, Any]]:
        params = {
            "startDate": _to_toast_ts(date_from),
            "endDate": _to_toast_ts(date_to),
        }
        data = await self._request("GET", "/labor/v1/timeEntries", params=params)
        return data if isinstance(data, list) else []

    async def get_employees(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/labor/v1/employees")
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    async def get_menus(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/config/v2/menus")
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Restaurant info
    # ------------------------------------------------------------------

    async def get_restaurant_info(self) -> dict[str, Any]:
        data = await self._request("GET", "/config/v2/restaurants")
        if isinstance(data, list) and data:
            return data[0]
        return {}

    # ------------------------------------------------------------------
    # Dining options (channel names: Dine In / Take Out / Uber / Skip / ...)
    # ------------------------------------------------------------------

    async def get_dining_options(self) -> list[dict[str, Any]]:
        """Dining-option config. Orders reference these by guid only, so we
        resolve guid→name here to label revenue by channel."""
        data = await self._request("GET", "/config/v2/diningOptions")
        return data if isinstance(data, list) else []


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _to_toast_ts(dt: datetime) -> str:
    """ISO 8601 UTC string for Toast API parameters."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def cents_to_decimal(value: Any) -> Optional[Decimal]:
    """Toast returns money as integer cents. Convert to Decimal dollars."""
    if value is None:
        return None
    try:
        return Decimal(str(value)) / Decimal("100")
    except Exception:
        return None


async def _async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
