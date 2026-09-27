from datetime import datetime

from pydantic import BaseModel, Field


class HouseholdAssetNodeSchema(BaseModel):
    device_id: str
    label: str
    asset_type: str
    role: str
    online: bool
    source_mode: str
    power_w: float | None = None
    soc_percent: float | None = None
    state: str | None = None


class HouseholdEnergyEdgeSchema(BaseModel):
    source: str
    target: str
    power_w: float
    direction: str
    truth_source: str | None = None


class CoordinatedActionSchema(BaseModel):
    device_id: str
    capability: str
    target_value: float
    expected_delta_w: float | None = None


class EnergyOpportunitySchema(BaseModel):
    code: str
    title: str
    reason: str
    priority: str
    requires_approval: bool = True
    expected_grid_delta_w: float | None = None
    actions: list[CoordinatedActionSchema] = Field(default_factory=list)


class HouseholdEnergyGraphSchema(BaseModel):
    available: bool
    observed_at: datetime
    meter_ground_truth: bool
    energy_balance_error_w: float | None = None
    grid_power_w: float | None = None
    solar_power_w: float | None = None
    home_load_w: float | None = None
    residual_load_w: float | None = None
    nodes: list[HouseholdAssetNodeSchema] = Field(default_factory=list)
    edges: list[HouseholdEnergyEdgeSchema] = Field(default_factory=list)
    opportunities: list[EnergyOpportunitySchema] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)

