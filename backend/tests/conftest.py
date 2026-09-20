"""Centralized test-database safety configuration.

This module is the single source of truth for test database isolation.
It ensures that destructive test fixtures (Base.metadata.create_all /
Base.metadata.drop_all) can NEVER execute against the OpsPilot runtime
or development database.

Safety rules
============
1.  ``TEST_DATABASE_URL`` must be set explicitly as an environment variable.
    If absent, all integration tests that require a database are skipped.
    The test system NEVER falls back to ``DATABASE_URL``.

2.  When ``TEST_DATABASE_URL`` is present, its **database name** (parsed from
    the URL path component) is validated against an explicit allowlist.

3.  Any database name that is NOT on the allowlist is **rejected with a hard
    RuntimeError** before any ``create_all`` / ``drop_all`` can execute.

4.  The shared ``safe_test_engine`` fixture centralises the validation so
    that individual test modules do not need to duplicate safety logic.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Explicit allowlist of database names that destructive test fixtures may
#: target.  Only names in this set are accepted.  Everything else -- including
#: ``opspilot`` -- is rejected.
ALLOWED_TEST_DATABASE_NAMES: frozenset[str] = frozenset({
    "test_db",
    "opspilot_test",
})

#: Read from the environment exactly once at import time.
TEST_DATABASE_URL: str | None = os.environ.get("TEST_DATABASE_URL")


# ---------------------------------------------------------------------------
# URL parsing / validation helpers
# ---------------------------------------------------------------------------

def extract_database_name(url: str) -> str:
    """Extract the database name from a SQLAlchemy-style database URL.

    Handles both ``postgresql://`` and ``postgresql+asyncpg://`` schemes.
    The database name is the last path component after stripping leading
    slashes.

    Raises ``ValueError`` if the database name cannot be determined.
    """
    parsed = urlparse(url)
    # The path is typically "/<dbname>" -- strip the leading slash.
    db_name = parsed.path.lstrip("/")
    if not db_name:
        raise ValueError(
            f"Cannot extract a database name from TEST_DATABASE_URL: {url!r}. "
            f"The URL path component is empty."
        )
    return db_name


class UnsafeTestDatabaseError(RuntimeError):
    """Raised when TEST_DATABASE_URL targets a non-test database."""


def validate_test_database_url(url: str) -> str:
    """Validate that *url* targets an allowlisted test database.

    Returns the parsed database name on success.

    Raises ``UnsafeTestDatabaseError`` with an actionable message on failure.
    """
    db_name = extract_database_name(url)

    if db_name not in ALLOWED_TEST_DATABASE_NAMES:
        raise UnsafeTestDatabaseError(
            f"\n{'=' * 70}\n"
            f"TEST DATABASE SAFETY CHECK FAILED\n"
            f"{'=' * 70}\n"
            f"\n"
            f"  TEST_DATABASE_URL targets database: {db_name!r}\n"
            f"\n"
            f"  This database name is NOT in the allowlist.\n"
            f"  Destructive test fixtures (create_all / drop_all) REFUSE to operate\n"
            f"  on any database not explicitly allowed.\n"
            f"\n"
            f"  Allowed database names: {sorted(ALLOWED_TEST_DATABASE_NAMES)}\n"
            f"\n"
            f"  To fix:\n"
            f"    1. Create a dedicated test database (e.g. 'test_db').\n"
            f"    2. Set TEST_DATABASE_URL to point to that database.\n"
            f"       Example:\n"
            f"         $env:TEST_DATABASE_URL=\"postgresql+asyncpg://opspilot:password@localhost:5433/test_db\"\n"
            f"\n"
            f"  The runtime 'opspilot' database must NEVER be used for tests.\n"
            f"{'=' * 70}\n"
        )
    return db_name


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def safe_test_engine():
    """Create a SQLAlchemy async engine that has passed safety validation.

    Usage in test modules::

        @pytest_asyncio.fixture
        async def session(safe_test_engine):
            async with safe_test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
            ...

    The fixture validates TEST_DATABASE_URL **before** creating the engine.
    If the URL is missing, a ``pytest.skip`` is raised.
    If the URL targets a non-test database, an ``UnsafeTestDatabaseError``
    is raised (hard failure, not a skip).
    """
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set -- skipping database integration test")

    # Hard safety gate -- raises UnsafeTestDatabaseError if the database
    # name is not in the allowlist.
    validate_test_database_url(TEST_DATABASE_URL)

    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield engine
    await engine.dispose()
