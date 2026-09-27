from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.optimizer.schemas.optimizer_v2 import OptimizationDecisionV2Schema
from app.modules.optimizer.services.optimizer_evaluation_service import (
    optimizer_evaluation_service,
)


router = APIRouter(prefix="/optimizer", tags=["Optimizer"])


@router.post("/evaluate", response_model=OptimizationDecisionV2Schema)
async def evaluate_optimizer(db: Session = Depends(get_db)):
    return await optimizer_evaluation_service.evaluate(db=db)
