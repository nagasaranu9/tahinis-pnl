"""Unit tests for OutlookClient."""
import base64
import pytest
import respx
import httpx
from datetime import datetime, timezone

from app.services.email.outlook_client import (
    OutlookClient,
    extract_outlook_metadata,
    SUPPORTED_ATTACHMENT_MIMES,
)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MOCK_ACCESS_TOKEN = "access_outlook"
MOCK_REFRESH_TOKEN = "refresh_outlook"


@respx.mock
@pytest.mark.asyncio
async def test_get_me():
    respx.get(f"{GRAPH_BASE}/me").mock(
        return_value=httpx.Response(200, json={"mail": "user@company.com"})
    )

    async with OutlookClient(MOCK_ACCESS_TOKEN, MOCK_REFRESH_TOKEN) as client:
        email, _ = await client.get_me()

    assert email == "user@company.com"


@respx.mock
@pytest.mark.asyncio
async def test_list_messages_delta_returns_delta_link():
    messages = [{"id": "msg1", "subject": "Invoice", "hasAttachments": True}]
    delta_link = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=abc"

    respx.get("https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta").mock(
        return_value=httpx.Response(200, json={"value": messages, "@odata.deltaLink": delta_link})
    )

    async with OutlookClient(MOCK_ACCESS_TOKEN, MOCK_REFRESH_TOKEN) as client:
        msgs, new_delta, _ = await client.list_messages_delta()

    assert len(msgs) == 1
    assert new_delta == delta_link


def test_extract_outlook_metadata():
    msg = {
        "subject": "RE: Monthly Statement",
        "from": {"emailAddress": {"address": "billing@vendor.com"}},
        "receivedDateTime": "2024-03-15T10:30:00Z",
        "hasAttachments": True,
    }
    meta = extract_outlook_metadata(msg)
    assert meta["subject"] == "RE: Monthly Statement"
    assert meta["sender"] == "billing@vendor.com"
    assert isinstance(meta["received_at"], datetime)


@respx.mock
@pytest.mark.asyncio
async def test_download_attachment_decodes_base64():
    content = b"INVOICE_BYTES"
    encoded = base64.b64encode(content).decode()

    respx.get(f"{GRAPH_BASE}/me/messages/msg1/attachments/att1").mock(
        return_value=httpx.Response(200, json={"contentBytes": encoded})
    )

    async with OutlookClient(MOCK_ACCESS_TOKEN, MOCK_REFRESH_TOKEN) as client:
        result = await client.download_attachment("msg1", "att1")

    assert result == content
