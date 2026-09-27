from datetime import datetime, timedelta, timezone

import pytest

from app.modules.device_registry.models.device import Device
from app.modules.device_registry.schemas.device_registry import (
    DeviceCapabilitySchema,
    DiscoveredDeviceSchema,
)
from app.modules.proposal.models.proposal import Proposal, ProposalStatus
from app.modules.safety.services.safety_service import safety_service
from app.modules.strategy.models.strategy import StrategyMode


def make_device(*, control_enabled: bool = True) -> Device:
    return Device(
        id=1,
        source_device_id="anker_solix_test",
        vendor="anker_solix",
        model="test",
        device_type="storage",
        topology_role="storage",
        integration="anker_solix_official",
        source_mode="simulator",
        observe_enabled=True,
        propose_enabled=True,
        control_enabled=control_enabled,
        scene_enabled=True,
    )


def make_proposal() -> Proposal:
    return Proposal(
        id=1,
        device_id=1,
        strategy_mode=StrategyMode.BACKUP,
        capability="backup_reserve",
        current_value=25,
        target_value=80,
        reason_code="TARGET_DIFFERS",
        reason="test",
        status=ProposalStatus.APPROVED,
    )


def make_runtime(
    *,
    online: bool = True,
    available: bool = True,
    verified: bool = True,
    observed_at: str | None = None,
    last_reported: str | None = None,
) -> DiscoveredDeviceSchema:
    now = datetime.now(timezone.utc)
    observation_time = observed_at or now.isoformat()
    return DiscoveredDeviceSchema(
        device_id="anker_solix_test",
        vendor="anker_solix",
        model="test",
        device_type="storage",
        topology_role="storage",
        integration="anker_solix_official",
        source_mode="simulator",
        online=online,
        observed_at=observation_time,
        controls=[
            DeviceCapabilitySchema(
                name="backup_reserve",
                entity_id="number.anker_solix_solarbank_4_e5000_pro_001_backup_reserve",
                access="read_write",
                value=25,
                available=available,
                verified=verified,
                min=0,
                max=100,
                step=1,
                last_changed=(now - timedelta(hours=8)).isoformat(),
                last_reported=last_reported or (now - timedelta(hours=6)).isoformat(),
                last_updated=(now - timedelta(hours=8)).isoformat(),
                observed_at=observation_time,
            )
        ],
    )


def test_old_entity_report_does_not_block_fresh_runtime_observation():
    result = safety_service.check(
        proposal=make_proposal(),
        device=make_device(),
        runtime=make_runtime(),
    )

    assert result.passed is True
    assert result.checks["runtime_observation_fresh"] is True
    assert result.diagnostics["entity_report_age_seconds"] > 30
    assert "ENTITY_REPORT_TIMESTAMP_OLD" in result.warnings


def test_home_assistant_request_failure_is_blocked():
    result = safety_service.runtime_unavailable_result(
        device_found=True,
        ha_request_succeeded=False,
        runtime_found=False,
        detail="connection failed",
    )

    assert result.passed is False
    assert result.reason_code == "HOME_ASSISTANT_REQUEST_FAILED"
    assert result.checks["ha_request_succeeded"] is False


@pytest.mark.parametrize(
    ("device", "runtime", "reason_code"),
    [
        (make_device(), make_runtime(online=False), "DEVICE_OFFLINE"),
        (make_device(), make_runtime(available=False), "CAPABILITY_UNAVAILABLE"),
        (make_device(), make_runtime(verified=False), "CAPABILITY_NOT_VERIFIED"),
        (make_device(control_enabled=False), make_runtime(), "DEVICE_CONTROL_DISABLED"),
    ],
)
def test_required_safety_failures_are_blocked(device, runtime, reason_code):
    result = safety_service.check(
        proposal=make_proposal(),
        device=device,
        runtime=runtime,
    )

    assert result.passed is False
    assert result.reason_code == reason_code
