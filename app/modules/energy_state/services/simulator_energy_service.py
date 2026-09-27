import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, ValidationError


BASE_DIR = Path(__file__).resolve().parents[4]
POLICY_PATH = BASE_DIR / "config" / "simulator_energy_policy.yaml"


class _SolarPolicy(BaseModel):
    sunrise_hour: float = Field(ge=0, lt=24)
    sunset_hour: float = Field(gt=0, le=24)
    peak_power_w: float = Field(gt=0)


class _LoadPolicy(BaseModel):
    base_power_w: float = Field(gt=0)
    overnight_extra_w: float = Field(ge=0)
    morning_peak_start_hour: float = Field(ge=0, lt=24)
    morning_peak_end_hour: float = Field(gt=0, le=24)
    morning_peak_extra_w: float = Field(ge=0)
    daytime_extra_w: float = Field(ge=0)
    evening_peak_start_hour: float = Field(ge=0, lt=24)
    evening_peak_end_hour: float = Field(gt=0, le=24)
    evening_peak_extra_w: float = Field(ge=0)


class _BatteryPolicy(BaseModel):
    default_reserve_percent: float = Field(ge=0, le=100)
    reserve_margin_percent: float = Field(ge=0, le=100)
    max_charge_power_w: float = Field(ge=0)
    max_discharge_power_w: float = Field(ge=0)


class SimulatorEnergyPolicy(BaseModel):
    version: str = "v1"
    enabled: bool = True
    time_zone: str = "Asia/Shanghai"
    history_backfill_days: int = Field(default=7, ge=0, le=31)
    history_interval_minutes: int = Field(default=15, ge=5, le=60)
    solar: _SolarPolicy
    load: _LoadPolicy
    battery: _BatteryPolicy


@dataclass(frozen=True)
class SimulatorPowerState:
    solar_w: float
    home_load_w: float
    battery_charging_w: float
    battery_discharging_w: float
    grid_import_w: float
    grid_export_w: float
    battery_status: str


def load_simulator_energy_policy() -> SimulatorEnergyPolicy:
    try:
        with POLICY_PATH.open("r", encoding="utf-8") as file:
            return SimulatorEnergyPolicy.model_validate(yaml.safe_load(file) or {})
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise RuntimeError("Simulator energy policy is invalid.") from exc


class SimulatorEnergyService:
    def __init__(self, policy: SimulatorEnergyPolicy) -> None:
        self.policy = policy
        self.zone = ZoneInfo(policy.time_zone)

    def calculate(
        self,
        observed_at: datetime,
        *,
        soc_percent: float | None,
        reserve_percent: float | None,
    ) -> SimulatorPowerState:
        local = observed_at.astimezone(self.zone)
        hour = local.hour + local.minute / 60 + local.second / 3600
        solar_w = self._solar_power(hour)
        home_load_w = self._home_load(hour)
        net_surplus_w = solar_w - home_load_w
        charge_w = 0.0
        discharge_w = 0.0
        grid_import_w = 0.0
        grid_export_w = 0.0

        if net_surplus_w >= 0:
            charge_w = min(net_surplus_w, self.policy.battery.max_charge_power_w)
            grid_export_w = max(net_surplus_w - charge_w, 0)
        else:
            deficit_w = -net_surplus_w
            reserve = (
                reserve_percent
                if reserve_percent is not None
                else self.policy.battery.default_reserve_percent
            )
            can_discharge = (
                soc_percent is not None
                and soc_percent
                > reserve + self.policy.battery.reserve_margin_percent
            )
            if can_discharge:
                discharge_w = min(
                    deficit_w, self.policy.battery.max_discharge_power_w
                )
            grid_import_w = max(deficit_w - discharge_w, 0)

        status = "charging" if charge_w > 0 else "discharging" if discharge_w > 0 else "idle"
        return SimulatorPowerState(
            solar_w=round(solar_w, 1),
            home_load_w=round(home_load_w, 1),
            battery_charging_w=round(charge_w, 1),
            battery_discharging_w=round(discharge_w, 1),
            grid_import_w=round(grid_import_w, 1),
            grid_export_w=round(grid_export_w, 1),
            battery_status=status,
        )

    def _solar_power(self, hour: float) -> float:
        solar = self.policy.solar
        if hour <= solar.sunrise_hour or hour >= solar.sunset_hour:
            return 0
        phase = (hour - solar.sunrise_hour) / (
            solar.sunset_hour - solar.sunrise_hour
        )
        return max(0.0, math.sin(math.pi * phase) * solar.peak_power_w)

    def _home_load(self, hour: float) -> float:
        load = self.policy.load
        if load.morning_peak_start_hour <= hour < load.morning_peak_end_hour:
            extra = load.morning_peak_extra_w
        elif load.evening_peak_start_hour <= hour < load.evening_peak_end_hour:
            extra = load.evening_peak_extra_w
        elif 9 <= hour < load.evening_peak_start_hour:
            extra = load.daytime_extra_w
        else:
            extra = load.overnight_extra_w
        return load.base_power_w + extra


simulator_energy_policy = load_simulator_energy_policy()
simulator_energy_service = SimulatorEnergyService(simulator_energy_policy)
