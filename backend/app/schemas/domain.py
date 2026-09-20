import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.domain import (
    Alert,
    EventProcessingStatus,
    DeploymentStatus,
    Environment,
    IncidentStatus,
    InvestigationStatus,
    RemediationStatus,
    RiskLevel,
    RunbookStatus,
    ServiceStatus,
    Severity,
)


def require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include timezone information")
    return value.astimezone(timezone.utc)


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    environment: Environment
    status: ServiceStatus = ServiceStatus.UNKNOWN
    owner_id: uuid.UUID | None = None


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    environment: Environment | None = None
    status: ServiceStatus | None = None
    owner_id: uuid.UUID | None = None


class ServiceRead(ServiceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class EventCreate(BaseModel):
    event_id: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=120)
    service_id: uuid.UUID
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime

    _occurred_at_aware = field_validator("occurred_at")(require_aware)


class EventRead(EventCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    processed: bool
    processing_status: EventProcessingStatus
    processing_attempts: int
    last_processing_error: str | None
    processed_at: datetime | None
    request_id: str | None
    task_id: str | None
    created_at: datetime


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    service_id: uuid.UUID
    source: str
    alert_type: str
    severity: Severity
    message: str
    payload: dict
    occurred_at: datetime
    created_at: datetime


class IncidentCreate(BaseModel):
    incident_number: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    service_id: uuid.UUID
    severity: Severity
    status: IncidentStatus = IncidentStatus.DETECTED
    detected_at: datetime
    assigned_to: uuid.UUID | None = None

    _detected_at_aware = field_validator("detected_at")(require_aware)


class IncidentRead(IncidentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RunbookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2000)
    content: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    status: RunbookStatus = RunbookStatus.DRAFT
    created_by: uuid.UUID


class RunbookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    content: str | None = Field(default=None, min_length=1)
    version: int | None = Field(default=None, ge=1)
    status: RunbookStatus | None = None


class RunbookRead(RunbookCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class Page[T](BaseModel):
    data: list[T]
    pagination: Pagination


class EventPageFilters(BaseModel):
    service_id: uuid.UUID | None = None
    event_type: str | None = None
    source: str | None = None
    processed: bool | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None


class AlertPageFilters(BaseModel):
    service_id: uuid.UUID | None = None
    severity: Severity | None = None
    alert_type: str | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None


class IncidentPageFilters(BaseModel):
    status: IncidentStatus | None = None
    severity: Severity | None = None
    service_id: uuid.UUID | None = None
    assigned_to: uuid.UUID | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


class ManualIncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    service_id: uuid.UUID
    severity: Severity
    detected_at: datetime | None = None

    @field_validator("detected_at")
    @classmethod
    def detected_at_aware(cls, value: datetime | None) -> datetime | None:
        return require_aware(value) if value is not None else value


class IncidentAssignRequest(BaseModel):
    user_id: uuid.UUID


class IncidentTransitionRequest(BaseModel):
    status: IncidentStatus


class TimelineEntry(BaseModel):
    id: uuid.UUID
    action: str
    resource_type: str
    resource_id: str | None
    actor_id: uuid.UUID | None
    result: str
    metadata: dict
    created_at: datetime
