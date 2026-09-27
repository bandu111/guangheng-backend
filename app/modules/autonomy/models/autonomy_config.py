from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AutonomyLevel(str, Enum):
    OBSERVE = "OBSERVE"
    SHADOW = "SHADOW"
    CONFIRM = "CONFIRM"
    AUTO = "AUTO"


class AutonomyConfig(Base):
    __tablename__ = "autonomy_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    level: Mapped[AutonomyLevel] = mapped_column(
        SqlEnum(AutonomyLevel, native_enum=False, length=20),
        default=AutonomyLevel.CONFIRM,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
