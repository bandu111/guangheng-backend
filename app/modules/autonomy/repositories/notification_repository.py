from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.autonomy.models.notification_event import (
    NotificationEvent,
    NotificationStatus,
)


class NotificationRepository:
    def create(self, db: Session, event: NotificationEvent) -> NotificationEvent:
        return self.save(db, event)

    def save(self, db: Session, event: NotificationEvent) -> NotificationEvent:
        try:
            db.add(event)
            db.commit()
            db.refresh(event)
        except Exception:
            db.rollback()
            raise
        return event

    def get_by_id(self, db: Session, event_id: int) -> NotificationEvent | None:
        return db.get(NotificationEvent, event_id)

    def get_unread_by_dedupe_key(
        self, db: Session, dedupe_key: str
    ) -> NotificationEvent | None:
        statement = select(NotificationEvent).where(
            NotificationEvent.dedupe_key == dedupe_key,
            NotificationEvent.status == NotificationStatus.UNREAD,
        )
        return db.scalar(statement)

    def list(
        self,
        db: Session,
        limit: int,
        status: NotificationStatus | None = None,
    ) -> list[NotificationEvent]:
        statement = select(NotificationEvent)
        if status is not None:
            statement = statement.where(NotificationEvent.status == status)
        statement = statement.order_by(NotificationEvent.id.desc()).limit(limit)
        return list(db.scalars(statement).all())

    def count_unread(self, db: Session) -> int:
        statement = select(func.count(NotificationEvent.id)).where(
            NotificationEvent.status == NotificationStatus.UNREAD
        )
        return int(db.scalar(statement) or 0)

    def mark_read(self, db: Session, event: NotificationEvent) -> NotificationEvent:
        if event.status == NotificationStatus.UNREAD:
            event.status = NotificationStatus.READ
            event.read_at = datetime.utcnow()
            return self.save(db, event)
        return event


notification_repository = NotificationRepository()
