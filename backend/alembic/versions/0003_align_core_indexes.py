"""align redundant Phase 2 index with ORM metadata

Revision ID: 0003_align_core_indexes
Revises: 0002_core_domain
Create Date: 2026-09-08
"""

from alembic import op

revision = "0003_align_core_indexes"
down_revision = "0002_core_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The users table already has a unique constraint on email; the Phase 2
    # migration also created a redundant non-unique index.
    op.drop_index("ix_users_email", table_name="users")


def downgrade() -> None:
    op.create_index("ix_users_email", "users", ["email"], unique=False)
