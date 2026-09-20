"""Tests for the test-database safety mechanism itself.

These tests verify that the conftest.py safety guards work correctly,
ensuring destructive fixtures can never target the runtime database.
"""

import pytest

from tests.conftest import (
    ALLOWED_TEST_DATABASE_NAMES,
    UnsafeTestDatabaseError,
    extract_database_name,
    validate_test_database_url,
)


# -----------------------------------------------------------------------
# extract_database_name
# -----------------------------------------------------------------------

class TestExtractDatabaseName:
    """Verify correct database name parsing from various URL formats."""

    def test_standard_asyncpg_url(self):
        url = "postgresql+asyncpg://opspilot:pass@localhost:5433/test_db"
        assert extract_database_name(url) == "test_db"

    def test_standard_postgresql_url(self):
        url = "postgresql://opspilot:pass@localhost:5432/opspilot_test"
        assert extract_database_name(url) == "opspilot_test"

    def test_runtime_database_name(self):
        url = "postgresql+asyncpg://opspilot:pass@postgres:5432/opspilot"
        assert extract_database_name(url) == "opspilot"

    def test_url_with_query_parameters(self):
        """Query parameters must NOT affect the extracted database name."""
        url = "postgresql+asyncpg://opspilot:pass@localhost:5433/opspilot?application_name=test"
        assert extract_database_name(url) == "opspilot"

    def test_url_with_test_in_hostname(self):
        """A 'test' substring in the host must not affect database name."""
        url = "postgresql+asyncpg://opspilot:pass@test-host:5433/opspilot"
        assert extract_database_name(url) == "opspilot"

    def test_url_with_test_in_password(self):
        """A 'test' substring in the password must not affect database name."""
        url = "postgresql+asyncpg://opspilot:test-password@localhost:5433/opspilot"
        assert extract_database_name(url) == "opspilot"

    def test_empty_path_raises(self):
        url = "postgresql+asyncpg://opspilot:pass@localhost:5433"
        with pytest.raises(ValueError, match="Cannot extract a database name"):
            extract_database_name(url)

    def test_slash_only_path_raises(self):
        url = "postgresql+asyncpg://opspilot:pass@localhost:5433/"
        with pytest.raises(ValueError, match="Cannot extract a database name"):
            extract_database_name(url)


# -----------------------------------------------------------------------
# validate_test_database_url
# -----------------------------------------------------------------------

class TestValidateTestDatabaseUrl:
    """Verify the allowlist-based safety validation."""

    # --- CASE C: test_db is accepted ---
    def test_test_db_is_accepted(self):
        url = "postgresql+asyncpg://opspilot:pass@localhost:5433/test_db"
        result = validate_test_database_url(url)
        assert result == "test_db"

    # --- CASE D: opspilot_test is accepted ---
    def test_opspilot_test_is_accepted(self):
        url = "postgresql+asyncpg://opspilot:pass@localhost:5433/opspilot_test"
        result = validate_test_database_url(url)
        assert result == "opspilot_test"

    # --- CASE B: opspilot is rejected ---
    def test_opspilot_is_rejected(self):
        url = "postgresql+asyncpg://opspilot:pass@localhost:5433/opspilot"
        with pytest.raises(UnsafeTestDatabaseError, match="TEST DATABASE SAFETY CHECK FAILED"):
            validate_test_database_url(url)

    def test_rejection_message_contains_database_name(self):
        url = "postgresql+asyncpg://opspilot:pass@localhost:5433/opspilot"
        with pytest.raises(UnsafeTestDatabaseError, match="'opspilot'"):
            validate_test_database_url(url)

    def test_rejection_message_contains_allowed_names(self):
        url = "postgresql+asyncpg://opspilot:pass@localhost:5433/opspilot"
        with pytest.raises(UnsafeTestDatabaseError, match="opspilot_test"):
            validate_test_database_url(url)

    # --- CASE E: opspilot with query param 'test' is still rejected ---
    def test_opspilot_with_test_query_param_is_rejected(self):
        url = "postgresql+asyncpg://opspilot:pass@localhost:5433/opspilot?application_name=test"
        with pytest.raises(UnsafeTestDatabaseError, match="TEST DATABASE SAFETY CHECK FAILED"):
            validate_test_database_url(url)

    def test_unknown_database_is_rejected(self):
        url = "postgresql+asyncpg://opspilot:pass@localhost:5433/production"
        with pytest.raises(UnsafeTestDatabaseError):
            validate_test_database_url(url)

    def test_empty_database_raises_value_error(self):
        url = "postgresql+asyncpg://opspilot:pass@localhost:5433/"
        with pytest.raises(ValueError):
            validate_test_database_url(url)


# -----------------------------------------------------------------------
# Allowlist integrity
# -----------------------------------------------------------------------

class TestAllowlistIntegrity:
    """Verify the allowlist is correctly configured."""

    def test_opspilot_is_not_in_allowlist(self):
        assert "opspilot" not in ALLOWED_TEST_DATABASE_NAMES

    def test_test_db_is_in_allowlist(self):
        assert "test_db" in ALLOWED_TEST_DATABASE_NAMES

    def test_opspilot_test_is_in_allowlist(self):
        assert "opspilot_test" in ALLOWED_TEST_DATABASE_NAMES

    def test_allowlist_is_frozen(self):
        """The allowlist must be immutable to prevent runtime tampering."""
        assert isinstance(ALLOWED_TEST_DATABASE_NAMES, frozenset)
