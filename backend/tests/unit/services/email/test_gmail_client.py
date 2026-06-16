"""Unit tests for GmailClient — respx mocks, no real network."""
import base64
import pytest
import respx
import httpx

from app.services.email.gmail_client import (
    GmailClient,
    extract_attachments,
    extract_message_metadata,
    SUPPORTED_ATTACHMENT_MIMES,
)

MOCK_ACCESS_TOKEN = "access_token_abc"
MOCK_REFRESH_TOKEN = "refresh_token_xyz"
GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"
AUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"


@respx.mock
@pytest.mark.asyncio
async def test_get_profile():
    respx.get(f"{GMAIL_BASE}/users/me/profile").mock(
        return_value=httpx.Response(200, json={"emailAddress": "user@example.com", "historyId": "12345"})
    )

    async with GmailClient(MOCK_ACCESS_TOKEN, MOCK_REFRESH_TOKEN) as client:
        email, history_id = await client.get_profile()

    assert email == "user@example.com"
    assert history_id == "12345"


@respx.mock
@pytest.mark.asyncio
async def test_token_refresh_on_401():
    call_count = 0

    def profile_response(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"emailAddress": "user@example.com", "historyId": "99"})

    respx.get(f"{GMAIL_BASE}/users/me/profile").mock(side_effect=profile_response)
    respx.post(AUTH_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "new_token", "expires_in": 3600})
    )

    async with GmailClient(MOCK_ACCESS_TOKEN, MOCK_REFRESH_TOKEN) as client:
        email, _ = await client.get_profile()

    assert email == "user@example.com"
    assert call_count == 2


def test_extract_attachments_pdf_only():
    msg = {
        "payload": {
            "parts": [
                {
                    "filename": "invoice.pdf",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "att-001", "size": 12345},
                    "parts": [],
                },
                {
                    "filename": "photo.png",
                    "mimeType": "image/png",
                    "body": {"attachmentId": "att-002", "size": 500},
                    "parts": [],
                },
                {
                    "filename": "archive.zip",
                    "mimeType": "application/zip",
                    "body": {"attachmentId": "att-003", "size": 99999},
                    "parts": [],
                },
            ],
            "headers": [],
        }
    }
    atts = extract_attachments(msg)
    mime_types = {a["mime_type"] for a in atts}
    assert "application/pdf" in mime_types
    assert "image/png" in mime_types
    assert "application/zip" not in mime_types
    assert len(atts) == 2


def test_extract_message_metadata():
    msg = {
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Invoice from Sysco"},
                {"name": "From", "value": "vendor@sysco.com"},
            ]
        },
        "internalDate": "1704067200000",  # 2024-01-01 UTC
    }
    meta = extract_message_metadata(msg)
    assert meta["subject"] == "Invoice from Sysco"
    assert meta["sender"] == "vendor@sysco.com"
    assert meta["received_at"] is not None


@respx.mock
@pytest.mark.asyncio
async def test_get_attachment_decodes_urlsafe_base64():
    content = b"PDF_CONTENT_HERE"
    encoded = base64.urlsafe_b64encode(content).decode()

    respx.get(f"{GMAIL_BASE}/users/me/messages/msg1/attachments/att1").mock(
        return_value=httpx.Response(200, json={"data": encoded, "size": len(content)})
    )

    async with GmailClient(MOCK_ACCESS_TOKEN, MOCK_REFRESH_TOKEN) as client:
        result = await client.get_attachment("msg1", "att1")

    assert result == content
