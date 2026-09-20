import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings
from app.core.errors import AppError
from app.models.user import User
from app.repositories.user_repository import UserRepository


password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _create_token(*, user_id: uuid.UUID, token_type: str, lifetime: timedelta, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: uuid.UUID, settings: Settings) -> str:
    return _create_token(
        user_id=user_id,
        token_type="access",
        lifetime=timedelta(minutes=settings.access_token_expire_minutes),
        settings=settings,
    )


def create_refresh_token(user_id: uuid.UUID, settings: Settings) -> str:
    return _create_token(
        user_id=user_id,
        token_type="refresh",
        lifetime=timedelta(days=settings.refresh_token_expire_days),
        settings=settings,
    )


def decode_token(token: str, *, expected_type: str, settings: Settings) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "type", "iat", "exp", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError("TOKEN_EXPIRED", "Token has expired", 401) from exc
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise AppError("INVALID_TOKEN", "Invalid authentication token", 401) from exc

    if payload.get("type") != expected_type:
        code = "INVALID_REFRESH_TOKEN" if expected_type == "refresh" else "INVALID_TOKEN"
        raise AppError(code, "Invalid authentication token", 401)
    try:
        uuid.UUID(str(payload["sub"]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise AppError("INVALID_TOKEN", "Invalid authentication token", 401) from exc
    return payload


async def authenticate_credentials(repository: UserRepository, email: str, password: str) -> User:
    user = await repository.get_by_email(email)
    if user is None or not verify_password(password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Invalid email or password.", 401)
    if not user.is_active:
        raise AppError("INVALID_CREDENTIALS", "Invalid email or password.", 401)
    return user
