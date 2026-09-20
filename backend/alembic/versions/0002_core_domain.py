"""create Phase 3 core domain tables

Revision ID: 0002_core_domain
Revises: 0001_create_users
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_core_domain"
down_revision = "0001_create_users"
branch_labels = None
depends_on = None


def enum_type(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def json_type():
    return postgresql.JSONB()


def uuid_type():
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "services",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("environment", enum_type("environment", "DEVELOPMENT", "STAGING", "PRODUCTION"), nullable=False),
        sa.Column("status", enum_type("service_status", "HEALTHY", "DEGRADED", "DOWN", "UNKNOWN"), server_default="UNKNOWN", nullable=False),
        sa.Column("owner_id", uuid_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="service_name_not_blank"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_services_owner_id", "services", ["owner_id"])

    op.create_table(
        "events",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("service_id", uuid_type(), nullable=False),
        sa.Column("payload", json_type(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(event_id)) > 0", name="event_id_not_blank"),
        sa.CheckConstraint("length(trim(event_type)) > 0", name="event_type_not_blank"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_events_service_id", "events", ["service_id"])
    op.create_index("ix_events_occurred_at", "events", ["occurred_at"])
    op.create_index("ix_events_processed", "events", ["processed"])

    op.create_table(
        "alerts",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("service_id", uuid_type(), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("alert_type", sa.String(120), nullable=False),
        sa.Column("severity", enum_type("severity", "LOW", "MEDIUM", "HIGH", "CRITICAL"), nullable=False),
        sa.Column("message", sa.String(2000), nullable=False),
        sa.Column("payload", json_type(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(message)) > 0", name="alert_message_not_blank"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_service_occurred", "alerts", ["service_id", "occurred_at"])

    op.create_table(
        "incidents",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("incident_number", sa.String(40), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.String(5000), nullable=False),
        sa.Column("service_id", uuid_type(), nullable=False),
        sa.Column("severity", enum_type("incident_severity", "LOW", "MEDIUM", "HIGH", "CRITICAL"), nullable=False),
        sa.Column("status", enum_type("incident_status", "DETECTED", "ACKNOWLEDGED", "INVESTIGATING", "DIAGNOSED", "REMEDIATION_PENDING", "APPROVAL_PENDING", "EXECUTING", "VERIFYING", "RESOLVED", "FAILED", "ESCALATED"), server_default="DETECTED", nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_to", uuid_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(incident_number)) > 0", name="incident_number_not_blank"),
        sa.CheckConstraint("length(trim(title)) > 0", name="incident_title_not_blank"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_number"),
    )
    op.create_index("ix_incidents_status_severity", "incidents", ["status", "severity"])
    op.create_index("ix_incidents_service_created", "incidents", ["service_id", "created_at"])
    op.create_index("ix_incidents_assigned_to", "incidents", ["assigned_to"])

    op.create_table(
        "incident_alerts",
        sa.Column("incident_id", uuid_type(), nullable=False),
        sa.Column("alert_id", uuid_type(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("incident_id", "alert_id"),
    )

    op.create_table(
        "logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("service_id", uuid_type(), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("message", sa.String(5000), nullable=False),
        sa.Column("metadata", json_type(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(message)) > 0", name="log_message_not_blank"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_logs_service_occurred", "logs", ["service_id", "occurred_at"])

    op.create_table(
        "metrics",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("service_id", uuid_type(), nullable=False),
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("labels", json_type(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(metric_name)) > 0", name="metric_name_not_blank"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metrics_service_name_occurred", "metrics", ["service_id", "metric_name", "occurred_at"])

    op.create_table(
        "deployments",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("service_id", uuid_type(), nullable=False),
        sa.Column("version", sa.String(120), nullable=False),
        sa.Column("environment", enum_type("deployment_environment", "DEVELOPMENT", "STAGING", "PRODUCTION"), nullable=False),
        sa.Column("status", enum_type("deployment_status", "PENDING", "SUCCESS", "FAILED", "ROLLED_BACK"), nullable=False),
        sa.Column("deployed_by", uuid_type(), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deployed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deployments_service_deployed", "deployments", ["service_id", "deployed_at"])

    op.create_table(
        "runbooks",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", enum_type("runbook_status", "DRAFT", "ACTIVE", "ARCHIVED"), server_default="DRAFT", nullable=False),
        sa.Column("created_by", uuid_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runbooks_created_by", "runbooks", ["created_by"])
    op.create_index("ix_runbooks_status", "runbooks", ["status"])

    op.create_table(
        "ai_investigations",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("incident_id", uuid_type(), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("summary", sa.String(5000), nullable=False),
        sa.Column("root_cause", sa.String(5000), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", json_type(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("recommendation", sa.String(5000), nullable=False),
        sa.Column("risk_level", enum_type("investigation_risk_level", "LOW", "MEDIUM", "HIGH", "CRITICAL"), nullable=False),
        sa.Column("status", enum_type("investigation_status", "PENDING", "RUNNING", "COMPLETED", "FAILED"), server_default="PENDING", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="investigation_confidence_range"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_investigations_incident_id", "ai_investigations", ["incident_id"])

    op.create_table(
        "remediation_actions",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("incident_id", uuid_type(), nullable=False),
        sa.Column("action_type", sa.String(120), nullable=False),
        sa.Column("parameters", json_type(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("risk_level", enum_type("remediation_risk_level", "LOW", "MEDIUM", "HIGH", "CRITICAL"), nullable=False),
        sa.Column("status", enum_type("remediation_status", "PENDING", "APPROVAL_REQUIRED", "APPROVED", "REJECTED", "EXECUTING", "COMPLETED", "FAILED", "CANCELLED"), server_default="PENDING", nullable=False),
        sa.Column("requested_by", uuid_type(), nullable=True),
        sa.Column("approved_by", uuid_type(), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", json_type(), nullable=True),
        sa.Column("error", sa.String(5000), nullable=True),
        sa.CheckConstraint("length(trim(action_type)) > 0", name="remediation_action_type_not_blank"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_remediation_actions_incident_id", "remediation_actions", ["incident_id"])
    op.create_index("ix_remediation_actions_requested_by", "remediation_actions", ["requested_by"])

    op.create_table(
        "approvals",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("remediation_action_id", uuid_type(), nullable=False),
        sa.Column("requested_by", uuid_type(), nullable=False),
        sa.Column("approved_by", uuid_type(), nullable=True),
        sa.Column("status", enum_type("approval_status", "PENDING", "APPROVED", "REJECTED", "EXPIRED"), server_default="PENDING", nullable=False),
        sa.Column("reason", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["remediation_action_id"], ["remediation_actions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("remediation_action_id"),
    )
    op.create_index("ix_approvals_requested_by", "approvals", ["requested_by"])
    op.create_index("ix_approvals_status", "approvals", ["status"])

    op.create_table(
        "policies",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("action_type", sa.String(120), nullable=False),
        sa.Column("environment", enum_type("policy_environment", "DEVELOPMENT", "STAGING", "PRODUCTION"), nullable=False),
        sa.Column("risk_level", enum_type("policy_risk_level", "LOW", "MEDIUM", "HIGH", "CRITICAL"), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_allowed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("max_frequency", sa.Integer(), nullable=True),
        sa.Column("configuration", json_type(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_by", uuid_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policies_created_by", "policies", ["created_by"])

    op.create_table(
        "audit_logs",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("actor_id", uuid_type(), nullable=True),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("resource_type", sa.String(120), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("old_value", json_type(), nullable=True),
        sa.Column("new_value", json_type(), nullable=True),
        sa.Column("result", sa.String(120), nullable=False),
        sa.Column("metadata", json_type(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(action)) > 0", name="audit_action_not_blank"),
        sa.CheckConstraint("length(trim(resource_type)) > 0", name="audit_resource_type_not_blank"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])

    op.create_table(
        "notifications",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("user_id", uuid_type(), nullable=False),
        sa.Column("type", sa.String(120), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.String(2000), nullable=False),
        sa.Column("channel", enum_type("notification_channel", "IN_APP", "EMAIL", "WEBHOOK"), nullable=False),
        sa.Column("status", enum_type("notification_status", "PENDING", "SENT", "FAILED", "READ"), server_default="PENDING", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_status", "notifications", ["status"])


def downgrade() -> None:
    for table in (
        "notifications",
        "audit_logs",
        "policies",
        "approvals",
        "remediation_actions",
        "ai_investigations",
        "runbooks",
        "deployments",
        "metrics",
        "logs",
        "incident_alerts",
        "incidents",
        "alerts",
        "events",
        "services",
    ):
        op.drop_table(table)
