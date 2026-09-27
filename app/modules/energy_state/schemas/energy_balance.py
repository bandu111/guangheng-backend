from pydantic import BaseModel


class EnergySourcePowerSchema(BaseModel):
    solar_w: float | None = None
    battery_discharging_w: float | None = None
    grid_import_w: float | None = None

    total_w: float | None = None


class EnergySinkPowerSchema(BaseModel):
    home_load_w: float | None = None
    battery_charging_w: float | None = None
    grid_export_w: float | None = None

    total_w: float | None = None


class EnergyBalanceResponseSchema(BaseModel):
    available: bool
    online: bool

    sources: EnergySourcePowerSchema
    sinks: EnergySinkPowerSchema

    balance_error_w: float | None = None
    balanced: bool | None = None