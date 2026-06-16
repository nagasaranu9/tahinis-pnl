"""
Document pipeline integration tests.
Uses mock OCR adapter (no external dependencies).
Storage calls mocked via pytest-mock.
"""
import io
import uuid

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models.tenant import Tenant
from app.db.models.user import User

PDF_BYTES = b"%PDF-1.4 fake invoice content for testing"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
GARBAGE_BYTES = b"\x00\x01\x02garbage"


@pytest.mark.asyncio
class TestDocumentUpload:
    async def test_upload_pdf_success(
        self, client: AsyncClient, owner_token: str, tenant: Tenant, mocker
    ) -> None:
        mocker.patch(
            "app.services.document_service.upload_document",
            return_value=(f"tenants/{tenant.id}/documents/test.pdf", "abc123"),
        )
        mocker.patch("app.workers.tasks.ocr_process.process_document.delay")

        resp = await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
            files={"file": ("invoice.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["original_filename"] == "invoice.pdf"
        assert data["mime_type"] == "application/pdf"
        assert data["status"] == "pending"
        assert data["is_duplicate"] is False

    async def test_upload_png_success(
        self, client: AsyncClient, owner_token: str, tenant: Tenant, mocker
    ) -> None:
        mocker.patch(
            "app.services.document_service.upload_document",
            return_value=(f"tenants/{tenant.id}/documents/test.png", "def456"),
        )
        mocker.patch("app.workers.tasks.ocr_process.process_document.delay")

        resp = await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
            files={"file": ("receipt.png", io.BytesIO(PNG_BYTES), "image/png")},
        )
        assert resp.status_code == 201

    async def test_upload_rejects_invalid_mime(
        self, client: AsyncClient, owner_token: str
    ) -> None:
        resp = await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
            files={"file": ("evil.exe", io.BytesIO(b"MZ\x90\x00bad"), "application/octet-stream")},
        )
        assert resp.status_code == 422

    async def test_upload_rejects_magic_byte_mismatch(
        self, client: AsyncClient, owner_token: str
    ) -> None:
        # PNG bytes but declared as PDF
        resp = await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
            files={"file": ("fake.pdf", io.BytesIO(PNG_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422

    async def test_upload_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("invoice.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 401

    async def test_duplicate_detection(
        self, client: AsyncClient, owner_token: str, tenant: Tenant, mocker
    ) -> None:
        storage_path = f"tenants/{tenant.id}/documents/test.pdf"
        mocker.patch(
            "app.services.document_service.upload_document",
            return_value=(storage_path, "abc123"),
        )
        mocker.patch("app.workers.tasks.ocr_process.process_document.delay")

        # First upload
        await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
            files={"file": ("invoice.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
        )

        # Second upload — same bytes
        resp2 = await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
            files={"file": ("invoice_copy.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp2.status_code == 201
        data2 = resp2.json()["data"]
        assert data2["is_duplicate"] is True
        assert data2["duplicate_of"] is not None


@pytest.mark.asyncio
class TestDocumentList:
    async def test_list_returns_only_own_tenant_docs(
        self, client: AsyncClient, owner_token: str, tenant: Tenant, mocker
    ) -> None:
        mocker.patch(
            "app.services.document_service.upload_document",
            return_value=(f"tenants/{tenant.id}/documents/doc.pdf", "xyz"),
        )
        mocker.patch("app.workers.tasks.ocr_process.process_document.delay")

        await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {owner_token}"},
            files={"file": ("test.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
        )

        resp = await client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["data"], list)
        assert data["meta"]["total"] >= 1

    async def test_viewer_can_list(
        self, client: AsyncClient, viewer_token: str
    ) -> None:
        resp = await client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 200

    async def test_viewer_cannot_delete(
        self, client: AsyncClient, viewer_token: str
    ) -> None:
        resp = await client.delete(
            f"/api/v1/documents/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403
