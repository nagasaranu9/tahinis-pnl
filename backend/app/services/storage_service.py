import hashlib
import uuid
from io import BytesIO

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings

logger = structlog.get_logger(__name__)

_client = None
_presign_client = None


def _get_client() -> boto3.client:
    global _client
    if _client is None:
        kwargs: dict = {
            "service_name": "s3",
            "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
            "region_name": settings.AWS_REGION,
            "config": Config(signature_version="s3v4"),
        }
        if settings.STORAGE_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.STORAGE_ENDPOINT_URL
        try:
            _client = boto3.client(**kwargs)
            logger.info("s3_client_created", endpoint=settings.STORAGE_ENDPOINT_URL, region=settings.AWS_REGION)
        except Exception as e:
            logger.error("s3_client_creation_failed", error=str(e), exc_info=e)
            raise
    return _client


def _get_presign_client() -> boto3.client:
    """Separate client for presigned URLs using the browser-reachable endpoint."""
    global _presign_client
    if _presign_client is None:
        endpoint = settings.STORAGE_PUBLIC_URL or settings.STORAGE_ENDPOINT_URL
        kwargs: dict = {
            "service_name": "s3",
            "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
            "region_name": settings.AWS_REGION,
            "config": Config(signature_version="s3v4"),
        }
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        _presign_client = boto3.client(**kwargs)
    return _presign_client


def _ensure_bucket() -> None:
    client = _get_client()
    try:
        client.head_bucket(Bucket=settings.STORAGE_BUCKET)
        logger.info("bucket_exists", bucket=settings.STORAGE_BUCKET)
    except ClientError as e:
        logger.error("bucket_check_failed", bucket=settings.STORAGE_BUCKET, error_code=e.response["Error"]["Code"], error=str(e))
        if e.response["Error"]["Code"] == "404":
            try:
                client.create_bucket(Bucket=settings.STORAGE_BUCKET)
                logger.info("storage_bucket_created", bucket=settings.STORAGE_BUCKET)
            except Exception as create_err:
                logger.error("bucket_creation_failed", bucket=settings.STORAGE_BUCKET, error=str(create_err), exc_info=create_err)
                raise
    except Exception as e:
        logger.error("bucket_check_error", bucket=settings.STORAGE_BUCKET, error=str(e), exc_info=e)
        raise


def upload_document(
    file_bytes: bytes,
    tenant_id: uuid.UUID,
    original_filename: str,
    mime_type: str,
) -> tuple[str, str]:
    """
    Stores file at a UUID-keyed path. Returns (storage_path, sha256_checksum).
    Original filename is stored in DB only — never in the storage path.
    """
    _ensure_bucket()

    checksum = hashlib.sha256(file_bytes).hexdigest()
    file_id = uuid.uuid4()
    ext = _safe_extension(mime_type)
    storage_path = f"tenants/{tenant_id}/documents/{file_id}{ext}"

    put_kwargs: dict = {
        "Bucket": settings.STORAGE_BUCKET,
        "Key": storage_path,
        "Body": file_bytes,
        "ContentType": mime_type,
        "Metadata": {"tenant_id": str(tenant_id)},
    }
    # SSE-AES256 only on real S3; MinIO dev instance has no KMS
    if not settings.STORAGE_ENDPOINT_URL:
        put_kwargs["ServerSideEncryption"] = "AES256"
    try:
        _get_client().put_object(**put_kwargs)
        logger.info("document_uploaded", path=storage_path, size=len(file_bytes))
    except Exception as e:
        logger.error("put_object_failed", bucket=settings.STORAGE_BUCKET, key=storage_path, error=str(e), exc_info=e)
        raise
    return storage_path, checksum


def get_signed_url(storage_path: str, expires_seconds: int = 900) -> str:
    """Returns pre-signed download URL valid for expires_seconds (default 15 min)."""
    return _get_presign_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.STORAGE_BUCKET, "Key": storage_path},
        ExpiresIn=expires_seconds,
    )


def download_document(storage_path: str) -> bytes:
    response = _get_client().get_object(Bucket=settings.STORAGE_BUCKET, Key=storage_path)
    return response["Body"].read()


def delete_document(storage_path: str) -> None:
    _get_client().delete_object(Bucket=settings.STORAGE_BUCKET, Key=storage_path)
    logger.info("document_deleted", path=storage_path)


def _safe_extension(mime_type: str) -> str:
    mapping = {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/tiff": ".tiff",
    }
    return mapping.get(mime_type, ".bin")
