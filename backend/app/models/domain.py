import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Table,
    Column,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Environment(str, enum.Enum):
    DEVELOPMENT = "DEVELOPMENT"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


class ServiceStatus(str, enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class Severity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(str, enum.Enum):
    DETECTED = "DETECTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    DIAGNOSED = "DIAGNOSED"
    REMEDIATION_PENDING = "REMEDIATION_PENDING"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


class DeploymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class RunbookStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class InvestigationStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RemediationStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class NotificationChannel(str, enum.Enum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    WEBHOOK = "WEBHOOK"


class NotificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    READ = "READ"


class SimulationStatus(str, enum.Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EventProcessingStatus(str, enum.Enum):
    PERSISTED = "PERSISTED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class KnowledgeDocumentType(str, enum.Enum):
    RUNBOOK = "RUNBOOK"
    HISTORICAL_INCIDENT = "HISTORICAL_INCIDENT"
    TROUBLESHOOTING_DOC = "TROUBLESHOOTING_DOC"
    ARCHITECTURE_DOC = "ARCHITECTURE_DOC"


class KnowledgeDocumentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class KnowledgeIndexStatus(str, enum.Enum):
    NOT_INDEXED = "NOT_INDEXED"
    INDEXING = "INDEXING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


def enum_column(enum_type: type[enum.Enum], length: int = 32):
    return Enum(
        enum_type,
        native_enum=False,
        create_constraint=False,
        validate_strings=True,
        length=length,
    )


def json_column():
    return JSONB().with_variant(JSON(), "sqlite")


def uuid_column():
    return UUID(as_uuid=True).with_variant(String(36), "sqlite")


incident_alerts = Table(
    "incident_alerts",
    Base.metadata,
    Column("incident_id", uuid_column(), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False, primary_key=True),
    Column("alert_id", uuid_column(), ForeignKey("alerts.id", ondelete="RESTRICT"), nullable=False, primary_key=True),
)


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="service_name_not_blank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    environment: Mapped[Environment] = mapped_column(enum_column(Environment), nullable=False)
    status: Mapped[ServiceStatus] = mapped_column(
        enum_column(ServiceStatus), nullable=False, default=ServiceStatus.UNKNOWN, server_default="UNKNOWN"
    )
    simulation_state: Mapped[dict] = mapped_column(json_column(), nullable=False, default=dict, server_default="{}")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner = relationship("User", back_populates="owned_services", foreign_keys=[owner_id])
    events = relationship("Event", back_populates="service", passive_deletes=True)
    alerts = relationship("Alert", back_populates="service", passive_deletes=True)
    incidents = relationship("Incident", back_populates="service", passive_deletes=True)
    logs = relationship("Log", back_populates="service", passive_deletes=True)
    metrics = relationship("Metric", back_populates="service", passive_deletes=True)
    deployments = relationship("Deployment", back_populates="service", passive_deletes=True)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("length(trim(event_id)) > 0", name="event_id_not_blank"),
        CheckConstraint("length(trim(event_type)) > 0", name="event_type_not_blank"),
        Index("ix_events_service_id", "service_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    service_id: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    payload: Mapped[dict] = mapped_column(json_column(), nullable=False, default=dict, server_default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    processing_status: Mapped[EventProcessingStatus] = mapped_column(
        enum_column(EventProcessingStatus), nullable=False, default=EventProcessingStatus.PERSISTED,
        server_default="PERSISTED", index=True
    )
    processing_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_processing_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    service = relationship("Service", back_populates="events")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("length(trim(message)) > 0", name="alert_message_not_blank"),
        Index("ix_alerts_service_occurred", "service_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[Severity] = mapped_column(enum_column(Severity), nullable=False)
    message: Mapped[str] = mapped_column(String(2000), nullable=False)
    payload: Mapped[dict] = mapped_column(json_column(), nullable=False, default=dict, server_default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    service = relationship("Service", back_populates="alerts")
    incidents = relationship("Incident", secondary=incident_alerts, back_populates="alerts")


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("length(trim(incident_number)) > 0", name="incident_number_not_blank"),
        CheckConstraint("length(trim(title)) > 0", name="incident_title_not_blank"),
        Index("ix_incidents_status_severity", "status", "severity"),
        Index("ix_incidents_service_created", "service_id", "created_at"),
        Index("ix_incidents_assigned_to", "assigned_to"),
    )

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    incident_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(5000), nullable=False)
    service_id: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    severity: Mapped[Severity] = mapped_column(enum_column(Severity), nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        enum_column(IncidentStatus), nullable=False, default=IncidentStatus.DETECTED, server_default="DETECTED"
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    service = relationship("Service", back_populates="incidents")
    assigned_user = relationship("User", back_populates="assigned_incidents", foreign_keys=[assigned_to])
    alerts = relationship("Alert", secondary=incident_alerts, back_populates="incidents")
    investigations = relationship("AIInvestigation", back_populates="incident", passive_deletes=True)
    remediation_actions = relationship("RemediationAction", back_populates="incident", passive_deletes=True)


class Log(Base):
    __tablename__ = "logs"
    __table_args__ = (
        CheckConstraint("length(trim(message)) > 0", name="log_message_not_blank"),
        Index("ix_logs_service_occurred", "service_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    service_id: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(String(5000), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", json_column(), nullable=False, default=dict, server_default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    service = relationship("Service", back_populates="logs")


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (
        CheckConstraint("length(trim(metric_name)) > 0", name="metric_name_not_blank"),
        Index("ix_metrics_service_name_occurred", "service_id", "metric_name", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    service_id: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    labels: Mapped[dict] = mapped_column(json_column(), nullable=False, default=dict, server_default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    service = relationship("Service", back_populates="metrics")


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (Index("ix_deployments_service_deployed", "service_id", "deployed_at"),)

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(120), nullable=False)
    environment: Mapped[Environment] = mapped_column(enum_column(Environment), nullable=False)
    status: Mapped[DeploymentStatus] = mapped_column(enum_column(DeploymentStatus), nullable=False)
    deployed_by: Mapped[uuid.UUID | None] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    service = relationship("Service", back_populates="deployments")
    deployer = relationship("User", back_populates="deployments", foreign_keys=[deployed_by])


class Runbook(Base):
    __tablename__ = "runbooks"

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[RunbookStatus] = mapped_column(
        enum_column(RunbookStatus), nullable=False, default=RunbookStatus.DRAFT, server_default="DRAFT", index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    creator = relationship("User", back_populates="created_runbooks", foreign_keys=[created_by])


class AIInvestigation(Base):
    __tablename__ = "ai_investigations"
    __table_args__ = (CheckConstraint("confidence >= 0 AND confidence <= 1", name="investigation_confidence_range"),)

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(String(5000), nullable=False)
    root_cause: Mapped[str] = mapped_column(String(5000), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[dict] = mapped_column(json_column(), nullable=False, default=dict, server_default="{}")
    recommendation: Mapped[str] = mapped_column(String(5000), nullable=False)
    observations: Mapped[list] = mapped_column(json_column(), nullable=False, default=list, server_default="[]")
    probable_root_causes: Mapped[list] = mapped_column(json_column(), nullable=False, default=list, server_default="[]")
    recommendation_data: Mapped[dict] = mapped_column(json_column(), nullable=False, default=dict, server_default="{}")
    knowledge_references: Mapped[list] = mapped_column(json_column(), nullable=False, default=list, server_default="[]")
    risk_level: Mapped[RiskLevel] = mapped_column(enum_column(RiskLevel), nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1", server_default="v1")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[InvestigationStatus] = mapped_column(
        enum_column(InvestigationStatus), nullable=False, default=InvestigationStatus.PENDING, server_default="PENDING"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    incident = relationship("Incident", back_populates="investigations")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="knowledge_title_not_blank"),
        CheckConstraint("length(trim(content)) > 0", name="knowledge_content_not_blank"),
        Index("ix_knowledge_documents_type_status", "document_type", "status"),
        Index("ix_knowledge_documents_service", "service_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    document_type: Mapped[KnowledgeDocumentType] = mapped_column(enum_column(KnowledgeDocumentType), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        uuid_column(), ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )
    environment: Mapped[Environment | None] = mapped_column(enum_column(Environment), nullable=True)
    version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[KnowledgeDocumentStatus] = mapped_column(
        enum_column(KnowledgeDocumentStatus), nullable=False, default=KnowledgeDocumentStatus.DRAFT, server_default="DRAFT"
    )
    index_status: Mapped[KnowledgeIndexStatus] = mapped_column(
        enum_column(KnowledgeIndexStatus), nullable=False, default=KnowledgeIndexStatus.NOT_INDEXED, server_default="NOT_INDEXED"
    )
    index_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class RemediationAction(Base):
    __tablename__ = "remediation_actions"
    __table_args__ = (
        CheckConstraint("length(trim(action_type)) > 0", name="remediation_action_type_not_blank"),
        Index("ix_remediation_actions_requested_by", "requested_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(120), nullable=False)
    parameters: Mapped[dict] = mapped_column(json_column(), nullable=False, default=dict, server_default="{}")
    risk_level: Mapped[RiskLevel] = mapped_column(enum_column(RiskLevel), nullable=False)
    status: Mapped[RemediationStatus] = mapped_column(
        enum_column(RemediationStatus), nullable=False, default=RemediationStatus.PENDING, server_default="PENDING"
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict | None] = mapped_column(json_column(), nullable=True)
    error: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    environment: Mapped[Environment | None] = mapped_column(enum_column(Environment), nullable=True)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        uuid_column(), ForeignKey("policies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    policy_decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    action_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    incident = relationship("Incident", back_populates="remediation_actions")
    requester = relationship("User", back_populates="requested_remediations", foreign_keys=[requested_by])
    approver = relationship("User", back_populates="approved_remediations", foreign_keys=[approved_by])
    approval = relationship("Approval", back_populates="remediation_action", uselist=False, passive_deletes=True)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    remediation_action_id: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("remediation_actions.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        enum_column(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING, server_default="PENDING", index=True
    )
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    remediation_action = relationship("RemediationAction", back_populates="approval")
    requester = relationship("User", back_populates="approval_requests", foreign_keys=[requested_by])
    approver = relationship("User", back_populates="approval_decisions", foreign_keys=[approved_by])


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    action_type: Mapped[str] = mapped_column(String(120), nullable=False)
    environment: Mapped[Environment] = mapped_column(enum_column(Environment), nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(enum_column(RiskLevel), nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    max_frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    configuration: Mapped[dict] = mapped_column(json_column(), nullable=False, default=dict, server_default="{}")
    created_by: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    creator = relationship("User", back_populates="created_policies", foreign_keys=[created_by])


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("length(trim(action)) > 0", name="audit_action_not_blank"),
        CheckConstraint("length(trim(resource_type)) > 0", name="audit_resource_type_not_blank"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    old_value: Mapped[dict | None] = mapped_column(json_column(), nullable=True)
    new_value: Mapped[dict | None] = mapped_column(json_column(), nullable=True)
    result: Mapped[str] = mapped_column(String(120), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", json_column(), nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    actor = relationship("User", back_populates="audit_logs")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(String(2000), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(enum_column(NotificationChannel), nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        enum_column(NotificationStatus), nullable=False, default=NotificationStatus.PENDING, server_default="PENDING", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="notifications")


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    __table_args__ = (
        CheckConstraint("length(trim(scenario)) > 0", name="simulation_scenario_not_blank"),
        CheckConstraint("length(trim(status)) > 0", name="simulation_status_not_blank"),
        Index("ix_simulation_runs_status_started", "status", "started_at"),
        Index("ix_simulation_runs_target_service", "target_service_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(uuid_column(), primary_key=True, default=uuid.uuid4)
    scenario: Mapped[str] = mapped_column(String(120), nullable=False)
    target_service_id: Mapped[uuid.UUID] = mapped_column(
        uuid_column(), ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        uuid_column(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[SimulationStatus] = mapped_column(
        enum_column(SimulationStatus), nullable=False, default=SimulationStatus.CREATED, server_default="CREATED"
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    configuration: Mapped[dict] = mapped_column(json_column(), nullable=False, default=dict, server_default="{}")
    result: Mapped[dict] = mapped_column(json_column(), nullable=False, default=dict, server_default="{}")
    current_state: Mapped[dict] = mapped_column(json_column(), nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    target_service = relationship("Service", foreign_keys=[target_service_id])
    actor = relationship("User", foreign_keys=[actor_id], back_populates="simulation_runs")
