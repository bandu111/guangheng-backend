from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.critical_load.models.critical_load import CriticalLoad


class CriticalLoadRepository:
    @staticmethod
    def list_all(db: Session) -> list[CriticalLoad]:
        return list(db.scalars(select(CriticalLoad).order_by(CriticalLoad.id.asc())).all())

    @staticmethod
    def get(db: Session, load_id: int) -> CriticalLoad | None:
        return db.get(CriticalLoad, load_id)

    @staticmethod
    def save(db: Session, item: CriticalLoad) -> CriticalLoad:
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def delete(db: Session, item: CriticalLoad) -> None:
        db.delete(item)
        db.commit()


critical_load_repository = CriticalLoadRepository()

