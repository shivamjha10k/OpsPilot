"""Add simulator execution control records.

Revision ID: 0004_simulation_runs
Revises: 0003_align_core_indexes
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_simulation_runs"
down_revision = "0003_align_core_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario", sa.String(length=120), nullable=False),
        sa.Column("target_service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CREATED"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("current_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(scenario)) > 0", name="simulation_scenario_not_blank"),
        sa.CheckConstraint("length(trim(status)) > 0", name="simulation_status_not_blank"),
        sa.ForeignKeyConstraint(["target_service_id"], ["services.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_simulation_runs_status_started", "simulation_runs", ["status", "started_at"])
    op.create_index("ix_simulation_runs_target_service", "simulation_runs", ["target_service_id", "started_at"])
    op.create_index("ix_simulation_runs_actor_id", "simulation_runs", ["actor_id"])


def downgrade() -> None:
    op.drop_index("ix_simulation_runs_actor_id", table_name="simulation_runs")
    op.drop_index("ix_simulation_runs_target_service", table_name="simulation_runs")
    op.drop_index("ix_simulation_runs_status_started", table_name="simulation_runs")
    op.drop_table("simulation_runs")
