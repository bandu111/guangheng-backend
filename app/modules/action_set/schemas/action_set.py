from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.action_set.models.action_set import (
    ActionSetItemStatus,
    ActionSetStatus,
    ActionSetVerificationStatus,
)


class ActionSetItemSchema(BaseModel):
    id: int
    sequence: int
    device_id: int
    source_device_id: str
    device_name: str
    capability: str
    current_value: float
    target_value: float
    expected_delta_w: float | None = None
    proposal_id: int
    execution_id: int | None = None
    status: ActionSetItemStatus
    result_code: str | None = None
    result_message: str | None = None

    model_config = {"from_attributes": True}


class ActionSetSchema(BaseModel):
    id: int
    opportunity_code: str
    title: str
    reason: str
    status: ActionSetStatus
    expected_grid_delta_w: float | None = None
    before_grid_power_w: float | None = None
    after_grid_power_w: float | None = None
    actual_grid_delta_w: float | None = None
    verification_status: ActionSetVerificationStatus
    verification_message: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    items: list[ActionSetItemSchema] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ActionSetListSchema(BaseModel):
    count: int
    action_sets: list[ActionSetSchema]


class ActionSetGenerateRequest(BaseModel):
    opportunity_code: str = "SOLAR_SURPLUS_SELF_CONSUMPTION"
