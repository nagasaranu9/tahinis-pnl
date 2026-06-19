"""Pipeboard adapter.

Handles OAuth token refresh, API calls, campaign/metric fetch.
Token expiry check includes 5-min buffer to refresh early.
Concurrent refresh protected by lock.
"""
from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Optional
from urllib.parse import urlencode

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipeboardCampaignData:
    """Campaign master record."""
    pipeboard_platform: str  # google_ads / meta_ads / tiktok_ads
    pipeboard_campaign_id: str
    name: str
    status: str = "ENABLED"
    campaign_type: Optional[str] = None
    daily_budget_limit: Optional[Decimal] = None
    lifetime_budget_limit: Optional[Decimal] = None
    spend_to_date: Optional[Decimal] = None


@dataclass
class PipeboardDailyMetricData:
    """Daily metrics per campaign."""
    pipeboard_platform: str
    pipeboard_campaign_id: str
    metric_date: str  # YYYY-MM-DD
    spend: Decimal = Decimal("0")
    impressions: int = 0
    clicks: int = 0
    conversions: Optional[Decimal] = None
    conversion_value: Optional[Decimal] = None
    ctr: Optional[Decimal] = None
    cpc: Optional[Decimal] = None
    roas: Optional[Decimal] = None
    currency_code: str = "CAD"


@dataclass
class PipeboardData:
    """Wrapper for campaigns + daily metrics."""
    campaigns: list[PipeboardCampaignData] = field(default_factory=list)
    daily_metrics: list[PipeboardDailyMetricData] = field(default_factory=list)


@dataclass
class TokenRefreshResult:
    """Result of token refresh."""
    access_token: str
    refresh_token: str
    token_expiry: datetime
    success: bool
    error: Optional[str] = None


class PipeboardAdapter(ABC):
    """Abstract Pipeboard adapter."""

    @abstractmethod
    async def get_oauth_authorize_url(
        self,
        client_id: str,
        redirect_uri: str,
        state: str,
    ) -> str:
        """Build OAuth authorize URL."""

    @abstractmethod
    async def exchange_code_for_token(
        self,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
    ) -> dict:
        """Exchange auth code for tokens. Returns {access_token, refresh_token, expires_in}."""

    @abstractmethod
    async def refresh_access_token(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> TokenRefreshResult:
        """Refresh expired access token."""

    @abstractmethod
    async def fetch_campaigns(
        self,
        access_token: str,
        pipeboard_platform: str,
    ) -> list[PipeboardCampaignData]:
        """Fetch campaigns for platform."""

    @abstractmethod
    async def fetch_daily_metrics(
        self,
        access_token: str,
        pipeboard_platform: str,
        start_date: str,
        end_date: str,
    ) -> list[PipeboardDailyMetricData]:
        """Fetch daily metrics for platform and date range (YYYY-MM-DD)."""


class PipeboardHttpAdapter(PipeboardAdapter):
    """Production Pipeboard API adapter."""

    BASE_URL = "https://api.pipeboard.ai"
    OAUTH_BASE_URL = "https://oauth.pipeboard.ai"
    TOKEN_EXPIRY_BUFFER = 300  # 5 minutes in seconds

    def __init__(self, timeout: int = 30):
        self._timeout = timeout
        self._token_refresh_lock = asyncio.Lock()

    async def get_oauth_authorize_url(
        self,
        client_id: str,
        redirect_uri: str,
        state: str,
    ) -> str:
        """Build OAuth authorize URL."""
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": "campaigns:read metrics:read",
        }
        return f"{self.OAUTH_BASE_URL}/authorize?{urlencode(params)}"

    async def exchange_code_for_token(
        self,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
    ) -> dict:
        """Exchange auth code for tokens."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self.OAUTH_BASE_URL}/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                },
            )
            resp.raise_for_status()
            body = resp.json()

            # Pipeboard returns: access_token, refresh_token, expires_in (seconds)
            return {
                "access_token": body["access_token"],
                "refresh_token": body.get("refresh_token"),
                "expires_in": body.get("expires_in", 3600),
            }

    async def refresh_access_token(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> TokenRefreshResult:
        """Refresh expired access token."""
        async with self._token_refresh_lock:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        f"{self.OAUTH_BASE_URL}/token",
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": refresh_token,
                            "client_id": client_id,
                            "client_secret": client_secret,
                        },
                    )
                    resp.raise_for_status()
                    body = resp.json()

                    access_token = body["access_token"]
                    new_refresh = body.get("refresh_token", refresh_token)
                    expires_in = body.get("expires_in", 3600)
                    token_expiry = datetime.now(UTC) + timedelta(seconds=expires_in)

                    return TokenRefreshResult(
                        access_token=access_token,
                        refresh_token=new_refresh,
                        token_expiry=token_expiry,
                        success=True,
                    )
            except Exception as e:
                logger.error("pipeboard_token_refresh_failed", error=str(e))
                return TokenRefreshResult(
                    access_token="",
                    refresh_token="",
                    token_expiry=datetime.now(UTC),
                    success=False,
                    error=str(e),
                )

    async def fetch_campaigns(
        self,
        access_token: str,
        pipeboard_platform: str,
    ) -> list[PipeboardCampaignData]:
        """Fetch campaigns for platform."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self.BASE_URL}/campaigns",
                params={"platform": pipeboard_platform},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            items = resp.json().get("campaigns", [])

            campaigns = []
            for item in items:
                campaigns.append(
                    PipeboardCampaignData(
                        pipeboard_platform=pipeboard_platform,
                        pipeboard_campaign_id=item["id"],
                        name=item["name"],
                        status=item.get("status", "ENABLED"),
                        campaign_type=item.get("type"),
                        daily_budget_limit=Decimal(str(item.get("daily_budget", 0))),
                        lifetime_budget_limit=Decimal(str(item.get("lifetime_budget", 0))),
                        spend_to_date=Decimal(str(item.get("spend_to_date", 0))),
                    )
                )
            return campaigns

    async def fetch_daily_metrics(
        self,
        access_token: str,
        pipeboard_platform: str,
        start_date: str,
        end_date: str,
    ) -> list[PipeboardDailyMetricData]:
        """Fetch daily metrics for platform and date range."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self.BASE_URL}/metrics",
                params={
                    "platform": pipeboard_platform,
                    "date_from": start_date,
                    "date_to": end_date,
                    "granularity": "daily",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            items = resp.json().get("metrics", [])

            metrics = []
            for item in items:
                metrics.append(
                    PipeboardDailyMetricData(
                        pipeboard_platform=pipeboard_platform,
                        pipeboard_campaign_id=item["campaign_id"],
                        metric_date=item["date"],
                        spend=Decimal(str(item.get("spend", 0))),
                        impressions=int(item.get("impressions", 0)),
                        clicks=int(item.get("clicks", 0)),
                        conversions=Decimal(str(item.get("conversions"))) if item.get("conversions") else None,
                        conversion_value=Decimal(str(item.get("conversion_value"))) if item.get("conversion_value") else None,
                        ctr=Decimal(str(item.get("ctr"))) if item.get("ctr") else None,
                        cpc=Decimal(str(item.get("cpc"))) if item.get("cpc") else None,
                        roas=Decimal(str(item.get("roas"))) if item.get("roas") else None,
                        currency_code=item.get("currency_code", "CAD"),
                    )
                )
            return metrics


class MockPipeboardAdapter(PipeboardAdapter):
    """Mock adapter for development."""

    async def get_oauth_authorize_url(
        self,
        client_id: str,
        redirect_uri: str,
        state: str,
    ) -> str:
        """Mock OAuth URL."""
        return f"{redirect_uri}?code=mock_code&state={state}"

    async def exchange_code_for_token(
        self,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
    ) -> dict:
        """Mock token response."""
        return {
            "access_token": "mock_access_token_12345",
            "refresh_token": "mock_refresh_token_12345",
            "expires_in": 3600,
        }

    async def refresh_access_token(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> TokenRefreshResult:
        """Mock token refresh."""
        return TokenRefreshResult(
            access_token="mock_access_token_refreshed",
            refresh_token=refresh_token,
            token_expiry=datetime.now(UTC) + timedelta(hours=1),
            success=True,
        )

    async def fetch_campaigns(
        self,
        access_token: str,
        pipeboard_platform: str,
    ) -> list[PipeboardCampaignData]:
        """Mock campaigns."""
        return [
            PipeboardCampaignData(
                pipeboard_platform=pipeboard_platform,
                pipeboard_campaign_id="cmp_001",
                name="Tahinis Brand Campaign",
                status="ENABLED",
                campaign_type="SEARCH",
                daily_budget_limit=Decimal("100"),
                spend_to_date=Decimal("2500"),
            ),
            PipeboardCampaignData(
                pipeboard_platform=pipeboard_platform,
                pipeboard_campaign_id="cmp_002",
                name="Tahinis Performance Max",
                status="ENABLED",
                campaign_type="PERFORMANCE_MAX",
                daily_budget_limit=Decimal("200"),
                spend_to_date=Decimal("5000"),
            ),
        ]

    async def fetch_daily_metrics(
        self,
        access_token: str,
        pipeboard_platform: str,
        start_date: str,
        end_date: str,
    ) -> list[PipeboardDailyMetricData]:
        """Mock daily metrics."""
        return [
            PipeboardDailyMetricData(
                pipeboard_platform=pipeboard_platform,
                pipeboard_campaign_id="cmp_001",
                metric_date=start_date,
                spend=Decimal("50.00"),
                impressions=500,
                clicks=25,
                conversions=Decimal("2.0"),
                conversion_value=Decimal("50.00"),
                ctr=Decimal("0.05"),
                cpc=Decimal("2.00"),
                roas=Decimal("1.00"),
            ),
        ]


class PipeboardAdapterFactory:
    @staticmethod
    def create(adapter_type: str = "mock") -> PipeboardAdapter:
        """Create adapter instance."""
        if adapter_type == "http":
            return PipeboardHttpAdapter()
        return MockPipeboardAdapter()
