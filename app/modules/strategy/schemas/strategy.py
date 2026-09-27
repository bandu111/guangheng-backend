from datetime import datetime

from pydantic import BaseModel

from app.modules.strategy.models.strategy import StrategyMode


class StrategyUpdateSchema(BaseModel):
    mode: StrategyMode


class StrategyResponseSchema(BaseModel):
    id: int
    mode: StrategyMode
    backup_reserve_target: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
