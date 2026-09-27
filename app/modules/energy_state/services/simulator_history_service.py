from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.modules.energy_state.models.energy_observation import EnergyObservation
from app.modules.energy_state.repositories.energy_observation_repository import (
    energy_observation_repository,
)
from app.modules.energy_state.services.simulator_energy_service import (
    simulator_energy_policy,
    simulator_energy_service,
)


class SimulatorHistoryService:
    """Seed deterministic demo history without touching real-device rows."""

    def ensure_recent_history(
        self,
        db: Session,
        *,
        observed_at: datetime,
        soc_percent: float | None,
    ) -> int:
        days = simulator_energy_policy.history_backfill_days
        if days <= 0:
            return 0
        end_at = observed_at.astimezone(timezone.utc).replace(tzinfo=None)
        start_at = end_at - timedelta(days=days)
        existing = energy_observation_repository.list_between(db, start_at, end_at)
        simulator_rows = [
            row for row in existing if row.source_mode == "simulator"
        ]
        interval_minutes = simulator_energy_policy.history_interval_minutes
        interval = timedelta(minutes=interval_minutes)
        interval_seconds = int(interval.total_seconds())
        occupied = {
            int(row.observed_at.timestamp()) // interval_seconds
            for row in simulator_rows
        }

        # Correct earlier static simulator rows with the same profile. Rows
        # captured from real Home Assistant devices are never selected here.
        for row in simulator_rows:
            self._apply_profile(row, row.observed_at, soc_percent)

        created: list[EnergyObservation] = []
        cursor = start_at.replace(
            minute=(start_at.minute // interval_minutes) * interval_minutes,
            second=0,
            microsecond=0,
        )
        while cursor <= end_at:
            bucket = int(cursor.timestamp()) // interval_seconds
            if bucket not in occupied:
                row = EnergyObservation(
                    observed_at=cursor,
                    available=True,
                    online=True,
                    source_mode="simulator",
                    soc_percent=soc_percent,
                )
                self._apply_profile(row, cursor, soc_percent)
                created.append(row)
            cursor += interval

        try:
            db.add_all(created)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return len(created)

    @staticmethod
    def _apply_profile(
        row: EnergyObservation,
        observed_at: datetime,
        soc_percent: float | None,
    ) -> None:
        aware = observed_at.replace(tzinfo=timezone.utc)
        power = simulator_energy_service.calculate(
            aware,
            soc_percent=soc_percent,
            reserve_percent=simulator_energy_policy.battery.default_reserve_percent,
        )
        row.solar_w = power.solar_w
        row.home_load_w = power.home_load_w
        row.battery_charging_w = power.battery_charging_w
        row.battery_discharging_w = power.battery_discharging_w
        row.grid_import_w = power.grid_import_w
        row.grid_export_w = power.grid_export_w


simulator_history_service = SimulatorHistoryService()
