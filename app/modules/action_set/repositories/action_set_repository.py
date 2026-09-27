from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.action_set.models.action_set import (
    ActionSet,
    ActionSetItem,
    ActionSetStatus,
)


class ActionSetRepository:
    def save(self, db: Session, value):
        db.add(value)
        db.commit()
        db.refresh(value)
        return value

    def get(self, db: Session, action_set_id: int) -> ActionSet | None:
        return db.get(ActionSet, action_set_id)

    def list(self, db: Session) -> list[ActionSet]:
        return list(db.scalars(select(ActionSet).order_by(ActionSet.id.desc())).all())

    def get_pending(self, db: Session) -> ActionSet | None:
        return db.scalar(
            select(ActionSet)
            .where(ActionSet.status == ActionSetStatus.PENDING)
            .order_by(ActionSet.id.desc())
        )

    def latest(self, db: Session) -> ActionSet | None:
        return db.scalar(select(ActionSet).order_by(ActionSet.id.desc()))

    def items(self, db: Session, action_set_id: int) -> list[ActionSetItem]:
        return list(
            db.scalars(
                select(ActionSetItem)
                .where(ActionSetItem.action_set_id == action_set_id)
                .order_by(ActionSetItem.sequence.asc())
            ).all()
        )


action_set_repository = ActionSetRepository()
