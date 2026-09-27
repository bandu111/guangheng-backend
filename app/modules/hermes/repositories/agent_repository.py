from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.hermes.models.agent_conversation import (
    AgentMessage,
    AgentSession,
    AgentToolCall,
)


class AgentRepository:
    def create_session(self, db: Session, session: AgentSession) -> AgentSession:
        return self._save(db, session)

    def save_session(self, db: Session, session: AgentSession) -> AgentSession:
        return self._save(db, session)

    def get_session(self, db: Session, session_id: str) -> AgentSession | None:
        return db.get(AgentSession, session_id)

    def count_messages(self, db: Session, session_id: str) -> int:
        statement = select(func.count(AgentMessage.id)).where(
            AgentMessage.session_id == session_id
        )
        return int(db.scalar(statement) or 0)

    def create_message(self, db: Session, message: AgentMessage) -> AgentMessage:
        return self._save(db, message)

    def list_messages(self, db: Session, session_id: str) -> list[AgentMessage]:
        statement = (
            select(AgentMessage)
            .where(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.created_at, AgentMessage.id)
        )
        return list(db.scalars(statement).all())

    def create_tool_calls(
        self, db: Session, tool_calls: list[AgentToolCall]
    ) -> list[AgentToolCall]:
        if not tool_calls:
            return []
        try:
            db.add_all(tool_calls)
            db.commit()
            for item in tool_calls:
                db.refresh(item)
        except Exception:
            db.rollback()
            raise
        return tool_calls

    def list_tool_calls(self, db: Session, message_id: str) -> list[AgentToolCall]:
        statement = (
            select(AgentToolCall)
            .where(AgentToolCall.message_id == message_id)
            .order_by(AgentToolCall.sequence)
        )
        return list(db.scalars(statement).all())

    @staticmethod
    def _save(db: Session, value):
        try:
            db.add(value)
            db.commit()
            db.refresh(value)
        except Exception:
            db.rollback()
            raise
        return value


agent_repository = AgentRepository()
