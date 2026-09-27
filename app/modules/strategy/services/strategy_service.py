from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.modules.strategy.models.strategy import StrategyConfig, StrategyMode
from app.modules.strategy.repositories.strategy_repository import strategy_repository
from app.modules.strategy.schemas.strategy import StrategyResponseSchema


BASE_DIR = Path(__file__).resolve().parents[4]
STRATEGY_POLICY_PATH = BASE_DIR / "config" / "strategy_policy.yaml"


class StrategyPolicyError(RuntimeError):
    pass


class StrategyService:
    @staticmethod
    def load_policy() -> dict[str, Any]:
        with STRATEGY_POLICY_PATH.open("r", encoding="utf-8") as file:
            policy = yaml.safe_load(file) or {}
        if "strategies" not in policy:
            raise StrategyPolicyError("Strategy policy has no strategies section.")
        return policy

    def target_for(self, mode: StrategyMode) -> float:
        try:
            return float(
                self.load_policy()["strategies"][mode.value][
                    "backup_reserve_target"
                ]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise StrategyPolicyError(
                f"No valid backup reserve target for strategy {mode.value}."
            ) from exc

    def get_current_model(self, db: Session) -> StrategyConfig:
        strategy = strategy_repository.get_current(db)
        if strategy is None:
            strategy = strategy_repository.save(
                db, StrategyConfig(mode=StrategyMode.AUTO)
            )
        return strategy

    def get_current(self, db: Session) -> StrategyResponseSchema:
        strategy = self.get_current_model(db)
        return StrategyResponseSchema(
            id=strategy.id,
            mode=strategy.mode,
            backup_reserve_target=self.target_for(strategy.mode),
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
        )

    def update(self, db: Session, mode: StrategyMode) -> StrategyResponseSchema:
        strategy = self.get_current_model(db)
        strategy.mode = mode
        strategy = strategy_repository.save(db, strategy)
        return StrategyResponseSchema(
            id=strategy.id,
            mode=strategy.mode,
            backup_reserve_target=self.target_for(strategy.mode),
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
        )


strategy_service = StrategyService()
