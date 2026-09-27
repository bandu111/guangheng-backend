from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.execution.repositories.execution_repository import execution_repository
from app.modules.execution.schemas.execution import (
    ExecutionListResponseSchema,
    ExecutionResponseSchema,
)


router = APIRouter(prefix="/executions", tags=["Execution"])


@router.get("", response_model=ExecutionListResponseSchema)
def list_executions(db: Session = Depends(get_db)):
    executions = execution_repository.get_all(db)
    return ExecutionListResponseSchema(count=len(executions), executions=executions)


@router.get("/{execution_id}", response_model=ExecutionResponseSchema)
def get_execution(execution_id: int, db: Session = Depends(get_db)):
    execution = execution_repository.get_by_id(db, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found.")
    return execution
