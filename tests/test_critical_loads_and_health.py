import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.modules.critical_load.models.critical_load import CriticalLoad
from app.modules.critical_load.schemas.critical_load import (
    CriticalLoadCreateSchema,
    CriticalLoadUpdateSchema,
)
from app.modules.critical_load.services.critical_load_service import CriticalLoadService
from app.modules.device_registry.schemas.device_registry import (
    DeviceCapabilitySchema,
    DeviceDiscoveryResponseSchema,
    DiscoveredDeviceSchema,
)
from app.modules.system_health.services.system_health_service import SystemHealthService


def test_critical_load_crud_and_enabled_total():
    engine = create_engine("sqlite:///:memory:")
    CriticalLoad.__table__.create(engine)
    with Session(engine) as db:
        first = CriticalLoadService.create(db, CriticalLoadCreateSchema(name="冰箱", category="appliance", rated_power_w=180))
        second = CriticalLoadService.create(db, CriticalLoadCreateSchema(name="路由器", category="network", rated_power_w=20))
        summary = CriticalLoadService.list(db)
        assert summary.total_power_w == 200
        CriticalLoadService.update(db, first.id, CriticalLoadUpdateSchema(enabled=False))
        assert CriticalLoadService.list(db).total_power_w == 20
        CriticalLoadService.delete(db, second.id)
        assert CriticalLoadService.list(db).count == 1


def test_health_summary_warns_for_unverified_controls_without_blocking(monkeypatch):
    async def fake_config():
        return SimpleNamespace(time_zone="Asia/Shanghai")

    async def fake_discovery():
        return DeviceDiscoveryResponseSchema(
            count=1,
            devices=[
                DiscoveredDeviceSchema(
                    device_id="solix-1",
                    vendor="anker_solix",
                    model="Solarbank 4",
                    device_type="storage",
                    topology_role="storage",
                    integration="anker_solix_official",
                    source_mode="simulator",
                    online=True,
                    observed_at=datetime.now(timezone.utc).isoformat(),
                    telemetry=[DeviceCapabilitySchema(name="soc", entity_id="sensor.soc", access="read", value=77)],
                    controls=[DeviceCapabilitySchema(name="mode", entity_id="select.mode", access="read_write", value="auto", verified=False)],
                )
            ],
        )

    monkeypatch.setattr("app.modules.system_health.services.system_health_service.home_assistant_service.get_config", fake_config)
    monkeypatch.setattr("app.modules.system_health.services.system_health_service.device_discovery_service.discover_devices", fake_discovery)
    result = asyncio.run(SystemHealthService().get_summary())
    assert result.status == "warning"
    assert result.devices[0].online is True
    assert result.devices[0].unverified_controls == 1
    assert not any(check.blocking for check in result.checks)
