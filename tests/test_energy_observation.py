import asyncio
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.modules.energy_state.services.energy_observation_service as observation_module
from app.modules.energy_state.models.energy_observation import EnergyObservation
from app.modules.energy_state.repositories.energy_observation_repository import (
    energy_observation_repository,
)
from app.modules.energy_state.schemas.energy_state import (
    EnergyPowerStateSchema,
    EnergySourceSchema,
    EnergyStateResponseSchema,
    EnergyStorageStateSchema,
)
from app.modules.energy_state.services.energy_observation_policy_service import (
    EnergyObservationPolicy,
)
from app.modules.energy_state.services.energy_observation_service import (
    EnergyObservationService,
)


class FakeEnergyStateService:
    async def get_energy_state(self, db):
        return EnergyStateResponseSchema(
            available=True,
            online=True,
            source=EnergySourceSchema(
                device_id=1,
                source_device_id="test-device",
                source_mode="simulator",
            ),
            power=EnergyPowerStateSchema(
                solar_w=1800,
                home_load_w=1200,
                grid_import_w=0,
                grid_export_w=600,
            ),
            storage=EnergyStorageStateSchema(soc_percent=72),
        )


def test_backend_capture_persists_without_any_app_request(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    EnergyObservation.__table__.create(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(
        observation_module, "energy_state_service", FakeEnergyStateService()
    )
    service = EnergyObservationService(
        EnergyObservationPolicy(
            enabled=True,
            interval_seconds=300,
            initial_delay_seconds=5,
            retention_days=30,
            max_hold_seconds=900,
        )
    )

    with session_factory() as db:
        asyncio.run(service.capture(db))
        rows = energy_observation_repository.list_between(
            db,
            start_at=datetime.min,
            end_at=datetime.max,
        )

    assert len(rows) == 1
    assert rows[0].solar_w == 1800
    assert rows[0].home_load_w == 1200
    assert rows[0].soc_percent == 72
