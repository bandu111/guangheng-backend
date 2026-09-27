from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HermesToolResultSchema(BaseModel):
    success: bool
    tool: str
    data: Any | None = None
    error_code: str | None = None
    message: str | None = None
    observed_at: datetime
