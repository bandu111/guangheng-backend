from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.strategy.schemas.strategy import (
    StrategyResponseSchema,
    StrategyUpdateSchema,
)
from app.modules.strategy.services.strategy_service import (
    StrategyPolicyError,
    strategy_service,
)


router = APIRouter(prefix="/strategy", tags=["Strategy"])


@router.get("", response_model=StrategyResponseSchema)
def get_strategy(db: Session = Depends(get_db)):
    try:
        return strategy_service.get_current(db)
    except StrategyPolicyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("", response_model=StrategyResponseSchema)
def update_strategy(
    request: StrategyUpdateSchema,
    db: Session = Depends(get_db),
):
    try:
        return strategy_service.update(db, request.mode)
    except StrategyPolicyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
