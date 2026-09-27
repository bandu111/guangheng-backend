from pydantic import BaseModel

from app.modules.strategy.models.strategy import StrategyMode


class OptimizerDecisionSchema(BaseModel):
    action_required: bool
    device_id: int | None = None
    capability: str = "backup_reserve"
    current_value: float | None = None
    target_value: float | None = None
    reason_code: str
    reason: str
    strategy_mode: StrategyMode
