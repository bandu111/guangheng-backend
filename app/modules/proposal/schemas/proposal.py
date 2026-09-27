from datetime import datetime

from pydantic import BaseModel, field_serializer

from app.core.datetime_serialization import serialize_utc_datetime
from app.modules.optimizer.schemas.optimizer_v2 import OptimizationDecisionV2Schema
from app.modules.proposal.models.proposal import ProposalStatus
from app.modules.strategy.models.strategy import StrategyMode


class ProposalResponseSchema(BaseModel):
    id: int
    device_id: int
    strategy_mode: StrategyMode
    capability: str
    current_value: float
    target_value: float
    reason_code: str
    reason: str
    status: ProposalStatus
    error_code: str | None = None
    error_message: str | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("approved_at", "rejected_at", "created_at", "updated_at")
    def serialize_timestamps(self, value: datetime | None) -> str | None:
        return serialize_utc_datetime(value)


class ProposalListResponseSchema(BaseModel):
    count: int
    proposals: list[ProposalResponseSchema]


class ProposalGenerationResponseSchema(BaseModel):
    created: bool
    decision: OptimizationDecisionV2Schema
    proposal: ProposalResponseSchema | None = None


class ProposalActionResponseSchema(BaseModel):
    proposal: ProposalResponseSchema
    safety: "SafetyCheckResponseSchema | None" = None
    execution: "ExecutionResponseSchema | None" = None


from app.modules.execution.schemas.execution import ExecutionResponseSchema  # noqa: E402
from app.modules.safety.schemas.safety import SafetyCheckResponseSchema  # noqa: E402

ProposalActionResponseSchema.model_rebuild()
