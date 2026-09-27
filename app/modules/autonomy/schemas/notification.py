from datetime import datetime

from pydantic import BaseModel, Field, field_serializer

from app.core.datetime_serialization import serialize_utc_datetime
from app.modules.autonomy.models.notification_event import (
    NotificationEventType,
    NotificationSeverity,
    NotificationStatus,
)


class NotificationPayloadSchema(BaseModel):
    strategy: str | None = None
    capability: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    reason_code: str | None = None
    confidence: str | None = None
    proposal_id: int | None = None
    existing_proposal_id: int | None = None
    recommended_target: float | None = None
    error_code: str | None = None


class NotificationEventSchema(BaseModel):
    id: int
    event_type: NotificationEventType
    title: str
    message: str
    severity: NotificationSeverity
    status: NotificationStatus
    decision_run_id: int
    proposal_id: int | None = None
    dedupe_key: str
    payload: NotificationPayloadSchema = Field(default_factory=NotificationPayloadSchema)
    created_at: datetime
    read_at: datetime | None = None

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "read_at")
    def serialize_timestamps(self, value: datetime | None) -> str | None:
        return serialize_utc_datetime(value)


class NotificationEventListSchema(BaseModel):
    count: int
    notifications: list[NotificationEventSchema]
