from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationEventType(str, Enum):
    ACTION_REQUIRED = "ACTION_REQUIRED"
    DECISION_COMPLETED = "DECISION_COMPLETED"
    SYSTEM_WARNING = "SYSTEM_WARNING"


class NotificationSeverity(str, Enum):
    INFO = "INFO"
    ATTENTION = "ATTENTION"
    WARNING = "WARNING"


class NotificationStatus(str, Enum):
    UNREAD = "UNREAD"
    READ = "READ"


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_type: Mapped[NotificationEventType] = mapped_column(
        SqlEnum(NotificationEventType, native_enum=False, length=30),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[NotificationSeverity] = mapped_column(
        SqlEnum(NotificationSeverity, native_enum=False, length=20),
        nullable=False,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        SqlEnum(NotificationStatus, native_enum=False, length=20),
        default=NotificationStatus.UNREAD,
        nullable=False,
        index=True,
    )
    decision_run_id: Mapped[int] = mapped_column(
        ForeignKey("autonomous_decision_runs.id"), nullable=False, index=True
    )
    proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposals.id"), nullable=True, index=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
