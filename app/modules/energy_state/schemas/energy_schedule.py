from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EnergyScheduleAction(str, Enum):
    STORE_SURPLUS = "STORE_SURPLUS"
    SOLAR_ASSIST = "SOLAR_ASSIST"
    COVER_DEFICIT = "COVER_DEFICIT"
    PRESERVE_RESERVE = "PRESERVE_RESERVE"
    UNAVAILABLE = "UNAVAILABLE"


class EnergySchedulePointSchema(BaseModel):
    time: datetime
    hour: int = Field(ge=0, le=23)
    solar_power_w: float | None = None
    load_power_w: float | None = None
    net_power_w: float | None = None
    action: EnergyScheduleAction
    confidence: str


class EnergyScheduleSummarySchema(BaseModel):
    projected_solar_kwh: float | None = None
    projected_load_kwh: float | None = None
    projected_surplus_kwh: float | None = None
    projected_deficit_kwh: float | None = None


class EnergyScheduleSourceSchema(BaseModel):
    method: str = "forecast_balance_advisory_v1"
    strategy: str
    advisory_only: bool = True
    executable: bool = False
    solar_forecast_method: str
    load_forecast_method: str


class EnergyScheduleResponseSchema(BaseModel):
    available: bool
    horizon_hours: int = 24
    points: list[EnergySchedulePointSchema] = Field(default_factory=list)
    summary: EnergyScheduleSummarySchema
    source: EnergyScheduleSourceSchema
    observed_at: datetime
    error_code: str | None = None
