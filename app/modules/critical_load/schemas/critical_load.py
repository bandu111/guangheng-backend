from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CriticalLoadCreateSchema(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    rated_power_w: float = Field(gt=0, le=20_000)
    enabled: bool = True


class CriticalLoadUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    rated_power_w: float | None = Field(default=None, gt=0, le=20_000)
    enabled: bool | None = None


class CriticalLoadSchema(BaseModel):
    id: int
    name: str
    category: str
    rated_power_w: float
    enabled: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class CriticalLoadListSchema(BaseModel):
    count: int
    enabled_count: int
    total_power_w: float
    loads: list[CriticalLoadSchema]

