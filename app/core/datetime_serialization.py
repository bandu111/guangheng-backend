from datetime import datetime, timezone


def serialize_utc_datetime(value: datetime | None) -> str | None:
    """Serialize database UTC timestamps with an explicit timezone marker."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")
