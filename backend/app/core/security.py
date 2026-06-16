import base64
import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    user_id: str, tenant_id: str, role: str, location_id: str | None = None
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "location_id": location_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_PRIVATE_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str, tenant_id: str) -> tuple[str, str]:
    """Returns (raw_token, hashed_token). Store hashed; send raw to client."""
    raw = secrets.token_urlsafe(64)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def decode_access_token(token: str) -> dict[str, str]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_PUBLIC_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "access":
            raise UnauthorizedError("Invalid token type")
        return payload
    except JWTError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _get_aes_key() -> bytes:
    raw = settings.CREDENTIAL_ENCRYPTION_KEY
    return base64.b64decode(raw)


def encrypt_value(plaintext: str) -> str:
    """AES-256-GCM encrypt. Returns base64(nonce + ciphertext)."""
    key = _get_aes_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_value(ciphertext: str) -> str:
    """AES-256-GCM decrypt. Inverse of encrypt_value."""
    key = _get_aes_key()
    data = base64.b64decode(ciphertext)
    nonce, ct = data[:12], data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode()
