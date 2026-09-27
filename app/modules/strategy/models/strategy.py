from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StrategyMode(str, Enum):
    SAVE = "SAVE"
    AUTO = "AUTO"
    BACKUP = "BACKUP"


class StrategyConfig(Base):
    __tablename__ = "strategy_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mode: Mapped[StrategyMode] = mapped_column(
        SqlEnum(StrategyMode, native_enum=False, length=20),
        default=StrategyMode.AUTO,
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
