from datetime import datetime
from enum import Enum

from pydantic import BaseModel, field_serializer

from app.core.datetime_serialization import serialize_utc_datetime
from app.modules.autonomy.models.autonomous_decision_run import (
    AutonomousRunStatus,
    AutonomousTriggerType,
)
from app.modules.autonomy.models.autonomy_config import AutonomyLevel


class AgentState(str, Enum):
    MONITORING = "MONITORING"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"


class AutonomousDecisionRunSchema(BaseModel):
    id: int
    trigger_type: AutonomousTriggerType
    status: AutonomousRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    strategy: str | None = None
    capability: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    action_required: bool | None = None
    reason_code: str | None = None
    confidence: str | None = None
    proposal_id: int | None = None
    notification_event_id: int | None = None
    result_code: str | None = None
    error_code: str | None = None
    context_observed_at: datetime | None = None
    decision_version: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer(
        "started_at", "completed_at", "context_observed_at", "created_at"
    )
    def serialize_timestamps(self, value: datetime | None) -> str | None:
        return serialize_utc_datetime(value)


class AutonomousDecisionListSchema(BaseModel):
    count: int
    decisions: list[AutonomousDecisionRunSchema]


class LatestDecisionSchema(BaseModel):
    run_id: int
    strategy: str | None = None
    optimizer_version: str | None = None
    confidence: str | None = None
    capability: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    action_required: bool | None = None
    reason_code: str | None = None
    evaluated_at: datetime
    result_code: str | None = None

    @field_serializer("evaluated_at")
    def serialize_evaluated_at(self, value: datetime) -> str:
        serialized = serialize_utc_datetime(value)
        assert serialized is not None
        return serialized


class PendingProposalSummarySchema(BaseModel):
    id: int
    status: str
    capability: str
    current_value: float
    target_value: float


class AutonomyStatusSchema(BaseModel):
    enabled: bool
    interval_seconds: int
    running: bool
    last_run: AutonomousDecisionRunSchema | None = None
    next_run_at: datetime | None = None
    agent_state: AgentState
    autonomy_level: AutonomyLevel
    latest_decision: LatestDecisionSchema | None = None
    pending_proposal: PendingProposalSummarySchema | None = None
    unread_notification_count: int
