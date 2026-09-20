"""Add durable event processing state for asynchronous workers.

Revision ID: 0005_event_processing_state
Revises: 0004_simulation_runs
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_event_processing_state"
down_revision = "0004_simulation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("processing_status", sa.String(length=32), nullable=False, server_default="PERSISTED"))
    op.add_column("events", sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("events", sa.Column("last_processing_error", sa.String(length=2000), nullable=True))
    op.add_column("events", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("request_id", sa.String(length=120), nullable=True))
    op.add_column("events", sa.Column("task_id", sa.String(length=255), nullable=True))
    op.create_index("ix_events_processing_status", "events", ["processing_status"])
    op.create_index("ix_events_request_id", "events", ["request_id"])
    op.create_index("ix_events_task_id", "events", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_events_task_id", table_name="events")
    op.drop_index("ix_events_request_id", table_name="events")
    op.drop_index("ix_events_processing_status", table_name="events")
    op.drop_column("events", "task_id")
    op.drop_column("events", "request_id")
    op.drop_column("events", "processed_at")
    op.drop_column("events", "last_processing_error")
    op.drop_column("events", "processing_attempts")
    op.drop_column("events", "processing_status")
