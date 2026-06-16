"""
Gmail API client using OAuth2 authorization code flow.

Scopes: https://www.googleapis.com/auth/gmail.readonly
Incremental sync: users.history.list with historyId cursor.
Token refresh: automatic via google-auth library.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "email",
]

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"

# MIME types we want to extract from attachments
SUPPORTED_ATTACHMENT_MIMES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/tiff",
}


def build_gmail_auth_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_gmail_code(code: str, redirect_uri: str) -> dict[str, Any]:
    """Exchange auth code for access_token + refresh_token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
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
    if resp.status_code != 200:
        raise ValueError(f"Gmail token exchange failed: {resp.text[:300]}")
    return resp.json()


async def refresh_gmail_token(refresh_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code != 200:
        raise ValueError(f"Gmail token refresh failed: {resp.text[:300]}")
    return resp.json()


class GmailClient:
    """
    Gmail incremental sync client.
    access_token and refresh_token come from IntegrationCredential (decrypted).
    """

    def __init__(self, access_token: str, refresh_token: str) -> None:
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._http: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "GmailClient":
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            base_url=GMAIL_API_BASE,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._http:
            await self._http.aclose()

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        assert self._http is not None
        headers = {"Authorization": f"Bearer {self._access_token}"}
        resp = await self._http.get(path, params=params, headers=headers)

        if resp.status_code == 401:
            token_data = await refresh_gmail_token(self._refresh_token)
            self._access_token = token_data["access_token"]
            headers["Authorization"] = f"Bearer {self._access_token}"
            resp = await self._http.get(path, params=params, headers=headers)

        if resp.status_code != 200:
            raise ValueError(f"Gmail API error {resp.status_code}: {resp.text[:200]}")
        return resp.json(), self._access_token  # return new token for storage

    async def get_profile(self) -> tuple[str, str]:
        """Returns (email_address, historyId)."""
        data, _ = await self._get("/users/me/profile")
        return data["emailAddress"], data.get("historyId", "")

    async def list_messages_with_attachments(
        self,
        history_id: Optional[str] = None,
        max_results: int = 500,
        after_date: Optional[str] = None,
    ) -> tuple[list[dict], str, str]:
        """
        Returns (messages, new_history_id, new_access_token).
        If history_id provided → incremental via history.list.
        Otherwise → full inbox search for messages with attachments.
        after_date: "YYYY/MM/DD" format, limits full scan start date.
        """
        if history_id:
            return await self._incremental_messages(history_id)
        return await self._full_scan_messages(max_results, after_date=after_date)

    async def _incremental_messages(
        self, history_id: str
    ) -> tuple[list[dict], str, str]:
        messages: list[dict] = []
        page_token = None

        while True:
            params: dict = {
                "startHistoryId": history_id,
                "historyTypes": "messageAdded",
            }
            if page_token:
                params["pageToken"] = page_token

            data, new_token = await self._get("/users/me/history", params=params)
            histories = data.get("history", [])
            for h in histories:
                for added in h.get("messagesAdded", []):
                    msg = added.get("message", {})
                    if msg:
                        messages.append(msg)

            page_token = data.get("nextPageToken")
            if not page_token:
                new_history_id = data.get("historyId", history_id)
                return messages, new_history_id, new_token

    async def _full_scan_messages(
        self, max_results: int, after_date: Optional[str] = None
    ) -> tuple[list[dict], str, str]:
        """Scan inbox for messages that have attachments."""
        messages: list[dict] = []
        page_token = None
        new_token = self._access_token

        # after_date format: "YYYY/MM/DD" (Gmail query syntax)
        # Restrict to financial documents only — exclude resumes, photos, etc.
        financial_keywords = (
            "(invoice OR bill OR receipt OR statement OR "
            "\"purchase order\" OR payment OR \"vendor\" OR "
            "\"accounts payable\" OR utility OR rent OR insurance)"
        )
        query = f"has:attachment {financial_keywords}"
        if after_date:
            query += f" after:{after_date}"

        while len(messages) < max_results:
            params: dict = {"q": query, "maxResults": min(100, max_results - len(messages))}
            if page_token:
                params["pageToken"] = page_token

            data, new_token = await self._get("/users/me/messages", params=params)
            messages.extend(data.get("messages", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        profile_data, new_token = await self._get("/users/me/profile")
        new_history_id = str(profile_data.get("historyId", ""))
        return messages, new_history_id, new_token

    async def get_message(self, message_id: str) -> tuple[dict, str]:
        """Get full message with payload. Returns (message, new_access_token)."""
        data, new_token = await self._get(f"/users/me/messages/{message_id}", params={"format": "full"})
        return data, new_token

    async def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download raw attachment bytes."""
        data, _ = await self._get(f"/users/me/messages/{message_id}/attachments/{attachment_id}")
        raw = data.get("data", "")
        # Gmail uses URL-safe base64
        return base64.urlsafe_b64decode(raw + "==")


def extract_message_metadata(msg: dict) -> dict:
    """Extract subject, sender, date from Gmail message headers."""
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "subject": headers.get("subject", ""),
        "sender": headers.get("from", ""),
        "received_at": _parse_internal_date(msg.get("internalDate")),
    }


def extract_attachments(msg: dict) -> list[dict]:
    """
    Recursively walk message payload parts and return list of attachment dicts.
    Each dict: {filename, mime_type, attachment_id, size}
    """
    attachments = []
    _walk_parts(msg.get("payload", {}), attachments)
    return [a for a in attachments if a.get("mime_type") in SUPPORTED_ATTACHMENT_MIMES]


def _walk_parts(part: dict, acc: list) -> None:
    if part.get("filename") and part.get("body", {}).get("attachmentId"):
        acc.append({
            "filename": part["filename"],
            "mime_type": part.get("mimeType", "application/octet-stream"),
            "attachment_id": part["body"]["attachmentId"],
            "size": part["body"].get("size", 0),
        })
    for sub in part.get("parts", []):
        _walk_parts(sub, acc)


def _parse_internal_date(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)
    except Exception:
        return None
