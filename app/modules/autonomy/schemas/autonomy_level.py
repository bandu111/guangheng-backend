from datetime import datetime

from pydantic import BaseModel

from app.modules.autonomy.models.autonomy_config import AutonomyLevel


class AutonomyPermissionsSchema(BaseModel):
    observe: bool
    optimize: bool
    propose: bool
    execute_without_approval: bool


class AutonomyLevelOptionSchema(BaseModel):
    level: AutonomyLevel
    label: str
    description: str
    available: bool
    permissions: AutonomyPermissionsSchema


class AutonomyLevelUpdateSchema(BaseModel):
    level: AutonomyLevel


class AutonomyLevelResponseSchema(BaseModel):
    level: AutonomyLevel
    permissions: AutonomyPermissionsSchema
    options: list[AutonomyLevelOptionSchema]
    updated_at: datetime
