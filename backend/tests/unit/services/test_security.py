import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.exceptions import UnauthorizedError


def test_password_hash_and_verify() -> None:
    hashed = hash_password("mypassword")
    assert hashed != "mypassword"
    assert verify_password("mypassword", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_access_token_roundtrip() -> None:
    import uuid
    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    token = create_access_token(user_id, tenant_id, "owner")
    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["tenant_id"] == tenant_id
    assert payload["role"] == "owner"
    assert payload["type"] == "access"


def test_invalid_token_raises() -> None:
    with pytest.raises(UnauthorizedError):
        decode_access_token("not.a.valid.token")


def test_refresh_token_hash_deterministic() -> None:
    raw = "some-raw-token"
    assert hash_refresh_token(raw) == hash_refresh_token(raw)
    assert hash_refresh_token(raw) != hash_refresh_token("other-token")
