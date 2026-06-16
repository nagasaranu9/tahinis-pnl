"""
Google Business Profile Reviews API client.

OAuth2 authorization code flow with scope: https://www.googleapis.com/auth/business.manage
Fetches reviews from My Business API v4.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GBP_ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
GBP_LOCATIONS_URL = "https://mybusinessbusinessinformation.googleapis.com/v1"
GBP_REVIEWS_URL = "https://mybusiness.googleapis.com/v4"

REVIEWS_SCOPES = [
    "https://www.googleapis.com/auth/business.manage",
    "openid",
    "email",
]


class GoogleAPIRateLimitError(Exception):
    """Raised on HTTP 429 — caller should back off, not treat as a permanent failure."""

    def __init__(self, retry_after_seconds: int | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Google API rate limited, retry_after={retry_after_seconds}")


def build_reviews_auth_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(REVIEWS_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_reviews_code(code: str, redirect_uri: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


class GoogleReviewsClient:
    def __init__(self, access_token: str, refresh_token: str) -> None:
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self) -> "GoogleReviewsClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._client.aclose()

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _refresh(self) -> None:
        resp = await self._client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code == 200:
            self._access_token = resp.json()["access_token"]

    async def _get(self, url: str, params: dict | None = None) -> dict:
        resp = await self._client.get(url, headers=self._auth_headers(), params=params)
        if resp.status_code == 401:
            await self._refresh()
            resp = await self._client.get(url, headers=self._auth_headers(), params=params)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            raise GoogleAPIRateLimitError(int(retry_after) if retry_after and retry_after.isdigit() else None)
        resp.raise_for_status()
        return resp.json()

    async def get_accounts(self) -> list[dict]:
        data = await self._get(GBP_ACCOUNTS_URL)
        return data.get("accounts", [])

    async def get_locations(self, account_name: str) -> list[dict]:
        url = f"{GBP_LOCATIONS_URL}/{account_name}/locations"
        data = await self._get(url, params={"readMask": "name,title,storefrontAddress"})
        return data.get("locations", [])

    async def list_reviews(
        self, account_name: str, location_name: str, page_token: str | None = None
    ) -> dict:
        """Returns {reviews: [...], nextPageToken: str|None, averageRating: float, totalReviewCount: int}"""
        # location_name is like "accounts/123/locations/456"
        # API: GET /v4/{name}/reviews
        loc_id = location_name.split("/")[-1]
        acct_id = account_name.split("/")[-1]
        url = f"{GBP_REVIEWS_URL}/accounts/{acct_id}/locations/{loc_id}/reviews"
        params: dict = {"pageSize": 50}
        if page_token:
            params["pageToken"] = page_token
        return await self._get(url, params=params)

    async def get_fresh_access_token(self) -> str:
        """Returns current access token (refreshed if needed)."""
        await self._refresh()
        return self._access_token
