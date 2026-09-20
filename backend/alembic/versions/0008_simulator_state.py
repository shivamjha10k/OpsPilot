"""persist simulator state for cross-process tool execution

Revision ID: 0008_simulator_state
Revises: 0007_knowledge_documents
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_simulator_state"
down_revision = "0007_knowledge_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("services", sa.Column("simulation_state", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))


def downgrade() -> None:
    op.drop_column("services", "simulation_state")
