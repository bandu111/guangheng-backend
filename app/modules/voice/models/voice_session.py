from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VoiceSession(Base):
    __tablename__ = "voice_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    companion_device_id: Mapped[int] = mapped_column(
        ForeignKey("companion_devices.id"), nullable=False, index=True
    )
    audio_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    audio_duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    asr_provider: Mapped[str] = mapped_column(String(60), nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    hermes_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    hermes_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    asr_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hermes_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
