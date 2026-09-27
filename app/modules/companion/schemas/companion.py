from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CompanionDeviceCodeRequest(BaseModel):
    device_uid: str = Field(min_length=8, max_length=80)
    display_name: str = Field(default="光衡随身终端", max_length=100)


class CompanionDeviceCodeResponse(BaseModel):
    code: str
    poll_token: str
    expires_at: datetime
    poll_interval_seconds: int = 3


class CompanionPairingConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class CompanionPairingPollRequest(BaseModel):
    code: str
    poll_token: str


class CompanionPairingPollResponse(BaseModel):
    status: str
    device_id: str | None = None
    credential: str | None = None


class CompanionApprovalChallengeSchema(BaseModel):
    action_set_id: int
    nonce: str
    action_set_version: str
    expires_at: datetime


class CompanionSnapshotSchema(BaseModel):
    schema_version: str = "1.1"
    observed_at: datetime
    energy: dict[str, Any]
    pending_action_set: dict[str, Any] | None = None
    current_action_set: dict[str, Any] | None = None
    approval_challenge: CompanionApprovalChallengeSchema | None = None


class CompanionApprovalRequest(BaseModel):
    nonce: str = Field(min_length=32, max_length=128)
    action_set_version: str = Field(min_length=1, max_length=40)


class CompanionDeviceSchema(BaseModel):
    device_uid: str
    display_name: str
    paired: bool
    revoked: bool
    paired_at: datetime | None
    last_seen_at: datetime | None

    model_config = {"from_attributes": True}
