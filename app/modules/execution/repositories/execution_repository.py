from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.execution.models.execution import Execution


class ExecutionRepository:
    def create(self, db: Session, execution: Execution) -> Execution:
        try:
            db.add(execution)
            db.commit()
            db.refresh(execution)
        except Exception:
            db.rollback()
            raise
        return execution

    def save(self, db: Session, execution: Execution) -> Execution:
        try:
            db.add(execution)
            db.commit()
            db.refresh(execution)
        except Exception:
            db.rollback()
            raise
        return execution

    def get_by_id(self, db: Session, execution_id: int) -> Execution | None:
        return db.get(Execution, execution_id)

    def get_by_proposal_id(self, db: Session, proposal_id: int) -> Execution | None:
        return db.scalar(select(Execution).where(Execution.proposal_id == proposal_id))

    def get_all(self, db: Session) -> list[Execution]:
        return list(db.scalars(select(Execution).order_by(Execution.id.desc())).all())


execution_repository = ExecutionRepository()
