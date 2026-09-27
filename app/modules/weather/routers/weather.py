from fastapi import APIRouter

from app.modules.weather.schemas.weather import WeatherContextSchema
from app.modules.weather.services.weather_service import weather_service


router = APIRouter(prefix="/weather", tags=["Weather Context"])


@router.get("", response_model=WeatherContextSchema)
async def get_weather():
    return await weather_service.get_weather()
