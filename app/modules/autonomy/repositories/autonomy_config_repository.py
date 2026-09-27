from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.autonomy.models.autonomy_config import AutonomyConfig


class AutonomyConfigRepository:
    def get_current(self, db: Session) -> AutonomyConfig | None:
        return db.scalar(
            select(AutonomyConfig).order_by(AutonomyConfig.id.desc()).limit(1)
        )

    def save(self, db: Session, config: AutonomyConfig) -> AutonomyConfig:
        try:
            db.add(config)
            db.commit()
            db.refresh(config)
        except Exception:
            db.rollback()
            raise
        return config


autonomy_config_repository = AutonomyConfigRepository()
