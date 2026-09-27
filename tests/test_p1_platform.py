import asyncio
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.area_energy.services.area_energy_service import area_energy_service
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
from app.modules.safety.services.safety_service import safety_service
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


def p1_states():
    plug = "anker_solix_smart_plug_gen_2_kitchen"
    meter = "anker_solix_smart_meter_gen_2_main"
    return [
        state(f"sensor.{plug}_device_model", "Anker SOLIX Smart Plug Gen 2"),
        state(f"sensor.{plug}_device_sn", "PLUG-001"),
        state(f"sensor.{plug}_real_time_power", "186", "W"),
        state(f"sensor.{plug}_switch_status", "connected"),
        state(f"switch.{plug}_power_switch", "on"),
        state(f"sensor.{meter}_meter_model", "Anker SOLIX Smart Meter Gen 2"),
        state(f"sensor.{meter}_meter_sn", "METER-001"),
        state(f"sensor.{meter}_meter_type", "three_phase"),
        state(f"sensor.{meter}_primary_total_active_power", "2450", "W"),
        state(f"sensor.{meter}_primary_phase_1_active_power", "800", "W"),
        state(f"sensor.{meter}_primary_phase_1_current", "3.48", "A"),
        state(f"sensor.{meter}_primary_phase_1_voltage", "230", "V"),
        state(f"sensor.{meter}_primary_total_power_factor", "0.96"),
    ]


def test_dynamic_discovery_matches_multiple_profiles(monkeypatch):
    async def get_states():
        return p1_states()

    monkeypatch.setattr(home_assistant_service, "get_states", get_states)
    result = asyncio.run(device_discovery_service.discover_devices())

    assert result.count == 2
    assert {device.profile_id for device in result.devices} == {
        "smart_plug_gen_2",
        "smart_meter_gen_2",
    }
    plug = next(device for device in result.devices if device.device_type == "smart_plug")
    assert plug.online is True
    assert next(item for item in plug.controls if item.name == "power_switch").verified is False
    meter = next(device for device in result.devices if device.device_type == "smart_meter")
    assert meter.online is True
    assert any(item.name == "primary_total_active_power" for item in meter.telemetry)


def test_area_load_view_uses_registry_assignment_without_double_count(monkeypatch):
    async def get_states():
        return [
            state("sensor.kitchen_plug_real_time_power", "186", "W"),
            state("sensor.kitchen_meter_primary_total_active_power", "500", "W"),
            state("sensor.kitchen_meter_primary_phase_1_active_power", "500", "W"),
        ]

    async def get_registries():
        return {
            "areas": [{"area_id": "kitchen", "name": "厨房"}],
            "devices": [{"id": "plug", "area_id": "kitchen"}],
            "entities": [
                {"entity_id": "sensor.kitchen_plug_real_time_power", "device_id": "plug"},
                {"entity_id": "sensor.kitchen_meter_primary_total_active_power", "area_id": "kitchen"},
                {"entity_id": "sensor.kitchen_meter_primary_phase_1_active_power", "area_id": "kitchen"},
            ],
        }

    monkeypatch.setattr(home_assistant_service, "get_states", get_states)
    monkeypatch.setattr(home_assistant_service, "get_registries", get_registries)
    result = asyncio.run(area_energy_service.get_load_view())

    assert result.available is True
    assert result.areas[0].name == "厨房"
    assert result.areas[0].total_power_w == 686
    phase = next(item for item in result.areas[0].entities if "phase_1" in item.entity_id)
    assert phase.included_in_total is False


def test_meter_insight_returns_ct_and_phase_details(monkeypatch):
    async def get_states():
        return p1_states()

    monkeypatch.setattr(home_assistant_service, "get_states", get_states)
    result = asyncio.run(
        area_energy_service.get_meter_insight("anker_solix_METER-001")
    )

    assert result.available is True
    assert result.meter_type == "three_phase"
    assert result.channels[0].total_active_power_w == 2450
    assert result.channels[0].phases[0].voltage_v == 230


def test_unverified_smart_plug_is_blocked_by_safety():
    now = datetime.now(timezone.utc).isoformat()
    device = Device(
        id=8,
        source_device_id="anker_solix_PLUG-001",
        vendor="anker_solix",
        model="Smart Plug Gen 2",
        device_type="smart_plug",
        topology_role="load",
        integration="anker_solix_official",
        source_mode="home_assistant",
        observe_enabled=True,
        propose_enabled=True,
        control_enabled=True,
    )
    proposal = Proposal(
        id=9,
        device_id=8,
        strategy_mode=StrategyMode.AUTO,
        capability="power_switch",
        current_value=0,
        target_value=1,
        reason_code="USER_REQUESTED_LOAD_CONTROL",
        reason="test",
        status=ProposalStatus.APPROVED,
    )
    runtime = DiscoveredDeviceSchema(
        device_id=device.source_device_id,
        vendor="anker_solix",
        model=device.model,
        device_type="smart_plug",
        topology_role="load",
        integration="anker_solix_official",
        source_mode="home_assistant",
        online=True,
        observed_at=now,
        profile_id="smart_plug_gen_2",
        controls=[
            DeviceCapabilitySchema(
                name="power_switch",
                entity_id="switch.test_power_switch",
                access="read_write",
                value="off",
                available=True,
                verified=False,
                min=0,
                max=1,
                step=1,
                observed_at=now,
            )
        ],
    )
    result = safety_service.check(proposal=proposal, device=device, runtime=runtime)
    assert result.passed is False
    assert result.reason_code == "CAPABILITY_NOT_VERIFIED"


def test_smart_plug_request_creates_pending_proposal(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc).isoformat()
    runtime = DiscoveredDeviceSchema(
        device_id="anker_solix_PLUG-001",
        vendor="anker_solix",
        model="Smart Plug Gen 2",
        device_type="smart_plug",
        topology_role="load",
        integration="anker_solix_official",
        source_mode="home_assistant",
        online=True,
        observed_at=now,
        profile_id="smart_plug_gen_2",
        controls=[
            DeviceCapabilitySchema(
                name="power_switch",
                entity_id="switch.test_power_switch",
                access="read_write",
                value="off",
                available=True,
                verified=False,
                min=0,
                max=1,
                step=1,
                observed_at=now,
            )
        ],
    )

    async def discover():
        from app.modules.device_registry.schemas.device_registry import (
            DeviceDiscoveryResponseSchema,
        )

        return DeviceDiscoveryResponseSchema(count=1, devices=[runtime])

    monkeypatch.setattr(device_discovery_service, "discover_devices", discover)
    with Session(engine) as db:
        device = Device(
            source_device_id=runtime.device_id,
            vendor="anker_solix",
            model=runtime.model,
            device_type="smart_plug",
            topology_role="load",
            integration="anker_solix_official",
            source_mode="home_assistant",
            observe_enabled=True,
            propose_enabled=True,
            control_enabled=True,
        )
        db.add(device)
        db.commit()
        proposal = asyncio.run(
            proposal_service.create_smart_plug_proposal(db, device.id, True)
        )
        assert proposal.status == ProposalStatus.PENDING
        assert proposal.capability == "power_switch"
        assert proposal.target_value == 1


def test_verified_smart_plug_execution_uses_switch_service_and_readback(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    calls = []

    async def call_service(**kwargs):
        calls.append(kwargs)
        return []

    async def get_state(entity_id):
        return state(entity_id, "on")

    monkeypatch.setattr(home_assistant_service, "call_service", call_service)
    monkeypatch.setattr(home_assistant_service, "get_state", get_state)

    with Session(engine) as db:
        device = Device(
            source_device_id="anker_solix_PLUG-001",
            vendor="anker_solix",
            model="Smart Plug Gen 2",
            device_type="smart_plug",
            topology_role="load",
            integration="anker_solix_official",
            source_mode="home_assistant",
        )
        db.add(device)
        db.commit()
        proposal = Proposal(
            device_id=device.id,
            strategy_mode=StrategyMode.AUTO,
            capability="power_switch",
            current_value=0,
            target_value=1,
            reason_code="USER_REQUESTED_LOAD_CONTROL",
            reason="test",
            status=ProposalStatus.EXECUTING,
        )
        db.add(proposal)
        db.commit()
        runtime = DiscoveredDeviceSchema(
            device_id=device.source_device_id,
            vendor="anker_solix",
            model=device.model,
            device_type="smart_plug",
            topology_role="load",
            integration="anker_solix_official",
            source_mode="home_assistant",
            online=True,
            observed_at=datetime.now(timezone.utc).isoformat(),
            profile_id="smart_plug_gen_2",
            controls=[
                DeviceCapabilitySchema(
                    name="power_switch",
                    entity_id="switch.test_power_switch",
                    access="read_write",
                    value="off",
                    available=True,
                    verified=True,
                    min=0,
                    max=1,
                    step=1,
                    observed_at=datetime.now(timezone.utc).isoformat(),
                )
            ],
        )
        execution = asyncio.run(
            execution_service.execute(db=db, proposal=proposal, runtime=runtime)
        )
        execution_status = execution.status

    assert execution_status == ExecutionStatus.SUCCEEDED
    assert calls[0]["domain"] == "switch"
    assert calls[0]["service"] == "turn_on"
    assert calls[0]["service_data"] == {}
