from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.hermes.schemas.hermes import (
    AgentMessageListSchema,
    AgentSessionCreateSchema,
    AgentSessionDetailSchema,
    HermesChatRequestSchema,
    HermesChatResponseSchema,
)
from app.modules.hermes.services.agent_service import (
    AgentSessionNotFoundError,
    agent_service,
)


router = APIRouter(prefix="/hermes", tags=["Hermes Agent"])


@router.post("/sessions", response_model=AgentSessionCreateSchema)
def create_hermes_session(db: Session = Depends(get_db)) -> AgentSessionCreateSchema:
    return agent_service.create_session(db)


@router.get("/sessions/{session_id}", response_model=AgentSessionDetailSchema)
def get_hermes_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> AgentSessionDetailSchema:
    try:
        return agent_service.get_session(db, session_id)
    except AgentSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Agent session not found.") from exc


@router.get(
    "/sessions/{session_id}/messages",
    response_model=AgentMessageListSchema,
)
def get_hermes_messages(
    session_id: str,
    db: Session = Depends(get_db),
) -> AgentMessageListSchema:
    try:
        return agent_service.get_messages(db, session_id)
    except AgentSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Agent session not found.") from exc


@router.post("/chat", response_model=HermesChatResponseSchema)
async def chat_with_hermes(
    request: HermesChatRequestSchema,
    db: Session = Depends(get_db),
) -> HermesChatResponseSchema:
    try:
        return await agent_service.chat(
            db=db,
            session_id=request.session_id,
            message=request.message,
        )
    except AgentSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Agent session not found.") from exc
