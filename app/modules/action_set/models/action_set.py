from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ActionSetStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"


class ActionSetItemStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    REJECTED = "REJECTED"


class ActionSetVerificationStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    UNAVAILABLE = "UNAVAILABLE"


class ActionSet(Base):
    __tablename__ = "action_sets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    opportunity_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ActionSetStatus] = mapped_column(
        SqlEnum(ActionSetStatus, native_enum=False, length=20),
        default=ActionSetStatus.PENDING,
        nullable=False,
        index=True,
    )
    expected_grid_delta_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    before_grid_power_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    after_grid_power_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_grid_delta_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    verification_status: Mapped[ActionSetVerificationStatus] = mapped_column(
        SqlEnum(ActionSetVerificationStatus, native_enum=False, length=20),
        default=ActionSetVerificationStatus.PENDING,
        nullable=False,
    )
    verification_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class ActionSetItem(Base):
    __tablename__ = "action_set_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    action_set_id: Mapped[int] = mapped_column(
        ForeignKey("action_sets.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    source_device_id: Mapped[str] = mapped_column(String(255), nullable=False)
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    capability: Mapped[str] = mapped_column(String(100), nullable=False)
    current_value: Mapped[float] = mapped_column(Float, nullable=False)
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    expected_delta_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"), nullable=False)
    execution_id: Mapped[int | None] = mapped_column(ForeignKey("executions.id"), nullable=True)
    status: Mapped[ActionSetItemStatus] = mapped_column(
        SqlEnum(ActionSetItemStatus, native_enum=False, length=20),
        default=ActionSetItemStatus.PENDING,
        nullable=False,
    )
    result_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
