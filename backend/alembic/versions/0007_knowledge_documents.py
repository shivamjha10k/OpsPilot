"""add authoritative knowledge document sources and investigation citations

Revision ID: 0007_knowledge_documents
Revises: 0006_ai_investigation_layer
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_knowledge_documents"
down_revision = "0006_ai_investigation_layer"
branch_labels = None
depends_on = None


def enum_type(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=False)


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_type", enum_type("knowledge_document_type", "RUNBOOK", "HISTORICAL_INCIDENT", "TROUBLESHOOTING_DOC", "ARCHITECTURE_DOC"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("environment", enum_type("knowledge_environment", "DEVELOPMENT", "STAGING", "PRODUCTION"), nullable=True),
        sa.Column("version", sa.String(120), nullable=True),
        sa.Column("status", enum_type("knowledge_document_status", "DRAFT", "ACTIVE", "ARCHIVED"), server_default="DRAFT", nullable=False),
        sa.Column("index_status", enum_type("knowledge_index_status", "NOT_INDEXED", "INDEXING", "INDEXED", "FAILED"), server_default="NOT_INDEXED", nullable=False),
        sa.Column("index_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(title)) > 0", name="knowledge_title_not_blank"),
        sa.CheckConstraint("length(trim(content)) > 0", name="knowledge_content_not_blank"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_documents_type_status", "knowledge_documents", ["document_type", "status"])
    op.create_index("ix_knowledge_documents_service", "knowledge_documents", ["service_id"])
    op.add_column("ai_investigations", sa.Column("knowledge_references", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False))


def downgrade() -> None:
    op.drop_column("ai_investigations", "knowledge_references")
    op.drop_index("ix_knowledge_documents_service", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_type_status", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
