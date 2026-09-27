from fastapi import APIRouter

from app.modules.system_health.schemas.system_health import SystemHealthSchema
from app.modules.system_health.services.system_health_service import system_health_service


router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/summary", response_model=SystemHealthSchema)
async def get_system_health():
    return await system_health_service.get_summary()

