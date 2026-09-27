from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AutonomousTriggerType(str, Enum):
    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"


class AutonomousRunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AutonomousDecisionRun(Base):
    __tablename__ = "autonomous_decision_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trigger_type: Mapped[AutonomousTriggerType] = mapped_column(
        SqlEnum(AutonomousTriggerType, native_enum=False, length=20),
        nullable=False,
    )
    status: Mapped[AutonomousRunStatus] = mapped_column(
        SqlEnum(AutonomousRunStatus, native_enum=False, length=20),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(30), nullable=True)
    capability: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    action_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(30), nullable=True)
    proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposals.id"), nullable=True, index=True
    )
    notification_event_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    result_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    decision_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
