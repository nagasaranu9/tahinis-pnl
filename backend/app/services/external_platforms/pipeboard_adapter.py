"""Pipeboard adapter — MCP (Model Context Protocol) client.

Pipeboard exposes one MCP server per ad platform (Streamable HTTP transport):
    https://google-ads.mcp.pipeboard.co/
    https://meta-ads.mcp.pipeboard.co/
    https://tiktok-ads.mcp.pipeboard.co/

Auth = a single Pipeboard API token (https://pipeboard.co/api-tokens), passed as
`Authorization: Bearer <token>` AND `?token=<token>`. There is NO OAuth client /
refresh-token flow — that was a wrong earlier assumption. The token is long-lived
and the same token unlocks every platform the user connected on pipeboard.co.

Flow per platform:
    1. open MCP session (initialize -> notifications/initialized)
    2. tools/call list_<platform>_customers   -> customer/account ids
    3. tools/call get_<platform>_campaigns     -> campaign master rows
    4. tools/call get_<platform>_campaign_metrics(time_breakdown="day")
                                               -> daily segmented_metrics rows

Tool names + response shapes verified live against google-ads on 2026-06-19.
Meta/TikTok use the same protocol but different tool names — wired but unverified.
"""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# DTOs (unchanged — downstream backfill/sync/pnl depend on these shapes)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# MCP transport
# ---------------------------------------------------------------------------
class PipeboardMcpError(Exception):
    """Raised when an MCP call fails or returns isError."""


class _PipeboardMcpClient:
    """Minimal MCP JSON-RPC client over Pipeboard Streamable HTTP.

    Stateless servers (session_id=None) — each call opens a fresh handshake-free
    request; we still send `initialize` once per client to be protocol-correct.
    """

    PROTOCOL_VERSION = "2025-03-26"

    def __init__(self, base_url: str, api_token: str, timeout: int = 60):
        self._url = base_url
        self._token = api_token
        self._timeout = timeout

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    @staticmethod
    def _parse_body(text: str) -> dict:
        """Pipeboard answers as JSON or SSE (`data: {...}`). Handle both."""
        text = text.strip()
        if not text:
            return {}
        if text.startswith("{"):
            return json.loads(text)
        payload = None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                payload = line[len("data:"):].strip()
        if payload:
            return json.loads(payload)
        raise PipeboardMcpError(f"Unrecognized MCP body: {text[:300]}")

    async def _rpc(self, client: httpx.AsyncClient, method: str,
                   params: dict | None = None, notify: bool = False) -> dict:
        body: dict = {"jsonrpc": "2.0", "method": method}
        if not notify:
            body["id"] = str(uuid.uuid4())
        if params is not None:
            body["params"] = params
        resp = await client.post(
            self._url, params={"token": self._token}, json=body, headers=self._headers()
        )
        if notify:
            return {}
        resp.raise_for_status()
        return self._parse_body(resp.text)

    async def call_tool(self, tool_name: str, arguments: dict | None = None) -> dict:
        """Open session, call one tool, return the decoded inner JSON payload.

        Pipeboard tools return result.content[0].text holding a JSON *string*,
        so we double-decode. Raises PipeboardMcpError on isError.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # Protocol-correct handshake (server is stateless, so cheap).
            await self._rpc(client, "initialize", {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "tahinis-pnl", "version": "1.0.0"},
            })
            await self._rpc(client, "notifications/initialized", {}, notify=True)

            out = await self._rpc(client, "tools/call", {
                "name": tool_name,
                "arguments": arguments or {},
            })

        result = out.get("result", {})
        content = result.get("content", [])
        text = content[0].get("text", "{}") if content else "{}"
        if result.get("isError"):
            raise PipeboardMcpError(f"{tool_name} error: {text}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Some tools return plain text; wrap it.
            return {"_raw": text}


# ---------------------------------------------------------------------------
# Date-range helper — map an explicit [start, end] window onto the smallest
# Pipeboard preset that covers it, then filter daily rows back to the window.
# Avoids guessing a custom date_range string format.
# ---------------------------------------------------------------------------
_PRESETS = [
    ("TODAY", 0),
    ("YESTERDAY", 1),
    ("LAST_7_DAYS", 7),
    ("LAST_14_DAYS", 14),
    ("LAST_30_DAYS", 30),
    ("LAST_90_DAYS", 90),
]


def _preset_for_window(start: date, end: date) -> str:
    """Smallest preset whose lookback (from today) covers `start`."""
    days_back = (date.today() - start).days
    for name, span in _PRESETS:
        if span >= days_back:
            return name
    return "LAST_90_DAYS"  # max preset; older data unsupported via presets


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------
class PipeboardAdapter(ABC):
    @abstractmethod
    async def fetch_campaigns(self, api_token: str, pipeboard_platform: str) -> list[PipeboardCampaignData]:
        ...

    @abstractmethod
    async def fetch_daily_metrics(self, api_token: str, pipeboard_platform: str,
                                  start_date: str, end_date: str) -> list[PipeboardDailyMetricData]:
        ...

    @abstractmethod
    async def list_accounts(self, api_token: str, pipeboard_platform: str) -> list[dict]:
        """Return [{id, currency_code, ...}] — used to validate token on connect."""
        ...


# Platform -> (mcp host subdomain, tool-name infix, currency default)
_PLATFORM_CFG = {
    "google_ads": ("google-ads", "google_ads", "CAD"),
    "meta_ads": ("meta-ads", "meta_ads", "CAD"),
    "tiktok_ads": ("tiktok-ads", "tiktok_ads", "CAD"),
}


class PipeboardHttpAdapter(PipeboardAdapter):
    """Production adapter — talks to live Pipeboard MCP servers."""

    HOST_TEMPLATE = "https://{sub}.mcp.pipeboard.co/"

    def __init__(self, timeout: int = 60):
        self._timeout = timeout

    def _client(self, api_token: str, platform: str) -> _PipeboardMcpClient:
        sub, _, _ = _PLATFORM_CFG[platform]
        return _PipeboardMcpClient(self.HOST_TEMPLATE.format(sub=sub), api_token, self._timeout)

    def _infix(self, platform: str) -> str:
        return _PLATFORM_CFG[platform][1]

    def _currency(self, platform: str) -> str:
        return _PLATFORM_CFG[platform][2]

    async def list_accounts(self, api_token: str, pipeboard_platform: str) -> list[dict]:
        if pipeboard_platform not in _PLATFORM_CFG:
            raise PipeboardMcpError(f"Unsupported platform: {pipeboard_platform}")
        client = self._client(api_token, pipeboard_platform)
        infix = self._infix(pipeboard_platform)
        data = await client.call_tool(f"list_{infix}_customers")
        logger.info("pipeboard_list_accounts_raw", platform=pipeboard_platform, keys=list(data.keys()), data=str(data)[:500])
        customers = data.get("customers", data.get("accounts", data.get("data", [])))
        if isinstance(customers, dict):
            customers = [customers]
        logger.info("pipeboard_list_accounts_result", platform=pipeboard_platform, count=len(customers))
        return customers

    async def fetch_campaigns(self, api_token: str, pipeboard_platform: str) -> list[PipeboardCampaignData]:
        client = self._client(api_token, pipeboard_platform)
        infix = self._infix(pipeboard_platform)

        campaigns: list[PipeboardCampaignData] = []
        for cust in await self.list_accounts(api_token, pipeboard_platform):
            customer_id = str(cust.get("id") or cust.get("customer_id") or "")
            logger.info("pipeboard_fetch_campaigns", platform=pipeboard_platform, customer_id=customer_id, cust_keys=list(cust.keys()))
            data = await client.call_tool(
                f"get_{infix}_campaigns", {"customer_id": customer_id}
            )
            logger.info("pipeboard_campaigns_raw", platform=pipeboard_platform, keys=list(data.keys()), data=str(data)[:500])
            for c in data.get("campaigns", []):
                budget = c.get("budget")
                campaigns.append(PipeboardCampaignData(
                    pipeboard_platform=pipeboard_platform,
                    pipeboard_campaign_id=str(c["id"]),
                    name=c.get("name", ""),
                    status=c.get("status", "ENABLED"),
                    campaign_type=c.get("type"),
                    daily_budget_limit=Decimal(str(budget)) if budget is not None else None,
                ))
        return campaigns

    async def fetch_daily_metrics(self, api_token: str, pipeboard_platform: str,
                                  start_date: str, end_date: str) -> list[PipeboardDailyMetricData]:
        client = self._client(api_token, pipeboard_platform)
        infix = self._infix(pipeboard_platform)
        currency = self._currency(pipeboard_platform)

        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        preset = _preset_for_window(start, end)

        metrics: list[PipeboardDailyMetricData] = []
        for cust in await self.list_accounts(api_token, pipeboard_platform):
            customer_id = str(cust.get("id"))
            cur = cust.get("currency_code", currency)
            if not cust.get("can_query_metrics", True):
                continue

            # Per-campaign so each daily row is attributable. Campaigns without
            # spend in-window simply return no segmented rows.
            campaigns_data = await client.call_tool(
                f"get_{infix}_campaigns", {"customer_id": customer_id}
            )
            for c in campaigns_data.get("campaigns", []):
                campaign_id = str(c["id"])
                result = await client.call_tool(f"get_{infix}_campaign_metrics", {
                    "customer_id": customer_id,
                    "campaign_ids": [campaign_id],
                    "date_range": preset,
                    "time_breakdown": "day",
                })
                logger.info("pipeboard_metrics_raw", platform=pipeboard_platform, campaign_id=campaign_id, keys=list(result.keys()), data=str(result)[:500])
                rows_added = 0
                for row in result.get("segmented_metrics", []):
                    row_date = row.get("date")
                    if not row_date or not (start_date <= row_date <= end_date):
                        continue
                    cost = Decimal(str(row.get("cost", 0)))
                    conv_value = row.get("conversions_value")
                    roas = (Decimal(str(conv_value)) / cost) if (conv_value and cost > 0) else None
                    metrics.append(PipeboardDailyMetricData(
                        pipeboard_platform=pipeboard_platform,
                        pipeboard_campaign_id=campaign_id,
                        metric_date=row_date,
                        spend=cost,
                        impressions=int(row.get("impressions", 0)),
                        clicks=int(row.get("clicks", 0)),
                        conversions=Decimal(str(row["conversions"])) if row.get("conversions") is not None else None,
                        conversion_value=Decimal(str(conv_value)) if conv_value is not None else None,
                        ctr=Decimal(str(row["ctr"])) if row.get("ctr") is not None else None,
                        cpc=Decimal(str(row["average_cpc"])) if row.get("average_cpc") is not None else None,
                        roas=roas,
                        currency_code=cur,
                    ))
                    rows_added += 1

                # Fallback: Pipeboard often returns an empty `segmented_metrics`
                # (no per-day breakdown) while still reporting real campaign totals
                # in `aggregate_metrics` — especially for PMax campaigns. Without
                # this, dashboards show 0 metrics even though spend exists. Persist
                # one summary row dated at end_date so spend/ROAS surface on the
                # P&L and marketing tiles.
                if rows_added == 0:
                    agg = result.get("aggregate_metrics") or {}
                    cost = Decimal(str(agg.get("cost", 0) or 0))
                    if cost > 0:
                        conv_value = agg.get("conversions_value")
                        roas = (Decimal(str(conv_value)) / cost) if (conv_value and cost > 0) else None
                        metrics.append(PipeboardDailyMetricData(
                            pipeboard_platform=pipeboard_platform,
                            pipeboard_campaign_id=campaign_id,
                            metric_date=end_date,
                            spend=cost,
                            impressions=int(agg.get("impressions", 0) or 0),
                            clicks=int(agg.get("clicks", 0) or 0),
                            conversions=Decimal(str(agg["conversions"])) if agg.get("conversions") is not None else None,
                            conversion_value=Decimal(str(conv_value)) if conv_value is not None else None,
                            ctr=Decimal(str(agg["average_ctr"])) if agg.get("average_ctr") is not None else None,
                            cpc=Decimal(str(agg["average_cpc"])) if agg.get("average_cpc") is not None else None,
                            roas=roas,
                            currency_code=cur,
                        ))
                        logger.info(
                            "pipeboard_metrics_aggregate_fallback",
                            platform=pipeboard_platform,
                            campaign_id=campaign_id,
                            spend=str(cost),
                        )
        return metrics


class MockPipeboardAdapter(PipeboardAdapter):
    """Mock adapter for development / tests — no network."""

    async def list_accounts(self, api_token: str, pipeboard_platform: str) -> list[dict]:
        return [{"id": "4104711801", "currency_code": "CAD", "can_query_metrics": True}]

    async def fetch_campaigns(self, api_token: str, pipeboard_platform: str) -> list[PipeboardCampaignData]:
        return [
            PipeboardCampaignData(
                pipeboard_platform=pipeboard_platform,
                pipeboard_campaign_id="23913438713",
                name="Game Day Platters",
                status="ENABLED",
                campaign_type="PERFORMANCE_MAX",
                daily_budget_limit=Decimal("20"),
            ),
        ]

    async def fetch_daily_metrics(self, api_token: str, pipeboard_platform: str,
                                  start_date: str, end_date: str) -> list[PipeboardDailyMetricData]:
        return [
            PipeboardDailyMetricData(
                pipeboard_platform=pipeboard_platform,
                pipeboard_campaign_id="23913438713",
                metric_date=start_date,
                spend=Decimal("20.03"),
                impressions=3756,
                clicks=115,
                conversions=Decimal("47"),
                conversion_value=Decimal("47"),
                ctr=Decimal("0.0306"),
                cpc=Decimal("0.1742"),
                roas=Decimal("2.35"),
            ),
        ]


class PipeboardAdapterFactory:
    @staticmethod
    def create(adapter_type: str = "mock") -> PipeboardAdapter:
        if adapter_type == "http":
            return PipeboardHttpAdapter()
        return MockPipeboardAdapter()
