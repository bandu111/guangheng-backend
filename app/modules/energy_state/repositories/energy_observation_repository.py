from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.energy_state.models.energy_observation import EnergyObservation


class EnergyObservationRepository:
    @staticmethod
    def create(db: Session, observation: EnergyObservation) -> EnergyObservation:
        try:
            db.add(observation)
            db.commit()
            db.refresh(observation)
        except Exception:
            db.rollback()
            raise
        return observation

    @staticmethod
    def list_between(
        db: Session, start_at: datetime, end_at: datetime
    ) -> list[EnergyObservation]:
        statement = (
            select(EnergyObservation)
            .where(EnergyObservation.observed_at >= start_at)
            .where(EnergyObservation.observed_at <= end_at)
            .order_by(EnergyObservation.observed_at.asc())
        )
        return list(db.scalars(statement).all())

    @staticmethod
    def delete_before(db: Session, cutoff: datetime) -> int:
        try:
            result = db.execute(
                delete(EnergyObservation).where(
                    EnergyObservation.observed_at < cutoff
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return int(result.rowcount or 0)


energy_observation_repository = EnergyObservationRepository()
