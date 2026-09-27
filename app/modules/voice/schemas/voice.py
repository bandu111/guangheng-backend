from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class VoiceIntent(str, Enum):
    READ_STATUS = "READ_STATUS"
    EXPLAIN = "EXPLAIN"
    EXPLAIN_PROPOSAL = "EXPLAIN_PROPOSAL"
    WHAT_IF = "WHAT_IF"
    STRATEGY_CHANGE_PROPOSAL = "STRATEGY_CHANGE_PROPOSAL"
    DEVICE_CONTROL_PROPOSAL = "DEVICE_CONTROL_PROPOSAL"
    MULTI_DEVICE_GOAL = "MULTI_DEVICE_GOAL"
    APPROVAL_INTENT = "APPROVAL_INTENT"
    REJECT_INTENT = "REJECT_INTENT"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


class VoiceTimingSchema(BaseModel):
    audio_duration_ms: int
    asr_latency_ms: int
    hermes_latency_ms: int
    total_latency_ms: int


class VoiceResponseSchema(BaseModel):
    voice_session_id: str
    transcript: str
    intent: VoiceIntent
    answer: str | None = None
    status: str
    requires_touch_approval: bool = False
    clarification: str | None = None
    pending_action_set: dict[str, Any] | None = None
    hermes_session_id: str | None = None
    hermes_message_id: str | None = None
    tool_names: list[str] = Field(default_factory=list)
    asr_provider: str
    raw_audio_persisted: bool = False
    timing: VoiceTimingSchema
    error_code: str | None = None
