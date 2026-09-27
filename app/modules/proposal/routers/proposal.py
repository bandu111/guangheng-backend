from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.proposal.repositories.proposal_repository import proposal_repository
from app.modules.proposal.schemas.proposal import (
    ProposalActionResponseSchema,
    ProposalGenerationResponseSchema,
    ProposalListResponseSchema,
    ProposalResponseSchema,
)
from app.modules.proposal.services.proposal_service import (
    InvalidProposalStateError,
    ProposalNotFoundError,
    ProposalPermissionError,
    RuntimeUnavailableError,
    proposal_service,
)


router = APIRouter(prefix="/proposals", tags=["Proposal"])


@router.post("/generate", response_model=ProposalGenerationResponseSchema)
async def generate_proposal(db: Session = Depends(get_db)):
    try:
        return await proposal_service.generate(db)
    except ProposalPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("", response_model=ProposalListResponseSchema)
def list_proposals(db: Session = Depends(get_db)):
    proposals = proposal_repository.get_all(db)
    return ProposalListResponseSchema(count=len(proposals), proposals=proposals)


@router.get("/{proposal_id}", response_model=ProposalResponseSchema)
def get_proposal(proposal_id: int, db: Session = Depends(get_db)):
    try:
        return proposal_service.get(db, proposal_id)
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{proposal_id}/approve", response_model=ProposalActionResponseSchema)
async def approve_proposal(proposal_id: int, db: Session = Depends(get_db)):
    try:
        return await proposal_service.approve(db, proposal_id)
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidProposalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{proposal_id}/reject", response_model=ProposalActionResponseSchema)
def reject_proposal(proposal_id: int, db: Session = Depends(get_db)):
    try:
        return proposal_service.reject(db, proposal_id)
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidProposalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
