"""
Microsoft Graph / Outlook client using OAuth2 authorization code flow.

Scopes: Mail.Read, openid, email, offline_access
Incremental sync: /me/mailFolders/inbox/messages/delta with @odata.deltaLink cursor.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

OUTLOOK_SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "openid",
    "email",
    "offline_access",
]

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

SUPPORTED_ATTACHMENT_MIMES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/tiff",
}


def build_outlook_auth_url(redirect_uri: str, state: str) -> str:
    tenant = settings.MICROSOFT_TENANT_ID
    auth_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
    params = {
        "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(OUTLOOK_SCOPES),
        "state": state,
        "response_mode": "query",
    }
    return f"{auth_url}?{urlencode(params)}"


async def exchange_outlook_code(code: str, redirect_uri: str) -> dict[str, Any]:
    tenant = settings.MICROSOFT_TENANT_ID
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            token_url,
            data={
                "code": code,
                "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
                "client_secret": settings.MICROSOFT_OAUTH_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": " ".join(OUTLOOK_SCOPES),
            },
        )
    if resp.status_code != 200:
        raise ValueError(f"Outlook token exchange failed: {resp.text[:300]}")
    return resp.json()


async def refresh_outlook_token(refresh_token: str) -> dict[str, Any]:
    tenant = settings.MICROSOFT_TENANT_ID
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            token_url,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
                "client_secret": settings.MICROSOFT_OAUTH_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "scope": " ".join(OUTLOOK_SCOPES),
            },
        )
    if resp.status_code != 200:
        raise ValueError(f"Outlook token refresh failed: {resp.text[:300]}")
    return resp.json()


class OutlookClient:
    def __init__(self, access_token: str, refresh_token: str) -> None:
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._http: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "OutlookClient":
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            base_url=GRAPH_API_BASE,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._http:
            await self._http.aclose()

    async def _get(self, path: str, params: Optional[dict] = None) -> tuple[Any, str]:
        assert self._http is not None
        headers = {"Authorization": f"Bearer {self._access_token}"}
        resp = await self._http.get(path, params=params, headers=headers)

        if resp.status_code == 401:
            token_data = await refresh_outlook_token(self._refresh_token)
            self._access_token = token_data["access_token"]
            headers["Authorization"] = f"Bearer {self._access_token}"
            resp = await self._http.get(path, params=params, headers=headers)

        if resp.status_code != 200:
            raise ValueError(f"Outlook API error {resp.status_code}: {resp.text[:200]}")
        return resp.json(), self._access_token

    async def get_me(self) -> tuple[str, str]:
        """Returns (email_address, new_access_token)."""
        data, token = await self._get("/me", params={"$select": "mail,userPrincipalName"})
        email = data.get("mail") or data.get("userPrincipalName", "")
        return email, token

    async def list_messages_delta(
        self, delta_link: Optional[str] = None
    ) -> tuple[list[dict], str, str]:
        """
        Returns (messages, new_delta_link, new_access_token).
        Uses /delta with $filter for attachment-bearing messages.
        """
        messages: list[dict] = []
        new_token = self._access_token

        if delta_link:
            url = delta_link  # absolute URL from previous sync
        else:
            url = (
                "/me/mailFolders/inbox/messages/delta"
                "?$select=id,subject,from,receivedDateTime,hasAttachments"
                "&$filter=hasAttachments eq true"
            )

        while True:
            assert self._http is not None
            headers = {"Authorization": f"Bearer {self._access_token}"}
            # Delta link may be absolute — handle both cases
            if url.startswith("http"):
                resp = await self._http.get(url, headers=headers)
            else:
                resp = await self._http.get(url, headers=headers)

            if resp.status_code == 401:
                token_data = await refresh_outlook_token(self._refresh_token)
                self._access_token = token_data["access_token"]
                new_token = self._access_token
                headers["Authorization"] = f"Bearer {self._access_token}"
                resp = await self._http.get(url, headers=headers)

            if resp.status_code != 200:
                raise ValueError(f"Outlook delta error {resp.status_code}: {resp.text[:200]}")

            data = resp.json()
            messages.extend(data.get("value", []))

            next_link = data.get("@odata.nextLink")
            new_delta_link = data.get("@odata.deltaLink")

            if new_delta_link:
                return messages, new_delta_link, new_token
            if next_link:
                url = next_link
            else:
                return messages, "", new_token

    async def get_message_attachments(self, message_id: str) -> tuple[list[dict], str]:
        """Get attachments for a message. Returns (attachments, new_access_token)."""
        data, new_token = await self._get(
            f"/me/messages/{message_id}/attachments",
            params={"$select": "id,name,contentType,size,contentBytes"},
        )
        return data.get("value", []), new_token

    async def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment content bytes."""
        import base64
        data, _ = await self._get(f"/me/messages/{message_id}/attachments/{attachment_id}")
        content = data.get("contentBytes", "")
        return base64.b64decode(content) if content else b""


def extract_outlook_metadata(msg: dict) -> dict:
    sender = (msg.get("from") or {}).get("emailAddress", {}).get("address", "")
    received_str = msg.get("receivedDateTime", "")
    received_at = None
    if received_str:
        try:
            received_at = datetime.fromisoformat(received_str.replace("Z", "+00:00"))
        except Exception:
            pass
    return {
        "subject": msg.get("subject", ""),
        "sender": sender,
        "received_at": received_at,
        "has_attachments": msg.get("hasAttachments", False),
    }
