from datetime import datetime

from pydantic import BaseModel, Field


class AreaLoadEntitySchema(BaseModel):
    entity_id: str
    name: str
    device_id: str | None = None
    power_w: float | None = None
    available: bool
    included_in_total: bool


class AreaLoadSchema(BaseModel):
    area_id: str | None
    name: str
    total_power_w: float
    available_count: int
    entity_count: int
    entities: list[AreaLoadEntitySchema] = Field(default_factory=list)


class AreaLoadViewSchema(BaseModel):
    available: bool
    observed_at: datetime
    total_power_w: float
    areas: list[AreaLoadSchema] = Field(default_factory=list)
    unassigned: list[AreaLoadEntitySchema] = Field(default_factory=list)
    diagnostic: str | None = None


class MeterPhaseSchema(BaseModel):
    phase: str
    active_power_w: float | None = None
    current_a: float | None = None
    voltage_v: float | None = None


class MeterChannelSchema(BaseModel):
    channel: str
    total_active_power_w: float | None = None
    total_reactive_power_w: float | None = None
    power_factor: float | None = None
    forward_energy_kwh: float | None = None
    reverse_energy_kwh: float | None = None
    phases: list[MeterPhaseSchema] = Field(default_factory=list)


class SmartMeterInsightSchema(BaseModel):
    available: bool
    device_id: str
    model: str
    online: bool
    meter_type: str | None = None
    observed_at: datetime | None = None
    channels: list[MeterChannelSchema] = Field(default_factory=list)
    diagnostic: str | None = None
