from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class LoadForecastConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNAVAILABLE = "UNAVAILABLE"


class LoadForecastPointSchema(BaseModel):
    time: datetime
    load_power_w: float | None = None
    historical_samples: int
    confidence: LoadForecastConfidence


class LoadForecastSummarySchema(BaseModel):
    next_1h_energy_kwh: float | None = None
    next_3h_energy_kwh: float | None = None
    next_6h_energy_kwh: float | None = None
    next_24h_energy_kwh: float | None = None
    peak_power_w: float | None = None
    peak_time: datetime | None = None


class LoadForecastResponseSchema(BaseModel):
    available: bool
    method: str
    history_days_requested: int
    history_samples: int
    history_start_at: datetime | None = None
    history_end_at: datetime | None = None
    current_load_w: float | None = None
    forecast: list[LoadForecastPointSchema] = Field(default_factory=list)
    summary: LoadForecastSummarySchema
    observed_at: datetime | None = None
    error_code: str | None = None
