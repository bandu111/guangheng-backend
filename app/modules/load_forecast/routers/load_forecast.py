from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.load_forecast.schemas.load_forecast import (
    LoadForecastResponseSchema,
)
from app.modules.load_forecast.services.load_forecast_service import (
    load_forecast_service,
)


router = APIRouter(prefix="/load-forecast", tags=["Load Forecast"])


@router.get("", response_model=LoadForecastResponseSchema)
async def get_load_forecast(db: Session = Depends(get_db)):
    return await load_forecast_service.get_forecast(db=db)
