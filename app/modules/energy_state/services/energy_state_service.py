from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.device_registry.repositories.device_repository import (
    device_repository,
)
from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.energy_state.schemas.energy_state import (
    EnergyPowerStateSchema,
    EnergySourceSchema,
    EnergyStateResponseSchema,
    EnergyStorageStateSchema,
)
class EnergyStateService:

    @staticmethod
    def _get_value(
        telemetry_map: dict,
        name: str,
    ):
        telemetry = telemetry_map.get(name)

        if telemetry is None:
            return None

        if not telemetry.available:
            return None

        return telemetry.value

    @staticmethod
    def _get_latest_updated(
        telemetry_map: dict,
    ) -> datetime | None:

        timestamps: list[datetime] = []

        for telemetry in telemetry_map.values():
            if not telemetry.last_updated:
                continue

            timestamp = datetime.fromisoformat(
                telemetry.last_updated.replace(
                    "Z",
                    "+00:00",
                )
            )

            timestamps.append(timestamp)

        if not timestamps:
            return None

        return max(timestamps)

    async def get_energy_state(
        self,
        db: Session,
    ) -> EnergyStateResponseSchema:

        # 1. 获取光衡已经绑定的设备
        bound_devices = device_repository.get_all(
            db=db,
        )

        # 2. 只选择允许 Observe 的储能设备
        storage_device = next(
            (
                device
                for device in bound_devices
                if device.observe_enabled
                and device.device_type == "storage"
            ),
            None,
        )

        # 当前没有可观察的储能设备
        if storage_device is None:
            return EnergyStateResponseSchema(
                available=False,
                online=False,
                source=None,
                power=EnergyPowerStateSchema(),
                storage=EnergyStorageStateSchema(),
                last_updated=None,
            )

        # 3. 获取 HA 当前发现的真实设备状态
        discovery_result = (
            await device_discovery_service.discover_devices()
        )

        discovered_device = next(
            (
                device
                for device in discovery_result.devices
                if device.device_id
                == storage_device.source_device_id
            ),
            None,
        )

        # 数据库有设备，但 HA 当前找不到
        if discovered_device is None:
            return EnergyStateResponseSchema(
                available=False,
                online=False,
                source=EnergySourceSchema(
                    device_id=storage_device.id,
                    source_device_id=(
                        storage_device.source_device_id
                    ),
                    display_name=storage_device.display_name,
                    source_mode=storage_device.source_mode,
                ),
                power=EnergyPowerStateSchema(),
                storage=EnergyStorageStateSchema(),
                last_updated=None,
            )

        # 4. 把 telemetry 数组转换成字典
        telemetry_map = {
            telemetry.name: telemetry
            for telemetry in discovered_device.telemetry
        }

        # Household totals are capability-driven. Storage telemetry remains
        # the fallback, while an online Smart Meter is the authoritative grid
        # truth source and its secondary CT is the aggregate PV/ESS circuit.
        online_storages = [
            item
            for item in discovery_result.devices
            if item.device_type == "storage" and item.online
        ]
        storage_maps = [
            {capability.name: capability for capability in item.telemetry}
            for item in online_storages
        ]
        meter = next(
            (
                item
                for item in discovery_result.devices
                if item.device_type == "smart_meter" and item.online
            ),
            None,
        )
        meter_map = (
            {capability.name: capability for capability in meter.telemetry}
            if meter is not None
            else {}
        )
        meter_grid = self._get_value(meter_map, "primary_total_active_power")
        meter_solar = self._get_value(meter_map, "secondary_total_active_power")
        aggregate_solar = sum(
            self._get_value(item, "solar_power") or 0 for item in storage_maps
        )
        aggregate_charging = sum(
            self._get_value(item, "battery_charging_power") or 0
            for item in storage_maps
        )
        aggregate_discharging = sum(
            self._get_value(item, "battery_discharging_power") or 0
            for item in storage_maps
        )

        # 5. 从设备能力模型映射成家庭能源模型
        power = EnergyPowerStateSchema(
            solar_w=meter_solar if meter_solar is not None else aggregate_solar,
            home_load_w=self._get_value(
                telemetry_map,
                "home_load",
            ),
            battery_charging_w=aggregate_charging,
            battery_discharging_w=aggregate_discharging,
            grid_import_w=(
                max(0, meter_grid)
                if meter_grid is not None
                else self._get_value(telemetry_map, "grid_import_power")
            ),
            grid_export_w=(
                max(0, -meter_grid)
                if meter_grid is not None
                else self._get_value(telemetry_map, "grid_export_power")
            ),
        )

        storage = EnergyStorageStateSchema(
            soc_percent=self._get_value(
                telemetry_map,
                "battery_soc",
            ),
            capacity_kwh=self._get_value(
                telemetry_map,
                "battery_capacity",
            ),
            status=self._get_value(
                telemetry_map,
                "device_status",
            ),
        )

        last_updated = self._get_latest_updated(
            telemetry_map
        )

        return EnergyStateResponseSchema(
            available=True,
            online=discovered_device.online,

            source=EnergySourceSchema(
                device_id=storage_device.id,
                source_device_id=(
                    storage_device.source_device_id
                ),
                display_name=storage_device.display_name,
                source_mode=storage_device.source_mode,
            ),

            power=power,
            storage=storage,

            last_updated=last_updated,
        )


energy_state_service = EnergyStateService()
