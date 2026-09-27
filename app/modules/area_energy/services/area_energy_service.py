from datetime import datetime, timezone

from app.modules.area_energy.schemas.area_energy import (
    AreaLoadEntitySchema,
    AreaLoadSchema,
    AreaLoadViewSchema,
    MeterChannelSchema,
    MeterPhaseSchema,
    SmartMeterInsightSchema,
)
from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.home_assistant.services.home_assistant_service import (
    home_assistant_service,
)


class AreaEnergyService:
    @staticmethod
    def _number(value: object) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _power_w(value: object, unit: object) -> float | None:
        number = AreaEnergyService._number(value)
        if number is None:
            return None
        normalized = str(unit or "").lower()
        if normalized == "kw":
            return number * 1000
        return number if normalized == "w" else None

    @staticmethod
    def _included_in_total(entity_id: str) -> bool:
        object_id = entity_id.split(".", 1)[-1]
        if any(
            key in object_id
            for key in (
                "reactive",
                "solar_power",
                "battery_charging_power",
                "battery_discharging_power",
                "battery_discharge_power",
                "grid_import_power",
                "grid_export_power",
                "ac_output",
            )
        ):
            return False
        if any(f"phase_{phase}_active_power" in object_id for phase in ("1", "2", "3")):
            return False
        return object_id.endswith("_power") or any(
            key in object_id for key in ("home_load", "total_active_power")
        )

    async def get_load_view(self) -> AreaLoadViewSchema:
        observed_at = datetime.now(timezone.utc)
        try:
            states = await home_assistant_service.get_states()
            registries = await home_assistant_service.get_registries()
        except Exception as exc:
            return AreaLoadViewSchema(
                available=False,
                observed_at=observed_at,
                total_power_w=0,
                diagnostic=f"HA_AREA_REGISTRY_UNAVAILABLE: {type(exc).__name__}",
            )

        state_map = {state.entity_id: state for state in states}
        area_names = {
            item.get("area_id"): item.get("name") or item.get("area_id")
            for item in registries["areas"]
            if item.get("area_id")
        }
        device_areas = {
            item.get("id"): item.get("area_id")
            for item in registries["devices"]
            if item.get("id")
        }
        grouped: dict[str, list[AreaLoadEntitySchema]] = {}
        unassigned: list[AreaLoadEntitySchema] = []

        for entity in registries["entities"]:
            entity_id = entity.get("entity_id")
            state = state_map.get(entity_id)
            if state is None or not entity_id or not entity_id.startswith("sensor."):
                continue
            unit = state.attributes.get("unit_of_measurement")
            power = self._power_w(state.state, unit)
            if power is None and str(unit or "").lower() not in {"w", "kw"}:
                continue
            available = state.state not in {"unknown", "unavailable", ""}
            area_id = entity.get("area_id") or device_areas.get(entity.get("device_id"))
            item = AreaLoadEntitySchema(
                entity_id=entity_id,
                name=state.attributes.get("friendly_name")
                or entity.get("name")
                or entity.get("original_name")
                or entity_id,
                device_id=entity.get("device_id"),
                power_w=round(power, 2) if available and power is not None else None,
                available=available,
                included_in_total=self._included_in_total(entity_id),
            )
            if area_id:
                grouped.setdefault(area_id, []).append(item)
            else:
                unassigned.append(item)

        areas = []
        for area_id, entities in grouped.items():
            total = sum(
                item.power_w or 0
                for item in entities
                if item.available and item.included_in_total
            )
            areas.append(
                AreaLoadSchema(
                    area_id=area_id,
                    name=area_names.get(area_id, area_id),
                    total_power_w=round(total, 2),
                    available_count=sum(item.available for item in entities),
                    entity_count=len(entities),
                    entities=sorted(
                        entities, key=lambda item: item.power_w or 0, reverse=True
                    ),
                )
            )
        areas.sort(key=lambda item: item.total_power_w, reverse=True)
        return AreaLoadViewSchema(
            available=True,
            observed_at=observed_at,
            total_power_w=round(sum(area.total_power_w for area in areas), 2),
            areas=areas,
            unassigned=unassigned,
            diagnostic=None
            if areas
            else "NO_AREA_POWER_ENTITIES: 请在 Home Assistant 为功率实体分配 Area",
        )

    async def get_meter_insight(self, device_id: str) -> SmartMeterInsightSchema:
        discovery = await device_discovery_service.discover_devices()
        device = next(
            (
                item
                for item in discovery.devices
                if item.device_id == device_id and item.device_type == "smart_meter"
            ),
            None,
        )
        if device is None:
            return SmartMeterInsightSchema(
                available=False,
                device_id=device_id,
                model="Anker SOLIX Smart Meter Gen 2",
                online=False,
                diagnostic="SMART_METER_NOT_DISCOVERED",
            )
        values = {
            item.name: item.value if item.available else None
            for item in device.telemetry
        }

        def number(name: str) -> float | None:
            return self._number(values.get(name))

        channels = []
        for channel in ("primary", "secondary"):
            phases = [
                MeterPhaseSchema(
                    phase=str(index),
                    active_power_w=number(f"{channel}_phase_{index}_active_power"),
                    current_a=number(f"{channel}_phase_{index}_current"),
                    voltage_v=number(f"{channel}_phase_{index}_voltage"),
                )
                for index in (1, 2, 3)
            ]
            if any(
                value is not None
                for phase in phases
                for value in (phase.active_power_w, phase.current_a, phase.voltage_v)
            ) or number(f"{channel}_total_active_power") is not None:
                channels.append(
                    MeterChannelSchema(
                        channel=channel,
                        total_active_power_w=number(f"{channel}_total_active_power"),
                        total_reactive_power_w=number(
                            f"{channel}_total_reactive_power"
                        ),
                        power_factor=number(f"{channel}_total_power_factor"),
                        forward_energy_kwh=number(
                            f"{channel}_total_forward_active_energy"
                        ),
                        reverse_energy_kwh=number(
                            f"{channel}_total_reverse_active_energy"
                        ),
                        phases=phases,
                    )
                )
        return SmartMeterInsightSchema(
            available=device.online and bool(channels),
            device_id=device.device_id,
            model=device.model,
            online=device.online,
            meter_type=str(values.get("meter_type"))
            if values.get("meter_type") is not None
            else None,
            observed_at=datetime.fromisoformat(
                device.observed_at.replace("Z", "+00:00")
            ),
            channels=channels,
            diagnostic=None if channels else "SMART_METER_DATA_UNAVAILABLE",
        )


area_energy_service = AreaEnergyService()
