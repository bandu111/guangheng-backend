import asyncio
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.device_registry.models.device import Device
from app.modules.device_registry.schemas.device_registry import (
    DeviceCapabilitySchema,
    DiscoveredDeviceSchema,
)
from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.execution.models.execution import ExecutionStatus
from app.modules.execution.services.execution_service import execution_service
from app.modules.home_assistant.schemas.home_assistant import HomeAssistantStateSchema
from app.modules.home_assistant.services.home_assistant_service import home_assistant_service
from app.modules.proposal.models.proposal import Proposal, ProposalStatus
from app.modules.proposal.services.proposal_service import proposal_service
from app.modules.solar_array.services.solar_array_service import solar_array_service
from app.modules.strategy.models.strategy import StrategyMode


def state(entity_id: str, value: str, unit: str | None = None):
    return HomeAssistantStateSchema(
        entity_id=entity_id,
        state=value,
        attributes={"unit_of_measurement": unit} if unit else {},
        last_changed="2026-09-23T00:00:00+00:00",
        last_reported="2026-09-23T00:00:00+00:00",
        last_updated="2026-09-23T00:00:00+00:00",
    )


def storage_states(*, with_channels: bool = False, serial: str = "123DPM44567890123"):
    prefix = "anker_solix_solarbank_4_main"
    result = [
        state(f"sensor.{prefix}_device_model", "Anker SOLIX Solarbank 4 E5000 Pro"),
        state(f"sensor.{prefix}_device_sn", serial),
        state(f"sensor.{prefix}_device_sw_version", "1.2.3"),
        state(f"sensor.{prefix}_battery_soc", "77", "%"),
        state(f"sensor.{prefix}_pv_power", "3700", "W"),
        state(f"number.{prefix}_backup_reserve_soc", "30", "%"),
        state(f"number.{prefix}_charging_limit_soc", "90", "%"),
        state(f"number.{prefix}_power_control", "0", "W"),
        state(f"select.{prefix}_operating_mode", "self_consumption"),
    ]
    if with_channels:
        result.extend(
            [
                state(f"sensor.{prefix}_mppt_1_power", "1850", "W"),
                state(f"sensor.{prefix}_mppt_1_voltage", "410", "V"),
                state(f"sensor.{prefix}_mppt_1_current", "4.51", "A"),
                state(f"sensor.{prefix}_panel_1_power", "460", "W"),
            ]
        )
    return result


def test_official_storage_aliases_and_model_profile(monkeypatch):
    async def get_states():
        return storage_states()

    monkeypatch.setattr(home_assistant_service, "get_states", get_states)
    result = asyncio.run(device_discovery_service.discover_devices())
    device = result.devices[0]
    assert device.profile_id == "solarbank_4_e5000_pro"
    assert device.entity_prefix == "anker_solix_solarbank_4_main"
    assert device.firmware_version == "1.2.3"
    assert next(item for item in device.telemetry if item.name == "solar_power").value == 3700
    reserve = next(item for item in device.controls if item.name == "backup_reserve")
    charging_limit = next(item for item in device.controls if item.name == "charging_limit")
    power_setpoint = next(
        item for item in device.controls if item.name == "battery_power_setpoint"
    )
    assert reserve.value == 30
    assert reserve.available is True
    assert reserve.verified is True
    assert reserve.verification_status == "verified"
    assert reserve.verification_method == "home_assistant_tcp_simulator_readback"
    assert "TCP 模拟器" in reserve.verification_note
    assert charging_limit.verified is True
    assert charging_limit.verification_status == "verified"
    assert "TCP 模拟器" in charging_limit.verification_note
    assert power_setpoint.verified is True
    assert power_setpoint.readback_reliable is True


def test_simulator_verification_is_not_advertised_as_global_model_verification():
    catalog = device_discovery_service.get_catalog()
    profiles = {item.profile_id: item for item in catalog.profiles}
    assert profiles["solarbank_4_e5000_pro"].verified_controls == []
    assert profiles["solarbank_max_ac_xe_ac"].verified_controls == []
    assert profiles["solarbank_max_xe"].verified_controls == []


def test_real_device_with_same_model_stays_unverified(monkeypatch):
    async def get_states():
        return storage_states(serial="AL3DPM40G22200245")

    monkeypatch.setattr(home_assistant_service, "get_states", get_states)
    result = asyncio.run(device_discovery_service.discover_devices())
    device = result.devices[0]
    reserve = next(item for item in device.controls if item.name == "backup_reserve")
    assert device.source_mode == "home_assistant"
    assert reserve.verified is False


def test_history_entity_ids_follow_current_discovered_storage(monkeypatch):
    async def get_states():
        return storage_states()

    monkeypatch.setattr(home_assistant_service, "get_states", get_states)
    result = asyncio.run(
        device_discovery_service.resolve_storage_telemetry_entity_ids(
            {
                "solar": "solar_power",
                "grid_import": "grid_import_power",
            }
        )
    )
    assert result["solar"].endswith("_pv_power")
    # The fixture intentionally has no grid entity: missing data must remain
    # missing instead of silently using another model's fixed entity ID.
    assert "grid_import" not in result


def test_solar_array_truthfully_reports_aggregate_only(monkeypatch):
    async def get_states():
        return storage_states()

    monkeypatch.setattr(home_assistant_service, "get_states", get_states)
    result = asyncio.run(
        solar_array_service.get_insight("anker_solix_123DPM44567890123")
    )
    assert result.available is True
    assert result.aggregate_power_w == 3700
    assert result.channel_data_available is False
    assert result.component_data_available is False
    assert result.diagnostic == "MPPT_CHANNELS_NOT_EXPOSED_BY_INTEGRATION"


def test_solar_array_discovers_future_mppt_and_component_entities(monkeypatch):
    async def get_states():
        return storage_states(with_channels=True)

    monkeypatch.setattr(home_assistant_service, "get_states", get_states)
    result = asyncio.run(
        solar_array_service.get_insight("anker_solix_123DPM44567890123")
    )
    assert result.channel_data_available is True
    assert result.mppt_channels[0].power_w == 1850
    assert result.mppt_channels[0].voltage_v == 410
    assert result.component_data_available is True
    assert result.components[0].power_w == 460


def test_storage_control_request_creates_pending_proposal(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    async def get_states():
        return storage_states()

    monkeypatch.setattr(home_assistant_service, "get_states", get_states)
    with Session(engine) as db:
        device = Device(
            source_device_id="anker_solix_123DPM44567890123",
            vendor="anker_solix",
            model="Anker SOLIX Solarbank 4 E5000 Pro",
            device_type="storage",
            topology_role="storage",
            integration="anker_solix_official",
            source_mode="simulator",
            observe_enabled=True,
            propose_enabled=True,
            control_enabled=True,
        )
        db.add(device)
        db.commit()
        proposal = asyncio.run(
            proposal_service.create_device_control_proposal(
                db, device.id, "backup_reserve", 80
            )
        )
        assert proposal.status == ProposalStatus.PENDING
        assert proposal.current_value == 30
        assert proposal.target_value == 80


def test_select_execution_maps_profile_value_and_verifies_readback(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    calls = []

    async def call_service(**kwargs):
        calls.append(kwargs)
        return []

    async def get_state(entity_id):
        return state(entity_id, "third_party_control")

    monkeypatch.setattr(home_assistant_service, "call_service", call_service)
    monkeypatch.setattr(home_assistant_service, "get_state", get_state)
    with Session(engine) as db:
        device = Device(
            source_device_id="anker_solix_SB4-001",
            vendor="anker_solix",
            model="Solarbank 4",
            device_type="storage",
            topology_role="storage",
            integration="anker_solix_official",
            source_mode="home_assistant",
        )
        db.add(device)
        db.commit()
        proposal = Proposal(
            device_id=device.id,
            strategy_mode=StrategyMode.AUTO,
            capability="operating_mode",
            current_value=0,
            target_value=3,
            reason_code="TEST",
            reason="test",
            status=ProposalStatus.EXECUTING,
        )
        db.add(proposal)
        db.commit()
        runtime = DiscoveredDeviceSchema(
            device_id=device.source_device_id,
            vendor="anker_solix",
            model=device.model,
            device_type="storage",
            topology_role="storage",
            integration="anker_solix_official",
            source_mode="home_assistant",
            online=True,
            observed_at=datetime.now(timezone.utc).isoformat(),
            profile_id="solarbank_4_e5000_pro",
            controls=[
                DeviceCapabilitySchema(
                    name="operating_mode",
                    entity_id="select.test_operating_mode",
                    access="read_write",
                    value="self_consumption",
                    available=True,
                    verified=True,
                    min=0,
                    max=7,
                    step=1,
                    observed_at=datetime.now(timezone.utc).isoformat(),
                )
            ],
        )
        execution = asyncio.run(
            execution_service.execute(db=db, proposal=proposal, runtime=runtime)
        )
        assert execution.status == ExecutionStatus.SUCCEEDED
    assert calls[0]["domain"] == "select"
    assert calls[0]["service"] == "select_option"
    assert calls[0]["service_data"] == {"option": "third_party_control"}
