from datetime import datetime, timezone

from app.modules.device_registry.schemas.device_registry import DiscoveredDeviceSchema
from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.household_graph.schemas.household_graph import (
    CoordinatedActionSchema,
    EnergyOpportunitySchema,
    HouseholdAssetNodeSchema,
    HouseholdEnergyEdgeSchema,
    HouseholdEnergyGraphSchema,
)


class HouseholdGraphService:
    @staticmethod
    def _telemetry(device: DiscoveredDeviceSchema, name: str) -> float | None:
        capability = next((item for item in device.telemetry if item.name == name), None)
        if capability is None or not capability.available:
            return None
        try:
            return float(capability.value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _state(device: DiscoveredDeviceSchema, name: str) -> str | None:
        capability = next((item for item in device.telemetry if item.name == name), None)
        return str(capability.value) if capability and capability.value is not None else None

    def compose(
        self, devices: list[DiscoveredDeviceSchema], observed_at: datetime
    ) -> HouseholdEnergyGraphSchema:
        storages = [item for item in devices if item.device_type == "storage"]
        meters = [item for item in devices if item.device_type == "smart_meter"]
        plugs = [item for item in devices if item.device_type == "smart_plug"]
        meter = next((item for item in meters if item.online), None)
        online_storage = [item for item in storages if item.online]

        grid = self._telemetry(meter, "primary_total_active_power") if meter else None
        solar = self._telemetry(meter, "secondary_total_active_power") if meter else None
        if solar is None:
            solar_values = [self._telemetry(item, "solar_power") for item in online_storage]
            solar = sum(value for value in solar_values if value is not None) or None
        home = next(
            (
                value
                for value in (self._telemetry(item, "home_load") for item in online_storage)
                if value is not None
            ),
            None,
        )
        charge = sum(self._telemetry(item, "battery_charging_power") or 0 for item in online_storage)
        discharge = sum(self._telemetry(item, "battery_discharging_power") or 0 for item in online_storage)
        plug_power = sum(self._telemetry(item, "real_time_power") or 0 for item in plugs if item.online)
        residual = max(0.0, home - plug_power) if home is not None else None
        # Smart Meter secondary CT is PV/ESS net active power. When it is the
        # source, storage charge/discharge is already reflected and must not be
        # counted a second time. The storage telemetry fallback is raw PV and
        # still requires the explicit battery terms.
        expected_grid = None
        if home is not None and solar is not None:
            expected_grid = (
                home - solar
                if meter is not None
                else home + charge - discharge - solar
            )
        balance_error = grid - expected_grid if grid is not None and expected_grid is not None else None

        nodes: list[HouseholdAssetNodeSchema] = []
        for item in devices:
            power = None
            soc = None
            state = None
            role = item.topology_role
            if item.device_type == "storage":
                charging = self._telemetry(item, "battery_charging_power") or 0
                discharging = self._telemetry(item, "battery_discharging_power") or 0
                power = discharging - charging
                soc = self._telemetry(item, "battery_soc")
                state = self._state(item, "device_status")
            elif item.device_type == "smart_meter":
                power = self._telemetry(item, "primary_total_active_power")
                role = "observer_verifier"
            elif item.device_type == "smart_plug":
                power = self._telemetry(item, "real_time_power")
                state = self._state(item, "switch_status")
                role = "load_actuator"
            nodes.append(
                HouseholdAssetNodeSchema(
                    device_id=item.device_id,
                    label=item.model,
                    asset_type=item.device_type,
                    role=role,
                    online=item.online,
                    source_mode=item.source_mode,
                    power_w=power,
                    soc_percent=soc,
                    state=state,
                )
            )

        edges: list[HouseholdEnergyEdgeSchema] = []
        truth_id = meter.device_id if meter else None
        if solar is not None and solar > 0:
            edges.append(HouseholdEnergyEdgeSchema(source="pv", target="home_bus", power_w=solar, direction="supply", truth_source=truth_id))
        if grid is not None and abs(grid) >= 1:
            edges.append(HouseholdEnergyEdgeSchema(source="grid" if grid > 0 else "home_bus", target="home_bus" if grid > 0 else "grid", power_w=abs(grid), direction="import" if grid > 0 else "export", truth_source=truth_id))
        if home is not None:
            edges.append(HouseholdEnergyEdgeSchema(source="home_bus", target="home", power_w=home, direction="consume", truth_source=truth_id))

        opportunities: list[EnergyOpportunitySchema] = []
        if grid is not None and grid < -200:
            export_w = abs(grid)
            actions: list[CoordinatedActionSchema] = []
            remaining_w = export_w
            plug = next((item for item in plugs if item.online and (self._telemetry(item, "real_time_power") or 0) < 50), None)
            if plug:
                plug_delta = min(800.0, remaining_w)
                actions.append(CoordinatedActionSchema(device_id=plug.device_id, capability="power_switch", target_value=1, expected_delta_w=plug_delta))
                remaining_w -= plug_delta
            # Split the remaining surplus across capability-compatible storage
            # assets. This deliberately uses runtime capabilities instead of
            # model names, allowing Max/XE variants to participate unchanged.
            for storage in online_storage:
                if remaining_w <= 50:
                    break
                if (self._telemetry(storage, "battery_soc") or 100) >= 90:
                    continue
                setpoint = next(
                    (
                        item
                        for item in storage.controls
                        if item.name == "battery_power_setpoint"
                        and item.available
                        and item.access == "read_write"
                    ),
                    None,
                )
                direction = next(
                    (
                        item
                        for item in storage.controls
                        if item.name == "battery_power_direction"
                        and item.available
                        and item.access == "read_write"
                    ),
                    None,
                )
                if setpoint is None or direction is None:
                    continue
                current_charge = self._telemetry(storage, "battery_charging_power") or 0
                maximum = float(setpoint.max) if setpoint.max is not None else 1200.0
                headroom = max(0.0, maximum - current_charge)
                allocation = min(1200.0, remaining_w, headroom)
                if allocation <= 50:
                    continue
                target = current_charge + allocation
                actions.extend([
                    CoordinatedActionSchema(device_id=storage.device_id, capability="battery_power_direction", target_value=0),
                    CoordinatedActionSchema(device_id=storage.device_id, capability="battery_power_setpoint", target_value=target, expected_delta_w=allocation),
                ])
                remaining_w -= allocation
            if actions:
                opportunities.append(EnergyOpportunitySchema(code="SOLAR_SURPLUS_SELF_CONSUMPTION", title="吸收光伏余电", reason=f"Smart Meter 检测到约 {export_w:.0f} W 电网反送，可协调储能与柔性负载提升自用率。", priority="high", expected_grid_delta_w=min(export_w, sum(item.expected_delta_w or 0 for item in actions)), actions=actions))

        diagnostics = []
        if meter is None:
            diagnostics.append("SMART_METER_GROUND_TRUTH_UNAVAILABLE")
        if balance_error is not None and abs(balance_error) > 100:
            diagnostics.append("HOUSEHOLD_ENERGY_BALANCE_MISMATCH")
        return HouseholdEnergyGraphSchema(
            available=bool(devices), observed_at=observed_at,
            meter_ground_truth=meter is not None,
            energy_balance_error_w=balance_error, grid_power_w=grid,
            solar_power_w=solar, home_load_w=home, residual_load_w=residual,
            nodes=nodes, edges=edges, opportunities=opportunities,
            diagnostics=diagnostics,
        )

    async def get_current(self) -> HouseholdEnergyGraphSchema:
        observed_at = datetime.now(timezone.utc)
        discovery = await device_discovery_service.discover_devices()
        return self.compose(discovery.devices, observed_at)


household_graph_service = HouseholdGraphService()
