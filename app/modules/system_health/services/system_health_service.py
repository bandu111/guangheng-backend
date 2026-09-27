from datetime import datetime, timezone

from app.modules.device_registry.services.device_discovery_service import device_discovery_service
from app.modules.home_assistant.services.home_assistant_service import home_assistant_service
from app.modules.system_health.schemas.system_health import (
    DeviceHealthSchema,
    HealthCheckSchema,
    SystemHealthSchema,
)


class SystemHealthService:
    async def get_summary(self) -> SystemHealthSchema:
        observed_at = datetime.now(timezone.utc)
        checks: list[HealthCheckSchema] = []
        recovery: list[str] = []
        devices: list[DeviceHealthSchema] = []
        try:
            config = await home_assistant_service.get_config()
            checks.append(HealthCheckSchema(key="home_assistant", label="Home Assistant", status="healthy", detail=f"已连接 · {config.time_zone}"))
        except Exception:
            checks.append(HealthCheckSchema(key="home_assistant", label="Home Assistant", status="critical", detail="当前请求失败", blocking=True))
            recovery.extend(["检查 Home Assistant 地址和网络", "确认服务器端 HA Token 仍然有效"])
            return SystemHealthSchema(status="critical", observed_at=observed_at, checks=checks, recovery_actions=recovery)

        try:
            discovery = await device_discovery_service.discover_devices()
        except Exception:
            checks.append(HealthCheckSchema(key="integration", label="SOLIX Integration", status="critical", detail="设备发现请求失败", blocking=True))
            recovery.append("在 Home Assistant 中检查 Anker SOLIX Official Integration")
            return SystemHealthSchema(status="critical", observed_at=observed_at, checks=checks, recovery_actions=recovery)

        if not discovery.devices:
            checks.append(HealthCheckSchema(key="integration", label="SOLIX Integration", status="critical", detail="未发现支持的能源设备", blocking=True))
            recovery.append("确认目标设备 Entity 已由 Integration 创建")
        else:
            checks.append(HealthCheckSchema(key="integration", label="SOLIX Integration", status="healthy", detail=f"发现 {discovery.count} 台设备"))

        for device in discovery.devices:
            capabilities = [*device.telemetry, *device.controls]
            unavailable = sum(not capability.available for capability in capabilities)
            verified = sum(capability.verified is True for capability in device.controls)
            unverified = sum(capability.verified is not True for capability in device.controls)
            try:
                device_observed_at = datetime.fromisoformat(device.observed_at.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                device_observed_at = None
            devices.append(DeviceHealthSchema(
                device_id=device.device_id,
                model=device.model,
                online=device.online,
                unavailable_capabilities=unavailable,
                verified_controls=verified,
                unverified_controls=unverified,
                observed_at=device_observed_at,
            ))
            if not device.online:
                recovery.append(f"检查 {device.model} 的局域网连接和供电")
            if unavailable:
                recovery.append(f"在 HA 设备页检查 {device.model} 的 unavailable Entity")

        offline = sum(not device.online for device in devices)
        unavailable_total = sum(device.unavailable_capabilities for device in devices)
        device_status = "critical" if offline else "warning" if unavailable_total else "healthy"
        checks.append(HealthCheckSchema(
            key="device_runtime",
            label="设备运行状态",
            status=device_status,
            detail=f"{len(devices) - offline}/{len(devices)} 在线 · {unavailable_total} 项能力不可用",
            blocking=offline > 0,
        ))
        unverified_total = sum(device.unverified_controls for device in devices)
        checks.append(HealthCheckSchema(
            key="control_verification",
            label="控制能力",
            status="warning" if unverified_total else "healthy",
            detail=f"{sum(device.verified_controls for device in devices)} 项已验证 · {unverified_total} 项保持只读",
            blocking=False,
        ))
        overall = "critical" if any(check.status == "critical" for check in checks) else "warning" if any(check.status == "warning" for check in checks) else "healthy"
        return SystemHealthSchema(status=overall, observed_at=observed_at, checks=checks, devices=devices, recovery_actions=list(dict.fromkeys(recovery)))


system_health_service = SystemHealthService()

