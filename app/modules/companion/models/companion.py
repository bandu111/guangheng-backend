from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanionDevice(Base):
    __tablename__ = "companion_devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_uid: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100), default="光衡随身终端")
    credential_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CompanionPairingSession(Base):
    __tablename__ = "companion_pairing_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_uid: Mapped[str] = mapped_column(String(80), index=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    poll_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CompanionApprovalChallenge(Base):
    __tablename__ = "companion_approval_challenges"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("companion_devices.id"), index=True, nullable=False
    )
    action_set_id: Mapped[int] = mapped_column(
        ForeignKey("action_sets.id"), index=True, nullable=False
    )
    nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    action_set_version: Mapped[str] = mapped_column(String(40), nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
