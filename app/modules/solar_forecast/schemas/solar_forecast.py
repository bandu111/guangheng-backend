from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SolarForecastConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNAVAILABLE = "UNAVAILABLE"


class SolarForecastPointSchema(BaseModel):
    time: datetime
    solar_power_w: float | None = None
    shortwave_radiation_w_m2: float | None = None
    cloud_cover_percent: float | None = None
    confidence: SolarForecastConfidence


class SolarForecastSummarySchema(BaseModel):
    next_1h_energy_kwh: float | None = None
    next_3h_energy_kwh: float | None = None
    next_6h_energy_kwh: float | None = None
    next_24h_energy_kwh: float | None = None
    peak_power_w: float | None = None
    peak_time: datetime | None = None


class SolarForecastResponseSchema(BaseModel):
    available: bool
    method: str
    current_solar_w: float | None = None
    current_shortwave_radiation_w_m2: float | None = None
    calibration_ratio: float | None = None
    calibration_source: str | None = None
    calibration_observed_at: datetime | None = None
    forecast: list[SolarForecastPointSchema] = Field(default_factory=list)
    summary: SolarForecastSummarySchema
    observed_at: datetime | None = None
    error_code: str | None = None
