"""JWT 与密码哈希"""

from jose import jwt

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.settings import settings


def test_hash_and_verify_password():
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert verify_password("s3cret!", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_access_token():
    token = create_access_token("42")
    assert decode_access_token(token) == "42"
    assert decode_access_token("not-a-jwt") is None


def test_token_contains_subject_and_exp():
    token = create_access_token("99")
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    assert payload["sub"] == "99"
    assert "exp" in payload
