from datetime import date, datetime

from pydantic import BaseModel, Field


class EnergyTodaySummarySchema(BaseModel):
    generation_kwh: float | None = None
    consumption_kwh: float | None = None
    grid_import_kwh: float | None = None
    avoided_grid_kwh: float | None = None
    savings_cny: float | None = None
    generation_change_percent: float | None = None
    consumption_change_percent: float | None = None
    savings_change_percent: float | None = None
    tariff_price_per_kwh: float | None = None
    currency: str = "CNY"
    savings_is_estimate: bool = True


class EnergyTodayFlowPointSchema(BaseModel):
    time: datetime
    hour: int = Field(ge=0, le=23)
    solar_power_w: float | None = None
    home_load_w: float | None = None
    grid_import_w: float | None = None
    coverage_percent: float = Field(ge=0, le=100)


class EnergyTodaySourceSchema(BaseModel):
    provider: str = "home_assistant_recorder"
    aggregation_method: str = "power_step_time_integral_v1"
    pricing_type: str = "reference_average"
    realtime_tariff: bool = False
    sample_count: int = 0
    coverage_percent: float = Field(default=0, ge=0, le=100)


class EnergyTodayResponseSchema(BaseModel):
    available: bool
    date: date
    time_zone: str
    summary: EnergyTodaySummarySchema
    flow: list[EnergyTodayFlowPointSchema] = Field(default_factory=list)
    source: EnergyTodaySourceSchema
    observed_at: datetime
    error_code: str | None = None
