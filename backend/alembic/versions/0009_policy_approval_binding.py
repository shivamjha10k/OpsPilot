"""add policy decision snapshots and approval expiry"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_policy_approval_binding"
down_revision = "0008_simulator_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("remediation_actions", sa.Column("environment", sa.String(length=32), nullable=True))
    op.add_column("remediation_actions", sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("remediation_actions", sa.Column("policy_decision", sa.String(length=40), nullable=True))
    op.add_column("remediation_actions", sa.Column("policy_version", sa.String(length=120), nullable=True))
    op.add_column("remediation_actions", sa.Column("action_fingerprint", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_remediation_actions_policy_id", "remediation_actions", "policies", ["policy_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_remediation_actions_policy_id", "remediation_actions", ["policy_id"])
    op.create_index("ix_remediation_actions_action_fingerprint", "remediation_actions", ["action_fingerprint"])
    op.add_column("approvals", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE approvals SET expires_at = created_at + interval '60 minutes' WHERE expires_at IS NULL")
    op.alter_column("approvals", "expires_at", nullable=False)


def downgrade() -> None:
    op.drop_column("approvals", "expires_at")
    op.drop_index("ix_remediation_actions_action_fingerprint", table_name="remediation_actions")
    op.drop_index("ix_remediation_actions_policy_id", table_name="remediation_actions")
    op.drop_constraint("fk_remediation_actions_policy_id", "remediation_actions", type_="foreignkey")
    for column in ("action_fingerprint", "policy_version", "policy_decision", "policy_id", "environment"):
        op.drop_column("remediation_actions", column)
