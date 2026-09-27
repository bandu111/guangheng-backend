from dataclasses import dataclass

from ..profiles import PLUG_PROFILE, STORAGE_PROFILES


@dataclass
class StorageRuntime:
    soc: float
    operating_mode: int = 3
    requested_battery_w: int = 0
    charging_limit: int = 90
    discharge_limit: int = 10
    backup_reserve: int = 30
    battery_w: int = 0
    charged_kwh: float = 123.4
    discharged_kwh: float = 98.7
    solar_kwh: float = 24.8


@dataclass
class HouseholdSnapshot:
    pv_w: int
    base_load_w: int
    controllable_load_w: int
    home_load_w: int
    battery_w: int
    grid_w: int
    secondary_ct_w: int
    balance_residual_w: int
    grid_import_kwh: float
    grid_export_kwh: float


class HouseholdWorld:
    """One deterministic household shared by every simulated device.

    Sign conventions:
    - storage battery_w > 0 discharges into the household bus;
    - storage battery_w < 0 charges from the household bus;
    - grid_w > 0 imports; grid_w < 0 exports.

    Energy balance:
        grid = home_load - pv - sum(storage_battery_w)
    """

    def __init__(self) -> None:
        self.base_load_w = 1100
        self.plug_on = True
        self.storages = {
            profile.key: StorageRuntime(soc=profile.initial_soc)
            for profile in STORAGE_PROFILES
        }
        self.grid_import_kwh = 36.2
        self.grid_export_kwh = 12.7
        self.plug_energy_kwh = 8.4
        self.snapshot = self._snapshot()

    @property
    def pv_w(self) -> int:
        return sum(profile.pv_share_w for profile in STORAGE_PROFILES)

    @property
    def plug_power_w(self) -> int:
        return PLUG_PROFILE.rated_power_w if self.plug_on else 0

    def _apply_storage_limits(self) -> None:
        profiles = {item.key: item for item in STORAGE_PROFILES}
        for key, state in self.storages.items():
            profile = profiles[key]
            requested = state.requested_battery_w if state.operating_mode == 3 else 0
            requested = max(-profile.max_charge_w, min(profile.max_discharge_w, requested))
            if requested < 0 and state.soc >= state.charging_limit:
                requested = 0
            minimum_soc = max(state.discharge_limit, state.backup_reserve)
            if requested > 0 and state.soc <= minimum_soc:
                requested = 0
            state.battery_w = int(requested)

    def _snapshot(self) -> HouseholdSnapshot:
        controllable = self.plug_power_w
        home = self.base_load_w + controllable
        battery = sum(item.battery_w for item in self.storages.values())
        grid = home - self.pv_w - battery
        secondary = self.pv_w + battery
        residual = grid - (home - self.pv_w - battery)
        return HouseholdSnapshot(
            pv_w=self.pv_w,
            base_load_w=self.base_load_w,
            controllable_load_w=controllable,
            home_load_w=home,
            battery_w=battery,
            grid_w=grid,
            secondary_ct_w=secondary,
            balance_residual_w=residual,
            grid_import_kwh=self.grid_import_kwh,
            grid_export_kwh=self.grid_export_kwh,
        )

    def tick(self, seconds: float) -> HouseholdSnapshot:
        self._apply_storage_limits()
        hours = max(0.0, seconds) / 3600
        profiles = {item.key: item for item in STORAGE_PROFILES}
        for key, state in self.storages.items():
            profile = profiles[key]
            if state.battery_w < 0:
                energy = -state.battery_w * hours / 1000
                state.charged_kwh += energy
                state.soc = min(100.0, state.soc + energy * 0.95 / profile.capacity_kwh * 100)
            elif state.battery_w > 0:
                energy = state.battery_w * hours / 1000
                state.discharged_kwh += energy
                state.soc = max(0.0, state.soc - energy / 0.95 / profile.capacity_kwh * 100)
            state.solar_kwh += profile.pv_share_w * hours / 1000

        snapshot = self._snapshot()
        if snapshot.grid_w > 0:
            self.grid_import_kwh += snapshot.grid_w * hours / 1000
        else:
            self.grid_export_kwh += -snapshot.grid_w * hours / 1000
        self.plug_energy_kwh += snapshot.controllable_load_w * hours / 1000
        self.snapshot = self._snapshot()
        return self.snapshot
