from sqlalchemy.orm import Session

from app.modules.critical_load.models.critical_load import CriticalLoad
from app.modules.critical_load.repositories.critical_load_repository import critical_load_repository
from app.modules.critical_load.schemas.critical_load import (
    CriticalLoadCreateSchema,
    CriticalLoadListSchema,
    CriticalLoadUpdateSchema,
)


class CriticalLoadNotFoundError(Exception):
    pass


class CriticalLoadService:
    @staticmethod
    def list(db: Session) -> CriticalLoadListSchema:
        items = critical_load_repository.list_all(db)
        enabled = [item for item in items if item.enabled]
        return CriticalLoadListSchema(
            count=len(items),
            enabled_count=len(enabled),
            total_power_w=round(sum(item.rated_power_w for item in enabled), 2),
            loads=items,
        )

    @staticmethod
    def create(db: Session, request: CriticalLoadCreateSchema) -> CriticalLoad:
        return critical_load_repository.save(db, CriticalLoad(**request.model_dump()))

    @staticmethod
    def update(db: Session, load_id: int, request: CriticalLoadUpdateSchema) -> CriticalLoad:
        item = critical_load_repository.get(db, load_id)
        if item is None:
            raise CriticalLoadNotFoundError(f"Critical load not found: {load_id}")
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        return critical_load_repository.save(db, item)

    @staticmethod
    def delete(db: Session, load_id: int) -> None:
        item = critical_load_repository.get(db, load_id)
        if item is None:
            raise CriticalLoadNotFoundError(f"Critical load not found: {load_id}")
        critical_load_repository.delete(db, item)


critical_load_service = CriticalLoadService()

