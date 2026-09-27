from datetime import datetime

from pydantic import BaseModel, Field


class SolarInputChannelSchema(BaseModel):
    key: str
    label: str
    available: bool
    power_w: float | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    energy_kwh: float | None = None
    entity_ids: list[str] = Field(default_factory=list)


class SolarComponentSchema(BaseModel):
    key: str
    label: str
    available: bool
    power_w: float | None = None
    energy_kwh: float | None = None
    entity_ids: list[str] = Field(default_factory=list)


class SolarArrayInsightSchema(BaseModel):
    available: bool
    device_id: str
    device_online: bool
    aggregate_power_w: float | None = None
    mppt_channels: list[SolarInputChannelSchema] = Field(default_factory=list)
    components: list[SolarComponentSchema] = Field(default_factory=list)
    channel_data_available: bool
    component_data_available: bool
    source: str = "home_assistant"
    observed_at: datetime
    diagnostic: str | None = None
