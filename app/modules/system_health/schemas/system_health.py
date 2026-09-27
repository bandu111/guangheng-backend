from datetime import datetime

from pydantic import BaseModel, Field


class HealthCheckSchema(BaseModel):
    key: str
    label: str
    status: str
    detail: str
    blocking: bool = False


class DeviceHealthSchema(BaseModel):
    device_id: str
    model: str
    online: bool
    unavailable_capabilities: int
    verified_controls: int
    unverified_controls: int
    observed_at: datetime | None = None


class SystemHealthSchema(BaseModel):
    status: str
    observed_at: datetime
    checks: list[HealthCheckSchema] = Field(default_factory=list)
    devices: list[DeviceHealthSchema] = Field(default_factory=list)
    recovery_actions: list[str] = Field(default_factory=list)

