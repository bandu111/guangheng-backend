from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EnergyObservation(Base):
    __tablename__ = "energy_observations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    online: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    solar_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_load_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_charging_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_discharging_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    grid_import_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    grid_export_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    soc_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
