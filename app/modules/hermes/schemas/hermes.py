from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentIntent(str, Enum):
    ENERGY_STATUS = "energy_status"
    WEATHER_FORECAST = "weather_forecast"
    SOLAR_FORECAST = "solar_forecast"
    ENERGY_DECISION = "energy_decision"
    PROPOSAL_REQUEST = "proposal_request"
    AUDIT_QUERY = "audit_query"
    GENERAL = "general"


class AgentResponseStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class HermesChatRequestSchema(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)


class AgentToolTraceSchema(BaseModel):
    tool_name: str
    display_name: str
    success: bool
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    error_code: str | None = None

    model_config = {"from_attributes": True}


class AgentDecisionSchema(BaseModel):
    optimizer_version: str
    strategy: str
    capability: str
    current_value: float | None = None
    target_value: float | None = None
    action_required: bool
    reason_code: str
    confidence: str


class AgentProposalSchema(BaseModel):
    id: int
    status: str
    capability: str
    current_value: float
    target_value: float
    created_at: datetime


class AgentErrorSchema(BaseModel):
    code: str
    message: str
    retryable: bool = False


class HermesChatResponseSchema(BaseModel):
    session_id: str
    message_id: str
    answer: str | None = None
    intent: AgentIntent = AgentIntent.GENERAL
    status: AgentResponseStatus
    tools: list[AgentToolTraceSchema] = Field(default_factory=list)
    decision: AgentDecisionSchema | None = None
    proposal: AgentProposalSchema | None = None
    sources: dict[str, Any] = Field(default_factory=dict)
    error: AgentErrorSchema | None = None

    # Phase 1 compatibility fields. `answer` is the Phase 2B source of truth.
    available: bool
    message: str | None = None
    agent: str = "hermes"
    model_provider: str = "deepseek"
    error_code: str | None = None


class AgentSessionCreateSchema(BaseModel):
    session_id: str
    created_at: datetime


class AgentSessionDetailSchema(BaseModel):
    session_id: str
    status: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class AgentMessageSchema(BaseModel):
    message_id: str
    role: str
    content: str
    intent: AgentIntent | None = None
    status: AgentResponseStatus | None = None
    tools: list[AgentToolTraceSchema] = Field(default_factory=list)
    decision: AgentDecisionSchema | None = None
    proposal: AgentProposalSchema | None = None
    sources: dict[str, Any] = Field(default_factory=dict)
    error: AgentErrorSchema | None = None
    created_at: datetime


class AgentMessageListSchema(BaseModel):
    session_id: str
    count: int
    messages: list[AgentMessageSchema]
