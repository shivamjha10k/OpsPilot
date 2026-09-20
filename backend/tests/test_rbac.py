import asyncio
import uuid

from app.core.auth import require_roles
from app.core.errors import AppError
from app.models.user import Role, User


def make_user(role: Role) -> User:
    return User(
        id=uuid.uuid4(),
        name="Test User",
        email="test@example.com",
        password_hash="unused",
        role=role,
        is_active=True,
    )


def test_admin_role_dependency_allows_admin_only() -> None:
    dependency = require_roles(Role.ADMIN)

    assert asyncio.run(dependency(make_user(Role.ADMIN))).role is Role.ADMIN
    try:
        asyncio.run(dependency(make_user(Role.ENGINEER)))
    except AppError as exc:
        assert exc.status_code == 403
        assert exc.code == "INSUFFICIENT_PERMISSIONS"
    else:
        raise AssertionError("non-admin user passed admin authorization")


def test_engineer_and_viewer_roles_remain_distinct() -> None:
    dependency = require_roles(Role.ENGINEER)

    assert asyncio.run(dependency(make_user(Role.ENGINEER))).role is Role.ENGINEER
    try:
        asyncio.run(dependency(make_user(Role.VIEWER)))
    except AppError as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("viewer passed engineer authorization")
