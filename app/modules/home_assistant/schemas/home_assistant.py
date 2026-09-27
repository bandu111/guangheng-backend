from typing import Any

from pydantic import BaseModel, Field

class HomeAssistantStateSchema(BaseModel):
    entity_id: str
    state: str

    attributes: dict[str, Any] = Field(default_factory=dict)

    last_changed: str | None = None
    last_reported: str | None = None
    last_updated: str | None = None

    context: dict[str, Any] = Field(default_factory=dict)


class HomeAssistantConfigSchema(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    location_name: str | None = None
    time_zone: str


class HomeAssistantHistoryStateSchema(BaseModel):
    entity_id: str | None = None
    state: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    last_changed: str | None = None
    last_updated: str | None = None
