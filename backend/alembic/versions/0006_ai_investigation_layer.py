"""add structured AI investigation lifecycle fields

Revision ID: 0006_ai_investigation_layer
Revises: 0005_event_processing_state
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_ai_investigation_layer"
down_revision = "0005_event_processing_state"
branch_labels = None
depends_on = None


def json_type():
    return postgresql.JSONB()


def upgrade() -> None:
    op.add_column("ai_investigations", sa.Column("observations", json_type(), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("ai_investigations", sa.Column("probable_root_causes", json_type(), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("ai_investigations", sa.Column("recommendation_data", json_type(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("ai_investigations", sa.Column("requires_approval", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("ai_investigations", sa.Column("prompt_version", sa.String(40), server_default="v1", nullable=False))
    op.add_column("ai_investigations", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("ai_investigations", sa.Column("error_code", sa.String(120), nullable=True))
    op.add_column("ai_investigations", sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ai_investigations", sa.Column("task_id", sa.String(255), nullable=True))
    op.add_column("ai_investigations", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_investigations", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_ai_investigations_requested_by_users", "ai_investigations", "users", ["requested_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_ai_investigations_requested_by", "ai_investigations", ["requested_by"])
    op.create_index("ix_ai_investigations_task_id", "ai_investigations", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_investigations_task_id", table_name="ai_investigations")
    op.drop_index("ix_ai_investigations_requested_by", table_name="ai_investigations")
    op.drop_constraint("fk_ai_investigations_requested_by_users", "ai_investigations", type_="foreignkey")
    for name in ("completed_at", "started_at", "task_id", "requested_by", "error_code", "duration_ms", "prompt_version", "requires_approval", "recommendation_data", "probable_root_causes", "observations"):
        op.drop_column("ai_investigations", name)
