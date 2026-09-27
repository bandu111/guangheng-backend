from fastapi import APIRouter

from app.modules.area_energy.schemas.area_energy import (
    AreaLoadViewSchema,
    SmartMeterInsightSchema,
)
from app.modules.area_energy.services.area_energy_service import area_energy_service


router = APIRouter(tags=["Area Energy"])


@router.get("/areas/load-view", response_model=AreaLoadViewSchema)
async def get_area_load_view():
    return await area_energy_service.get_load_view()


@router.get(
    "/meters/{device_id}/insight", response_model=SmartMeterInsightSchema
)
async def get_meter_insight(device_id: str):
    return await area_energy_service.get_meter_insight(device_id)
