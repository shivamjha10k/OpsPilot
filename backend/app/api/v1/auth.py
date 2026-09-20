import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.errors import AppError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import LoginRequest, RefreshRequest, TokenResponse, UserResponse
from app.services.auth_service import (
    authenticate_credentials,
    create_access_token,
    create_refresh_token,
    decode_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=dict, summary="Authenticate a user")
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db_session)) -> dict:
    settings = get_settings()
    user = await authenticate_credentials(UserRepository(session), str(payload.email), payload.password)
    return {
        "data": TokenResponse(
            access_token=create_access_token(user.id, settings),
            refresh_token=create_refresh_token(user.id, settings),
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            user=UserResponse.model_validate(user),
        ).model_dump(mode="json")
    }


@router.post("/refresh", response_model=dict, summary="Issue a new access token")
async def refresh(payload: RefreshRequest, session: AsyncSession = Depends(get_db_session)) -> dict:
    settings = get_settings()
    token_payload = decode_token(payload.refresh_token, expected_type="refresh", settings=settings)
    user = await UserRepository(session).get_by_id(uuid.UUID(token_payload["sub"]))
    if user is None or not user.is_active:
        raise AppError("INVALID_REFRESH_TOKEN", "Invalid refresh token", 401)
    return {
        "data": {
            "access_token": create_access_token(user.id, settings),
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }
    }


@router.post("/logout", response_model=dict, summary="Log out the current client")
async def logout(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "data": {
            "message": "Logged out. Discard the access and refresh tokens on the client.",
            "user_id": str(current_user.id),
        }
    }


@router.get("/me", response_model=dict, summary="Get the authenticated user")
async def me(current_user: User = Depends(get_current_user)) -> dict:
    return {"data": UserResponse.model_validate(current_user).model_dump(mode="json")}
