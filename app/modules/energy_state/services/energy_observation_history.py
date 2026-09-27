from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.modules.energy_state.repositories.energy_observation_repository import (
    energy_observation_repository,
)
from app.modules.home_assistant.schemas.home_assistant import (
    HomeAssistantHistoryStateSchema,
)


FIELD_MAP = {
    "solar": "solar_w",
    "home": "home_load_w",
    "grid": "grid_import_w",
    "grid_import": "grid_import_w",
    "grid_export": "grid_export_w",
}


def load_observation_histories(
    start_at: datetime, end_at: datetime, keys: set[str]
) -> dict[str, list[HomeAssistantHistoryStateSchema]]:
    with SessionLocal() as db:
        observations = energy_observation_repository.list_between(
            db,
            start_at.astimezone(timezone.utc).replace(tzinfo=None),
            end_at.astimezone(timezone.utc).replace(tzinfo=None),
        )
    histories: dict[str, list[HomeAssistantHistoryStateSchema]] = {
        key: [] for key in keys
    }
    for observation in observations:
        if not observation.available or not observation.online:
            continue
        observed_at = observation.observed_at.replace(tzinfo=timezone.utc).isoformat()
        for key in keys:
            field = FIELD_MAP.get(key)
            value = getattr(observation, field, None) if field else None
            if value is not None:
                histories[key].append(
                    HomeAssistantHistoryStateSchema(
                        state=str(value), last_updated=observed_at
                    )
                )
    return histories


def merge_histories(
    recorder: dict[str, list[HomeAssistantHistoryStateSchema]],
    observations: dict[str, list[HomeAssistantHistoryStateSchema]],
) -> dict[str, list[HomeAssistantHistoryStateSchema]]:
    merged: dict[str, list[HomeAssistantHistoryStateSchema]] = {}
    for key in recorder.keys() | observations.keys():
        items = [*recorder.get(key, []), *observations.get(key, [])]
        items.sort(key=lambda item: item.last_updated or item.last_changed or "")
        merged[key] = items
    return merged
