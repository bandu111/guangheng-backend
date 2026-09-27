from typing import Any

import httpx

from app.core.config import settings


class OpenMeteoService:
    async def get_forecast(
        self,
        *,
        latitude: float,
        longitude: float,
        time_zone: str,
    ) -> dict[str, Any]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(
                (
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "precipitation",
                    "weather_code",
                    "cloud_cover",
                    "wind_speed_10m",
                    "is_day",
                    "shortwave_radiation",
                    "direct_normal_irradiance",
                )
            ),
            "hourly": ",".join(
                (
                    "temperature_2m",
                    "precipitation_probability",
                    "precipitation",
                    "cloud_cover",
                    "shortwave_radiation",
                    "direct_normal_irradiance",
                )
            ),
            "forecast_hours": 24,
            "timezone": time_zone,
        }

        async with httpx.AsyncClient(
            timeout=settings.weather_timeout_seconds,
        ) as client:
            response = await client.get(
                settings.weather_base_url,
                params=params,
            )
            response.raise_for_status()
            return response.json()


open_meteo_service = OpenMeteoService()
