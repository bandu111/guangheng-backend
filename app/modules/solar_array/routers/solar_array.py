from fastapi import APIRouter, HTTPException

from app.modules.solar_array.schemas.solar_array import SolarArrayInsightSchema
from app.modules.solar_array.services.solar_array_service import (
    SolarArrayNotFoundError,
    solar_array_service,
)


router = APIRouter(tags=["Solar Array"])


@router.get(
    "/devices/{device_id}/solar-array-insight",
    response_model=SolarArrayInsightSchema,
)
async def get_solar_array_insight(device_id: str):
    try:
        return await solar_array_service.get_insight(device_id)
    except SolarArrayNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
