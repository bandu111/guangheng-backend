from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from app.modules.hermes.schemas.tool import HermesToolResultSchema


def serialize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [serialize(item) for item in value]
    return value


def success(tool: str, data: Any) -> HermesToolResultSchema:
    return HermesToolResultSchema(
        success=True,
        tool=tool,
        data=serialize(data),
        observed_at=datetime.now(timezone.utc),
    )


def failure(
    tool: str,
    error_code: str,
    message: str,
) -> HermesToolResultSchema:
    return HermesToolResultSchema(
        success=False,
        tool=tool,
        error_code=error_code,
        message=message,
        observed_at=datetime.now(timezone.utc),
    )
