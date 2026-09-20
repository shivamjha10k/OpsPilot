import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.domain import SimulationStatus


class SimulationTriggerRequest(BaseModel):
    configuration: dict = Field(default_factory=dict)


class SimulationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scenario: str
    target_service_id: uuid.UUID
    target_service_name: str
    actor_id: uuid.UUID | None
    status: SimulationStatus
    started_at: datetime
    stopped_at: datetime | None
    configuration: dict
    result: dict
    current_state: dict
    created_at: datetime
