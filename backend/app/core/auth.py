import uuid
from collections.abc import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.errors import AppError
from app.models.user import Role, User
from app.repositories.user_repository import UserRepository
from app.services.auth_service import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError("AUTHENTICATION_REQUIRED", "Authentication is required", 401)

    payload = decode_token(credentials.credentials, expected_type="access", settings=get_settings())
    user = await UserRepository(session).get_by_id(uuid.UUID(payload["sub"]))
    if user is None:
        raise AppError("INVALID_TOKEN", "Invalid authentication token", 401)
    if not user.is_active:
        raise AppError("USER_INACTIVE", "User account is inactive", 401)
    return user


def require_roles(*roles: Role) -> Callable:
    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise AppError("INSUFFICIENT_PERMISSIONS", "You do not have permission for this action", 403)
        return current_user

    return dependency
