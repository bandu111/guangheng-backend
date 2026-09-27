from datetime import datetime

from pydantic import BaseModel, field_serializer

from app.core.datetime_serialization import serialize_utc_datetime
from app.modules.execution.models.execution import ExecutionStatus


class ExecutionResponseSchema(BaseModel):
    id: int
    proposal_id: int
    device_id: int
    capability: str
    ha_entity_id: str
    requested_value: float
    readback_value: float | None = None
    status: ExecutionStatus
    ha_domain: str
    ha_service: str
    error_code: str | None = None
    error_message: str | None = None
    requested_at: datetime
    executed_at: datetime | None = None
    verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}

    @field_serializer(
        "requested_at",
        "executed_at",
        "verified_at",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
    )
    def serialize_timestamps(self, value: datetime | None) -> str | None:
        return serialize_utc_datetime(value)


class ExecutionListResponseSchema(BaseModel):
    count: int
    executions: list[ExecutionResponseSchema]
