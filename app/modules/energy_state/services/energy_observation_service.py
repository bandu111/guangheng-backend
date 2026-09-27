from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.modules.energy_state.models.energy_observation import EnergyObservation
from app.modules.energy_state.repositories.energy_observation_repository import (
    energy_observation_repository,
)
from app.modules.energy_state.services.energy_observation_policy_service import (
    EnergyObservationPolicy,
    energy_observation_policy,
)
from app.modules.energy_state.services.energy_state_service import energy_state_service


class EnergyObservationService:
    def __init__(
        self, policy: EnergyObservationPolicy = energy_observation_policy
    ) -> None:
        self.policy = policy

    async def capture(self, db: Session) -> EnergyObservation:
        observed_at = datetime.now(timezone.utc)
        state = await energy_state_service.get_energy_state(db)
        observation = EnergyObservation(
            # SQLite stores UTC as a naive datetime in this project.
            observed_at=observed_at.replace(tzinfo=None),
            available=state.available,
            online=state.online,
            source_mode=state.source.source_mode if state.source else None,
            solar_w=state.power.solar_w,
            home_load_w=state.power.home_load_w,
            battery_charging_w=state.power.battery_charging_w,
            battery_discharging_w=state.power.battery_discharging_w,
            grid_import_w=state.power.grid_import_w,
            grid_export_w=state.power.grid_export_w,
            soc_percent=state.storage.soc_percent,
        )
        saved = energy_observation_repository.create(db, observation)
        energy_observation_repository.delete_before(
            db,
            (observed_at - timedelta(days=self.policy.retention_days)).replace(
                tzinfo=None
            ),
        )
        return saved


energy_observation_service = EnergyObservationService()
