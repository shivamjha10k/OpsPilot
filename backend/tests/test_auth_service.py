import uuid
import jwt

from app.core.config import Settings
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_passwords_are_argon2_hashes_and_verify() -> None:
    hashed = hash_password("CorrectHorseBatteryStaple!")

    assert hashed.startswith("$argon2")
    assert verify_password("CorrectHorseBatteryStaple!", hashed)
    assert not verify_password("wrong", hashed)


def test_access_and_refresh_tokens_have_distinct_types() -> None:
    settings = Settings(jwt_secret="a" * 32)
    user_id = uuid.uuid4()

    access = decode_token(create_access_token(user_id, settings), expected_type="access", settings=settings)
    refresh = decode_token(create_refresh_token(user_id, settings), expected_type="refresh", settings=settings)

    assert access["sub"] == str(user_id)
    assert access["type"] == "access"
    assert refresh["type"] == "refresh"


def test_refresh_token_cannot_be_used_as_access_token() -> None:
    settings = Settings(jwt_secret="a" * 32)
    token = create_refresh_token(uuid.uuid4(), settings)

    try:
        decode_token(token, expected_type="access", settings=settings)
    except Exception as exc:
        assert getattr(exc, "code", None) == "INVALID_TOKEN"
    else:
        raise AssertionError("refresh token was accepted as an access token")


def test_expired_token_is_rejected() -> None:
    settings = Settings(jwt_secret="a" * 32)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "iat": 1,
            "exp": 1,
            "jti": str(uuid.uuid4()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    try:
        decode_token(token, expected_type="access", settings=settings)
    except Exception as exc:
        assert getattr(exc, "code", None) == "TOKEN_EXPIRED"
    else:
        raise AssertionError("expired token was accepted")


def test_token_signature_tampering_is_rejected() -> None:
    settings = Settings(jwt_secret="a" * 32)
    token = create_access_token(uuid.uuid4(), settings)
    header, payload, signature = token.split(".")
    replacement = "a" if signature[0] != "a" else "b"
    tampered = ".".join((header, payload, replacement + signature[1:]))

    try:
        decode_token(tampered, expected_type="access", settings=settings)
    except Exception as exc:
        assert getattr(exc, "code", None) == "INVALID_TOKEN"
    else:
        raise AssertionError("tampered token was accepted")
