from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.solar_forecast.schemas.solar_forecast import (
    SolarForecastResponseSchema,
)
from app.modules.solar_forecast.services.solar_forecast_service import (
    solar_forecast_service,
)


router = APIRouter(prefix="/solar-forecast", tags=["Solar Forecast"])


@router.get("", response_model=SolarForecastResponseSchema)
async def get_solar_forecast(db: Session = Depends(get_db)):
    return await solar_forecast_service.get_forecast(db=db)
