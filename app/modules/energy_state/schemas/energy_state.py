from datetime import datetime

from pydantic import BaseModel


class EnergySourceSchema(BaseModel):
    device_id: int
    source_device_id: str

    display_name: str | None = None
    source_mode: str


class EnergyPowerStateSchema(BaseModel):
    solar_w: float | None = None

    home_load_w: float | None = None

    battery_charging_w: float | None = None
    battery_discharging_w: float | None = None

    grid_import_w: float | None = None
    grid_export_w: float | None = None


class EnergyStorageStateSchema(BaseModel):
    soc_percent: float | None = None

    capacity_kwh: float | None = None

    status: str | None = None


class EnergyStateResponseSchema(BaseModel):
    available: bool
    online: bool

    source: EnergySourceSchema | None = None

    power: EnergyPowerStateSchema
    storage: EnergyStorageStateSchema

    last_updated: datetime | None = None