from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.decision_context.schemas.decision_context import DecisionContextSchema
from app.modules.decision_context.services.decision_context_service import (
    decision_context_service,
)


router = APIRouter(prefix="/decision-context", tags=["Decision Context"])


@router.get("", response_model=DecisionContextSchema)
async def get_decision_context(db: Session = Depends(get_db)):
    return await decision_context_service.get_context(db=db)
