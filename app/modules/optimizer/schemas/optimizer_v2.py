from pydantic import BaseModel

from app.modules.strategy.models.strategy import StrategyMode


class OptimizerV2EvidenceSchema(BaseModel):
    current_soc_percent: float | None = None
    battery_capacity_kwh: float | None = None

    solar_6h_kwh: float | None = None
    load_6h_kwh: float | None = None
    net_energy_6h_kwh: float | None = None

    solar_24h_kwh: float | None = None
    load_24h_kwh: float | None = None
    net_energy_24h_kwh: float | None = None

    solar_forecast_confidence: str
    load_forecast_confidence: str
    decision_confidence: str

    weather_condition: str | None = None
    weather_cloud_cover_percent: float | None = None

    tariff_price_per_kwh: float | None = None
    tariff_pricing_type: str | None = None
    tariff_realtime: bool | None = None

    projected_grid_energy_need_kwh: float | None = None
    estimated_reference_grid_cost_cny: float | None = None


class OptimizationDecisionV2Schema(BaseModel):
    version: str
    action_required: bool
    device_id: int | None = None
    capability: str = "backup_reserve"
    current_value: float | None = None
    target_value: float | None = None
    strategy_mode: StrategyMode
    decision_confidence: str
    reason_code: str
    reason: str
    evidence: OptimizerV2EvidenceSchema
    policy_rule: str
