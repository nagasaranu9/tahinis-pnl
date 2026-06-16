"""
Unit tests for ToastClient.
Uses respx to mock HTTP — no real network calls.
"""
import pytest
import respx
import httpx
from decimal import Decimal
from datetime import datetime, timezone

from app.services.toast.client import ToastClient, cents_to_decimal, _to_toast_ts


MOCK_LOCATION_ID = "00000000-0000-0000-0000-000000000001"
MOCK_CLIENT_ID = "test_client"
MOCK_CLIENT_SECRET = "test_secret"
MOCK_RESTAURANT_GUID = "rest-guid-123"
MOCK_TOKEN = "mock_access_token_abc"

AUTH_RESPONSE = {
    "token": {
        "accessToken": MOCK_TOKEN,
        "expiresIn": 3600,
        "tokenType": "Bearer",
    }
}


@pytest.fixture
def mock_redis():
    class FakeRedis:
        def __init__(self):
            self._store = {}

        async def get(self, key):
            return self._store.get(key)

        async def setex(self, key, ttl, value):
            self._store[key] = value if isinstance(value, bytes) else value.encode()

        async def delete(self, key):
            self._store.pop(key, None)

    return FakeRedis()


@respx.mock
@pytest.mark.asyncio
async def test_authenticate_success(mock_redis):
    respx.post("https://ws-api.toasttab.com/authentication/v1/authentication/login").mock(
        return_value=httpx.Response(200, json=AUTH_RESPONSE)
    )

    async with ToastClient(
        MOCK_CLIENT_ID, MOCK_CLIENT_SECRET, MOCK_RESTAURANT_GUID,
        MOCK_LOCATION_ID, mock_redis
    ) as client:
        token = await client._authenticate()

    assert token == MOCK_TOKEN


@respx.mock
@pytest.mark.asyncio
async def test_token_cached_in_redis(mock_redis):
    auth_route = respx.post(
        "https://ws-api.toasttab.com/authentication/v1/authentication/login"
    ).mock(return_value=httpx.Response(200, json=AUTH_RESPONSE))

    async with ToastClient(
        MOCK_CLIENT_ID, MOCK_CLIENT_SECRET, MOCK_RESTAURANT_GUID,
        MOCK_LOCATION_ID, mock_redis
    ) as client:
        t1 = await client._authenticate()
        t2 = await client._authenticate()  # should use cache

    assert t1 == t2 == MOCK_TOKEN
    assert auth_route.call_count == 1  # only one real auth call


@respx.mock
@pytest.mark.asyncio
async def test_authenticate_failure_raises():
    from app.services.toast.client import ToastAuthError

    respx.post("https://ws-api.toasttab.com/authentication/v1/authentication/login").mock(
        return_value=httpx.Response(401, json={"message": "unauthorized"})
    )

    async with ToastClient(
        MOCK_CLIENT_ID, MOCK_CLIENT_SECRET, MOCK_RESTAURANT_GUID, MOCK_LOCATION_ID
    ) as client:
        with pytest.raises(ToastAuthError):
            await client._authenticate()


@respx.mock
@pytest.mark.asyncio
async def test_get_orders_pagination(mock_redis):
    respx.post("https://ws-api.toasttab.com/authentication/v1/authentication/login").mock(
        return_value=httpx.Response(200, json=AUTH_RESPONSE)
    )

    page1 = [{"guid": f"order-{i}", "amount": 1000} for i in range(100)]
    page2 = [{"guid": f"order-{i}", "amount": 1000} for i in range(100, 120)]

    call_count = 0

    def orders_response(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=page1 if call_count == 1 else page2)

    respx.get("https://ws-api.toasttab.com/orders/v2/ordersBulk").mock(side_effect=orders_response)

    async with ToastClient(
        MOCK_CLIENT_ID, MOCK_CLIENT_SECRET, MOCK_RESTAURANT_GUID,
        MOCK_LOCATION_ID, mock_redis
    ) as client:
        date_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2024, 1, 31, tzinfo=timezone.utc)
        orders = await client.get_orders(date_from, date_to, page_size=100)

    assert len(orders) == 120
    assert call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_retry_on_429(mock_redis):
    respx.post("https://ws-api.toasttab.com/authentication/v1/authentication/login").mock(
        return_value=httpx.Response(200, json=AUTH_RESPONSE)
    )

    call_count = 0

    def flaky_response(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=[])

    respx.get("https://ws-api.toasttab.com/orders/v2/ordersBulk").mock(side_effect=flaky_response)

    async with ToastClient(
        MOCK_CLIENT_ID, MOCK_CLIENT_SECRET, MOCK_RESTAURANT_GUID,
        MOCK_LOCATION_ID, mock_redis
    ) as client:
        result = await client.get_orders(
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
        )

    assert result == []
    assert call_count == 2


def test_cents_to_decimal():
    assert cents_to_decimal(1000) == Decimal("10.00")
    assert cents_to_decimal(0) == Decimal("0.00")
    assert cents_to_decimal(None) is None
    assert cents_to_decimal(123) == Decimal("1.23")


def test_to_toast_ts():
    dt = datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc)
    result = _to_toast_ts(dt)
    assert result == "2024-03-15T10:30:00.000+0000"
