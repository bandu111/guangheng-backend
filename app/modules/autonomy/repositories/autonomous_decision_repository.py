from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.autonomy.models.autonomous_decision_run import (
    AutonomousDecisionRun,
)


class AutonomousDecisionRepository:
    def create(
        self, db: Session, run: AutonomousDecisionRun
    ) -> AutonomousDecisionRun:
        return self.save(db, run)

    def save(
        self, db: Session, run: AutonomousDecisionRun
    ) -> AutonomousDecisionRun:
        try:
            db.add(run)
            db.commit()
            db.refresh(run)
        except Exception:
            db.rollback()
            raise
        return run

    def get_by_id(self, db: Session, run_id: int) -> AutonomousDecisionRun | None:
        return db.get(AutonomousDecisionRun, run_id)

    def get_latest(self, db: Session) -> AutonomousDecisionRun | None:
        statement = select(AutonomousDecisionRun).order_by(
            AutonomousDecisionRun.id.desc()
        )
        return db.scalar(statement)

    def list(self, db: Session, limit: int) -> list[AutonomousDecisionRun]:
        statement = (
            select(AutonomousDecisionRun)
            .order_by(AutonomousDecisionRun.id.desc())
            .limit(limit)
        )
        return list(db.scalars(statement).all())


autonomous_decision_repository = AutonomousDecisionRepository()
