import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.modules.device_registry.schemas.device_registry import (
    DeviceCapabilitySchema,
    DeviceRuntimeStateSchema,
)
from app.modules.device_registry.services.device_registry_service import (
    DeviceRegistryService,
)
from app.modules.energy_state.schemas.energy_state import (
    EnergyPowerStateSchema,
    EnergySourceSchema,
    EnergyStateResponseSchema,
    EnergyStorageStateSchema,
)
from app.modules.energy_state.schemas.energy_today import (
    EnergyTodayResponseSchema,
    EnergyTodaySourceSchema,
    EnergyTodaySummarySchema,
)
from app.modules.station.services.station_service import StationService


NOW = datetime(2026, 9, 23, 2, 0, tzinfo=timezone.utc)


def test_station_summary_preserves_real_node_directions_and_coverage():
    state = EnergyStateResponseSchema(
        available=True,
        online=True,
        source=EnergySourceSchema(
            device_id=1,
            source_device_id="solix-1",
            display_name="家庭储能",
            source_mode="simulator",
        ),
        power=EnergyPowerStateSchema(
            solar_w=3700,
            home_load_w=2500,
            battery_charging_w=1200,
            battery_discharging_w=0,
            grid_import_w=0,
            grid_export_w=0,
        ),
        storage=EnergyStorageStateSchema(
            soc_percent=77,
            capacity_kwh=10,
            status="Charging",
        ),
        last_updated=NOW,
    )
    today = EnergyTodayResponseSchema(
        available=True,
        date=date(2026, 9, 23),
        time_zone="Asia/Shanghai",
        summary=EnergyTodaySummarySchema(
            generation_kwh=24.8,
            consumption_kwh=20.1,
            grid_import_kwh=0,
            savings_cny=5.46,
        ),
        source=EnergyTodaySourceSchema(coverage_percent=96),
        observed_at=NOW,
    )

    result = StationService.compose(state, today, NOW)
    nodes = {node.key: node for node in result.nodes}
    assert result.data_quality == "good"
    assert nodes["solar"].direction == "out"
    assert nodes["home"].direction == "in"
    assert nodes["battery"].direction == "in"
    assert nodes["grid"].direction == "idle"
    assert result.today.coverage_percent == 96


def test_battery_insight_uses_real_load_and_does_not_invent_critical_load(monkeypatch):
    service = DeviceRegistryService()
    runtime = DeviceRuntimeStateSchema(
        online=True,
        observed_at=NOW.isoformat(),
        telemetry=[
            DeviceCapabilitySchema(name="battery_soc", entity_id="sensor.soc", access="read", value=77),
            DeviceCapabilitySchema(name="battery_capacity", entity_id="sensor.capacity", access="read", value=10),
            DeviceCapabilitySchema(name="home_load", entity_id="sensor.load", access="read", value=2500),
            DeviceCapabilitySchema(name="device_status", entity_id="sensor.status", access="read", value="Charging"),
        ],
        controls=[
            DeviceCapabilitySchema(name="backup_reserve", entity_id="number.reserve", access="read_write", value=80, verified=True),
            DeviceCapabilitySchema(name="discharge_limit", entity_id="number.limit", access="read_write", value=10, verified=False),
        ],
    )

    async def fake_state(_db, _device_id):
        return SimpleNamespace(
            runtime=runtime,
            device=SimpleNamespace(source_mode="simulator"),
        )

    monkeypatch.setattr(service, "get_device_state", fake_state)
    monkeypatch.setattr(
        "app.modules.device_registry.services.device_registry_service.critical_load_service.list",
        lambda _db: SimpleNamespace(total_power_w=0, enabled_count=0),
    )
    result = asyncio.run(service.get_battery_insight(object(), 1))
    assert result.current_energy_kwh == 7.7
    assert result.protected_energy_kwh == 8.0
    assert result.usable_energy_kwh == 6.7
    assert result.whole_home_backup_hours == 2.47
    assert result.critical_load_backup_hours is None
    assert any("关键负载尚未配置" in item for item in result.assumptions)


def test_battery_insight_uses_user_configured_critical_load(monkeypatch):
    service = DeviceRegistryService()
    runtime = DeviceRuntimeStateSchema(
        online=True,
        observed_at=NOW.isoformat(),
        telemetry=[
            DeviceCapabilitySchema(name="battery_soc", entity_id="sensor.soc", access="read", value=77),
            DeviceCapabilitySchema(name="battery_capacity", entity_id="sensor.capacity", access="read", value=10),
            DeviceCapabilitySchema(name="home_load", entity_id="sensor.load", access="read", value=2500),
        ],
        controls=[
            DeviceCapabilitySchema(name="backup_reserve", entity_id="number.reserve", access="read_write", value=80),
            DeviceCapabilitySchema(name="discharge_limit", entity_id="number.limit", access="read_write", value=10),
        ],
    )

    async def fake_state(_db, _device_id):
        return SimpleNamespace(runtime=runtime, device=SimpleNamespace(source_mode="simulator"))

    monkeypatch.setattr(service, "get_device_state", fake_state)
    monkeypatch.setattr(
        "app.modules.device_registry.services.device_registry_service.critical_load_service.list",
        lambda _db: SimpleNamespace(total_power_w=500, enabled_count=2),
    )
    result = asyncio.run(service.get_battery_insight(object(), 1))
    assert result.critical_load_backup_hours == 12.33
    assert any("2 项" in item for item in result.assumptions)
