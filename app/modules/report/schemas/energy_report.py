from datetime import date, datetime

from pydantic import BaseModel, Field


class EnergyReportMetricsSchema(BaseModel):
    consumption_kwh: float | None = None
    generation_kwh: float | None = None
    grid_import_kwh: float | None = None
    grid_export_kwh: float | None = None
    solar_self_consumption_kwh: float | None = None
    solar_self_use_percent: float | None = None
    reference_baseline_cost_cny: float | None = None
    actual_grid_cost_cny: float | None = None
    savings_cny: float | None = None
    savings_percent: float | None = None
    carbon_reduction_kg: float | None = None


class EnergyReportDailyPointSchema(BaseModel):
    date: date
    consumption_kwh: float | None = None
    generation_kwh: float | None = None
    grid_import_kwh: float | None = None
    actual_grid_cost_cny: float | None = None
    savings_cny: float | None = None
    carbon_reduction_kg: float | None = None


class EnergyReportPeriodSchema(BaseModel):
    period: str
    start_at: datetime
    end_at: datetime
    metrics: EnergyReportMetricsSchema
    daily: list[EnergyReportDailyPointSchema] = Field(default_factory=list)
    coverage_percent: float = Field(default=0, ge=0, le=100)


class EnergyReportTariffSourceSchema(BaseModel):
    price_per_kwh: float
    currency: str
    provider: str
    pricing_type: str
    realtime: bool
    reference_date: str | None = None


class EnergyReportCarbonSourceSchema(BaseModel):
    factor_kg_co2_per_kwh: float
    provider: str
    region: str
    reference_year: int
    published_date: str
    source_url: str


class EnergyReportSourceSchema(BaseModel):
    provider: str = "home_assistant_recorder"
    aggregation_method: str = "power_step_time_integral_v1"
    cost_baseline_method: str
    actual_cost_method: str
    savings_method: str


class EnergyReportResponseSchema(BaseModel):
    available: bool
    periods: dict[str, EnergyReportPeriodSchema] = Field(default_factory=dict)
    tariff: EnergyReportTariffSourceSchema | None = None
    carbon: EnergyReportCarbonSourceSchema | None = None
    source: EnergyReportSourceSchema
    observed_at: datetime
    error_code: str | None = None
