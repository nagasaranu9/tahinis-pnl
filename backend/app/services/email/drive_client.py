"""
Google Drive API client using OAuth2 authorization code flow.

Scopes: https://www.googleapis.com/auth/drive.readonly
Incremental sync: files.list with pageToken.
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlencode

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "openid",
    "email",
]

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DRIVE_DOWNLOAD_BASE = "https://www.googleapis.com/drive/v3/files"

SUPPORTED_DRIVE_MIMES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
}

# Google Docs/Sheets can be exported as PDF — not handled here for now


def build_drive_auth_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(DRIVE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_drive_code(code: str, redirect_uri: str) -> dict[str, Any]:
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
        raise ValueError(f"Drive token exchange failed: {resp.text[:300]}")
    return resp.json()


async def refresh_drive_token(refresh_token: str) -> dict[str, Any]:
    from app.services.email.gmail_client import refresh_gmail_token
    return await refresh_gmail_token(refresh_token)


class GoogleDriveClient:
    def __init__(self, access_token: str, refresh_token: str) -> None:
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._http: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "GoogleDriveClient":
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._http:
            await self._http.aclose()

    async def _get(self, url: str, params: Optional[dict] = None) -> tuple[Any, str]:
        assert self._http is not None
        headers = {"Authorization": f"Bearer {self._access_token}"}
        resp = await self._http.get(url, params=params, headers=headers)

        if resp.status_code == 401:
            token_data = await refresh_drive_token(self._refresh_token)
            self._access_token = token_data["access_token"]
            headers["Authorization"] = f"Bearer {self._access_token}"
            resp = await self._http.get(url, params=params, headers=headers)

        if resp.status_code != 200:
            raise ValueError(f"Drive API error {resp.status_code}: {resp.text[:200]}")
        return resp.json(), self._access_token

    async def get_user_email(self) -> tuple[str, str]:
        data, token = await self._get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            params={"fields": "email"},
        )
        return data.get("email", ""), token

    async def list_files(
        self,
        page_token: Optional[str] = None,
        folder_ids: Optional[list[str]] = None,
    ) -> tuple[list[dict], Optional[str], str]:
        """
        List supported files incrementally.
        Returns (files, next_page_token, new_access_token).
        next_page_token=None means sync is complete.
        """
        mime_filter = " or ".join(
            f"mimeType='{m}'" for m in SUPPORTED_DRIVE_MIMES
        )
        query = f"trashed=false and ({mime_filter})"

        if folder_ids:
            parents = " or ".join(f"'{fid}' in parents" for fid in folder_ids)
            query = f"({query}) and ({parents})"

        params: dict = {
            "q": query,
            "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,parents)",
            "pageSize": 100,
        }
        if page_token:
            params["pageToken"] = page_token

        data, new_token = await self._get(f"{DRIVE_API_BASE}/files", params=params)
        return data.get("files", []), data.get("nextPageToken"), new_token

    async def download_file(self, file_id: str) -> bytes:
        """Download file content as bytes."""
        assert self._http is not None
        headers = {"Authorization": f"Bearer {self._access_token}"}
        url = f"{DRIVE_DOWNLOAD_BASE}/{file_id}"
        resp = await self._http.get(url, params={"alt": "media"}, headers=headers)

        if resp.status_code == 401:
            token_data = await refresh_drive_token(self._refresh_token)
            self._access_token = token_data["access_token"]
            headers["Authorization"] = f"Bearer {self._access_token}"
            resp = await self._http.get(url, params={"alt": "media"}, headers=headers)

        if resp.status_code != 200:
            raise ValueError(f"Drive download error {resp.status_code}")
        return resp.content
