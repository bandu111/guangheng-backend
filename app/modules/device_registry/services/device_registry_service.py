from sqlalchemy.orm import Session

from app.modules.device_registry.models.device import Device
from app.modules.device_registry.repositories.device_repository import (
    device_repository,
)
from app.modules.device_registry.schemas.device_registry import (
    BatteryInsightSchema,
    DeviceBindRequestSchema,
    DeviceResponseSchema,
    DeviceRuntimeStateSchema,
    DeviceStateResponseSchema,
    DeviceUpdateRequestSchema,
)
from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.critical_load.services.critical_load_service import (
    critical_load_service,
)


class DeviceNotFoundError(Exception):
    pass


class DeviceRegistryService:

    @staticmethod
    def _capability_value(items, name: str):
        item = next((candidate for candidate in items if candidate.name == name), None)
        if item is None or not item.available:
            return None
        return item.value

    async def get_battery_insight(
        self,
        db: Session,
        device_id: int,
    ) -> BatteryInsightSchema:
        state = await self.get_device_state(db, device_id)
        runtime = state.runtime
        telemetry = runtime.telemetry
        controls = runtime.controls
        soc = self._capability_value(telemetry, "battery_soc")
        capacity = self._capability_value(telemetry, "battery_capacity")
        reserve = self._capability_value(controls, "backup_reserve")
        discharge_limit = self._capability_value(controls, "discharge_limit")
        home_load = self._capability_value(telemetry, "home_load")
        status = self._capability_value(telemetry, "device_status")
        numeric_ready = isinstance(soc, (int, float)) and isinstance(capacity, (int, float))
        current = capacity * soc / 100 if numeric_ready else None
        protected = capacity * reserve / 100 if numeric_ready and isinstance(reserve, (int, float)) else None
        minimum = capacity * discharge_limit / 100 if numeric_ready and isinstance(discharge_limit, (int, float)) else 0
        usable = max(0.0, current - minimum) if current is not None else None
        efficiency = 0.92
        whole_home = (
            usable * efficiency / (home_load / 1000)
            if usable is not None and isinstance(home_load, (int, float)) and home_load > 0
            else None
        )
        critical_loads = critical_load_service.list(db)
        critical_hours = (
            usable * efficiency / (critical_loads.total_power_w / 1000)
            if usable is not None and critical_loads.total_power_w > 0
            else None
        )
        assumptions = ["备电时长按当前家庭负载估算", "放电效率按 92% 计算"]
        if discharge_limit is None:
            assumptions.append("设备未提供放电下限，按 0% 计算可用能量")
        if critical_loads.total_power_w > 0:
            assumptions.append(
                f"关键负载由用户配置：{critical_loads.enabled_count} 项，共 {critical_loads.total_power_w:g} W"
            )
        else:
            assumptions.append("关键负载尚未配置，因此不生成关键负载时长")
        return BatteryInsightSchema(
            available=runtime.online and numeric_ready,
            device_id=device_id,
            source_mode=state.device.source_mode,
            soc_percent=float(soc) if isinstance(soc, (int, float)) else None,
            capacity_kwh=float(capacity) if isinstance(capacity, (int, float)) else None,
            current_energy_kwh=round(current, 3) if current is not None else None,
            reserve_percent=float(reserve) if isinstance(reserve, (int, float)) else None,
            protected_energy_kwh=round(protected, 3) if protected is not None else None,
            discharge_limit_percent=float(discharge_limit) if isinstance(discharge_limit, (int, float)) else None,
            usable_energy_kwh=round(usable, 3) if usable is not None else None,
            whole_home_load_w=float(home_load) if isinstance(home_load, (int, float)) else None,
            whole_home_backup_hours=round(whole_home, 2) if whole_home is not None else None,
            critical_load_backup_hours=round(critical_hours, 2) if critical_hours is not None else None,
            status=str(status) if status is not None else None,
            observed_at=runtime.observed_at,
            assumptions=assumptions,
            diagnostic=None if runtime.online and numeric_ready else "BATTERY_DATA_UNAVAILABLE",
        )

    async def bind_device(
        self,
        db: Session,
        source_device_id: str,
        request: DeviceBindRequestSchema,
    ) -> Device:

        # 1. 先检查数据库里是否已经绑定
        existing_device = device_repository.get_by_source_device_id(
            db=db,
            source_device_id=source_device_id,
        )

        if existing_device is not None:
            return existing_device

        # 2. 从 Home Assistant 实时发现设备
        discovery_result = (
            await device_discovery_service.discover_devices()
        )

        # 3. 根据 device_id 找到用户要绑定的那台设备
        discovered_device = next(
            (
                device
                for device in discovery_result.devices
                if device.device_id == source_device_id
            ),
            None,
        )

        if discovered_device is None:
            raise DeviceNotFoundError(
                f"Device not found: {source_device_id}"
            )

        # 4. 把“设备事实 + 用户配置”组合成 ORM
        device = Device(
            source_device_id=discovered_device.device_id,
            vendor=discovered_device.vendor,
            model=discovered_device.model,
            serial_number=discovered_device.serial_number,
            device_type=discovered_device.device_type,
            topology_role=discovered_device.topology_role,
            integration=discovered_device.integration,
            source_mode=discovered_device.source_mode,

            display_name=(
                request.display_name
                or discovered_device.model
            ),

            observe_enabled=request.observe_enabled,
            propose_enabled=request.propose_enabled,
            control_enabled=request.control_enabled,
            scene_enabled=request.scene_enabled,
        )

        # 5. Repository 写入数据库
        return device_repository.create(
            db=db,
            device=device,
        )

    def get_bound_devices(self,db:Session)->list[Device]:
        return device_repository.get_all(db=db)

    def update_device(
        self,
        db: Session,
        device_id: int,
        request: DeviceUpdateRequestSchema,
    ) -> Device:
        device = device_repository.get_by_id(
            db=db,
            device_id=device_id,
        )

        if device is None:
            raise DeviceNotFoundError(
                f"Bound device not found: {device_id}"
            )

        for field, value in request.model_dump(
            exclude_unset=True,
        ).items():
            setattr(device, field, value)

        return device_repository.update(
            db=db,
            device=device,
        )

    async def get_device_state(
            self,
            db: Session,
            device_id: int,
    ) -> DeviceStateResponseSchema:

        # 1. 查询光衡数据库中的绑定设备
        device = device_repository.get_by_id(
            db=db,
            device_id=device_id,
        )

        if device is None:
            raise DeviceNotFoundError(
                f"Bound device not found: {device_id}"
            )

        # 2. 查询 Home Assistant 当前发现的设备
        discovery_result = (
            await device_discovery_service.discover_devices()
        )

        # 3. 使用 source_device_id 做关联
        discovered_device = next(
            (
                discovered
                for discovered in discovery_result.devices
                if discovered.device_id
                   == device.source_device_id
            ),
            None,
        )

        # 4. 数据库有绑定记录，
        #    但 HA 当前找不到设备
        if discovered_device is None:
            return DeviceStateResponseSchema(
                device=DeviceResponseSchema.model_validate(
                    device
                ),
                runtime=DeviceRuntimeStateSchema(
                    online=False,
                    observed_at=None,
                    telemetry=[],
                    controls=[],
                ),
            )

        # 5. 合并持久化数据和实时数据
        return DeviceStateResponseSchema(
            device=DeviceResponseSchema.model_validate(
                device
            ),
            runtime=DeviceRuntimeStateSchema(
                online=discovered_device.online,
                observed_at=discovered_device.observed_at,
                telemetry=discovered_device.telemetry,
                controls=discovered_device.controls,
            ),
        )


device_registry_service = DeviceRegistryService()
