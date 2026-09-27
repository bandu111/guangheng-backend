from datetime import date as DateType, datetime

from pydantic import BaseModel, Field


class StationNodeSchema(BaseModel):
    key: str
    label: str
    available: bool
    power_w: float | None = None
    direction: str = "idle"
    status: str | None = None


class StationTodaySchema(BaseModel):
    date: DateType | None = None
    generation_kwh: float | None = None
    consumption_kwh: float | None = None
    grid_import_kwh: float | None = None
    savings_cny: float | None = None
    coverage_percent: float = 0


class StationSourceSchema(BaseModel):
    device_id: int | None = None
    source_device_id: str | None = None
    display_name: str | None = None
    source_mode: str | None = None


class StationSummarySchema(BaseModel):
    available: bool
    online: bool
    data_quality: str
    source: StationSourceSchema
    nodes: list[StationNodeSchema] = Field(default_factory=list)
    today: StationTodaySchema
    observed_at: datetime
    last_updated: datetime | None = None
    diagnostic: str | None = None
