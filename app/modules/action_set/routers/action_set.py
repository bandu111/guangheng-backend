from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.action_set.schemas.action_set import (
    ActionSetGenerateRequest,
    ActionSetListSchema,
    ActionSetSchema,
)
from app.modules.action_set.services.action_set_service import (
    ActionSetNotFoundError,
    ActionSetOpportunityUnavailableError,
    InvalidActionSetStateError,
    action_set_service,
)
from app.modules.proposal.services.proposal_service import (
    ProposalPermissionError,
    RuntimeUnavailableError,
)


router = APIRouter(prefix="/action-sets", tags=["Coordinated Action Set"])


@router.post("/generate", response_model=ActionSetSchema)
async def generate_action_set(
    body: ActionSetGenerateRequest, db: Session = Depends(get_db)
):
    try:
        return await action_set_service.generate(db, body.opportunity_code)
    except ProposalPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ActionSetOpportunityUnavailableError, RuntimeUnavailableError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=ActionSetListSchema)
def list_action_sets(db: Session = Depends(get_db)):
    values = action_set_service.list(db)
    return ActionSetListSchema(count=len(values), action_sets=values)


@router.get("/pending", response_model=ActionSetSchema | None)
def get_pending_action_set(db: Session = Depends(get_db)):
    return action_set_service.pending(db)


@router.get("/{action_set_id}", response_model=ActionSetSchema)
def get_action_set(action_set_id: int, db: Session = Depends(get_db)):
    try:
        return action_set_service.get(db, action_set_id)
    except ActionSetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{action_set_id}/approve", response_model=ActionSetSchema)
def approve_action_set(
    action_set_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        result = action_set_service.approve(db, action_set_id)
    except ActionSetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidActionSetStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(action_set_service.execute_approved, action_set_id)
    return result


@router.post("/{action_set_id}/reject", response_model=ActionSetSchema)
def reject_action_set(action_set_id: int, db: Session = Depends(get_db)):
    try:
        return action_set_service.reject(db, action_set_id)
    except ActionSetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidActionSetStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
