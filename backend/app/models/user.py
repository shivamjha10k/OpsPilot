import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    ENGINEER = "ENGINEER"
    VIEWER = "VIEWER"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", native_enum=False, create_constraint=False),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    owned_services = relationship("Service", back_populates="owner", foreign_keys="Service.owner_id")
    assigned_incidents = relationship("Incident", back_populates="assigned_user", foreign_keys="Incident.assigned_to")
    deployments = relationship("Deployment", back_populates="deployer", foreign_keys="Deployment.deployed_by")
    created_runbooks = relationship("Runbook", back_populates="creator", foreign_keys="Runbook.created_by")
    requested_remediations = relationship(
        "RemediationAction", back_populates="requester", foreign_keys="RemediationAction.requested_by"
    )
    approved_remediations = relationship(
        "RemediationAction", back_populates="approver", foreign_keys="RemediationAction.approved_by"
    )
    approval_requests = relationship("Approval", back_populates="requester", foreign_keys="Approval.requested_by")
    approval_decisions = relationship("Approval", back_populates="approver", foreign_keys="Approval.approved_by")
    created_policies = relationship("Policy", back_populates="creator", foreign_keys="Policy.created_by")
    audit_logs = relationship("AuditLog", back_populates="actor", foreign_keys="AuditLog.actor_id")
    notifications = relationship("Notification", back_populates="user")
    simulation_runs = relationship("SimulationRun", back_populates="actor", foreign_keys="SimulationRun.actor_id")
