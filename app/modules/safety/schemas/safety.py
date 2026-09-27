from typing import Any

from pydantic import BaseModel, Field


class SafetyCheckResponseSchema(BaseModel):
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    reason_code: str
    message: str
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
