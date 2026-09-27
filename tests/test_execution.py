import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.device_registry.models.device import Device
from app.modules.device_registry.schemas.device_registry import (
    DeviceCapabilitySchema,
    DiscoveredDeviceSchema,
)
from app.modules.execution.models.execution import ExecutionStatus
from app.modules.execution.services.execution_service import execution_service
from app.modules.home_assistant.schemas.home_assistant import HomeAssistantStateSchema
from app.modules.home_assistant.services.home_assistant_service import home_assistant_service
from app.modules.proposal.models.proposal import Proposal, ProposalStatus
from app.modules.strategy.models.strategy import StrategyMode


def test_execution_calls_ha_and_confirms_readback(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    calls = []

    async def call_service(**kwargs):
        calls.append(kwargs)
        return []

    async def get_state(entity_id):
        return HomeAssistantStateSchema(
            entity_id=entity_id,
            state="80",
            attributes={},
            last_changed="2026-09-18T00:00:00+00:00",
            last_reported="2026-09-18T00:00:00+00:00",
            last_updated="2026-09-18T00:00:00+00:00",
        )

    monkeypatch.setattr(home_assistant_service, "call_service", call_service)
    monkeypatch.setattr(home_assistant_service, "get_state", get_state)

    with Session(engine) as db:
        device = Device(
            source_device_id="anker_solix_test",
            vendor="anker_solix",
            model="test",
            device_type="storage",
            topology_role="storage",
            integration="anker_solix_official",
            source_mode="simulator",
        )
        db.add(device)
        db.commit()
        proposal = Proposal(
            device_id=device.id,
            strategy_mode=StrategyMode.BACKUP,
            capability="backup_reserve",
            current_value=25,
            target_value=80,
            reason_code="TARGET_DIFFERS",
            reason="test",
            status=ProposalStatus.EXECUTING,
        )
        db.add(proposal)
        db.commit()
        runtime = DiscoveredDeviceSchema(
            device_id="anker_solix_test",
            vendor="anker_solix",
            model="test",
            device_type="storage",
            topology_role="storage",
            integration="anker_solix_official",
            source_mode="simulator",
            online=True,
            observed_at="2026-09-18T00:00:00+00:00",
            controls=[
                DeviceCapabilitySchema(
                    name="backup_reserve",
                    entity_id="number.test_backup_reserve",
                    access="read_write",
                    value=25,
                    available=True,
                    verified=True,
                    min=0,
                    max=100,
                    step=1,
                    observed_at="2026-09-18T00:00:00+00:00",
                )
            ],
        )

        execution = asyncio.run(
            execution_service.execute(db=db, proposal=proposal, runtime=runtime)
        )

        assert execution.status == ExecutionStatus.SUCCEEDED
        assert execution.readback_value == 80
        assert proposal.status == ProposalStatus.SUCCEEDED
        assert calls[0]["domain"] == "number"
        assert calls[0]["service"] == "set_value"
        assert calls[0]["service_data"] == {"value": 80}
