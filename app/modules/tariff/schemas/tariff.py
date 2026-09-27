from datetime import datetime

from pydantic import BaseModel


class TariffCurrentSchema(BaseModel):
    price_per_kwh: float
    currency: str
    period: str | None = None


class TariffSourceSchema(BaseModel):
    provider: str
    pricing_type: str
    region: str
    reference_date: str | None = None
    realtime: bool


class TariffContextSchema(BaseModel):
    available: bool
    current: TariffCurrentSchema | None = None
    source: TariffSourceSchema
    observed_at: datetime
