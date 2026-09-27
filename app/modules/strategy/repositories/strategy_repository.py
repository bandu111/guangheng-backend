from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.strategy.models.strategy import StrategyConfig


class StrategyRepository:
    def get_current(self, db: Session) -> StrategyConfig | None:
        return db.scalar(
            select(StrategyConfig).order_by(StrategyConfig.id.desc()).limit(1)
        )

    def save(self, db: Session, strategy: StrategyConfig) -> StrategyConfig:
        try:
            db.add(strategy)
            db.commit()
            db.refresh(strategy)
        except Exception:
            db.rollback()
            raise
        return strategy


strategy_repository = StrategyRepository()
