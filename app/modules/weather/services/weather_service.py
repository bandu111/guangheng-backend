import asyncio
from datetime import datetime, timezone
from time import monotonic
from typing import Any

import httpx

from app.core.config import settings
from app.modules.home_assistant.services.home_assistant_service import (
    HomeAssistantConfigInvalidError,
    home_assistant_service,
)
from app.modules.weather.schemas.weather import (
    WeatherContextSchema,
    WeatherCurrentSchema,
    WeatherHourlySchema,
    WeatherLocationSchema,
)
from app.modules.weather.services.open_meteo_service import open_meteo_service


class WeatherService:
    def __init__(self) -> None:
        self._cached_context: WeatherContextSchema | None = None
        self._cache_expires_at = 0.0
        self._cache_lock = asyncio.Lock()

    def clear_cache(self) -> None:
        self._cached_context = None
        self._cache_expires_at = 0.0

    @staticmethod
    def condition_for(weather_code: int | None) -> str:
        if weather_code == 0:
            return "clear"
        if weather_code in {1, 2}:
            return "partly_cloudy"
        if weather_code == 3:
            return "cloudy"
        if weather_code in {45, 48}:
            return "fog"
        if weather_code in {51, 53, 55, 56, 57}:
            return "drizzle"
        if weather_code in {61, 63, 65, 66, 67, 80, 81, 82}:
            return "rain"
        if weather_code in {71, 73, 75, 77, 85, 86}:
            return "snow"
        if weather_code in {95, 96, 99}:
            return "thunderstorm"
        return "unknown"

    @staticmethod
    def _value(values: Any, index: int) -> Any:
        if not isinstance(values, list) or index >= len(values):
            return None
        return values[index]

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _normalize(
        self,
        raw: dict[str, Any],
        location: WeatherLocationSchema,
    ) -> WeatherContextSchema:
        current_raw = raw.get("current")
        hourly_raw = raw.get("hourly")
        if not isinstance(current_raw, dict) or not isinstance(hourly_raw, dict):
            return self._unavailable(
                "WEATHER_PROVIDER_INVALID_RESPONSE",
                "Weather provider response has no current or hourly object.",
                location=location,
            )

        weather_code = current_raw.get("weather_code")
        current = WeatherCurrentSchema(
            time=self._parse_time(current_raw.get("time")),
            temperature_c=current_raw.get("temperature_2m"),
            apparent_temperature_c=current_raw.get("apparent_temperature"),
            relative_humidity_percent=current_raw.get("relative_humidity_2m"),
            precipitation_mm=current_raw.get("precipitation"),
            weather_code=weather_code,
            condition=self.condition_for(weather_code),
            cloud_cover_percent=current_raw.get("cloud_cover"),
            wind_speed_kmh=current_raw.get("wind_speed_10m"),
            is_day=(
                bool(current_raw["is_day"])
                if current_raw.get("is_day") is not None
                else None
            ),
            shortwave_radiation_w_m2=current_raw.get("shortwave_radiation"),
            direct_normal_irradiance_w_m2=current_raw.get(
                "direct_normal_irradiance"
            ),
        )

        hourly: list[WeatherHourlySchema] = []
        times = hourly_raw.get("time")
        if isinstance(times, list):
            for index, value in enumerate(times[:24]):
                parsed_time = self._parse_time(value)
                if parsed_time is None:
                    continue
                hourly.append(
                    WeatherHourlySchema(
                        time=parsed_time,
                        temperature_c=self._value(
                            hourly_raw.get("temperature_2m"), index
                        ),
                        precipitation_probability_percent=self._value(
                            hourly_raw.get("precipitation_probability"), index
                        ),
                        precipitation_mm=self._value(
                            hourly_raw.get("precipitation"), index
                        ),
                        cloud_cover_percent=self._value(
                            hourly_raw.get("cloud_cover"), index
                        ),
                        shortwave_radiation_w_m2=self._value(
                            hourly_raw.get("shortwave_radiation"), index
                        ),
                        direct_normal_irradiance_w_m2=self._value(
                            hourly_raw.get("direct_normal_irradiance"), index
                        ),
                    )
                )

        return WeatherContextSchema(
            available=True,
            provider=settings.weather_provider,
            location=location,
            current=current,
            hourly=hourly,
            observed_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _unavailable(
        error_code: str,
        error_message: str,
        *,
        location: WeatherLocationSchema | None = None,
    ) -> WeatherContextSchema:
        return WeatherContextSchema(
            available=False,
            provider=settings.weather_provider,
            location=location,
            error_code=error_code,
            error_message=error_message,
        )

    async def get_weather(self) -> WeatherContextSchema:
        if self._cached_context is not None and monotonic() < self._cache_expires_at:
            return self._cached_context

        async with self._cache_lock:
            if self._cached_context is not None and monotonic() < self._cache_expires_at:
                return self._cached_context

            try:
                ha_config = await home_assistant_service.get_config()
            except HomeAssistantConfigInvalidError:
                return self._unavailable(
                    "HOME_LOCATION_UNAVAILABLE",
                    "Home Assistant has no valid home coordinates or time zone.",
                )
            except (httpx.HTTPError, OSError):
                return self._unavailable(
                    "HOME_ASSISTANT_CONFIG_UNAVAILABLE",
                    "Home Assistant configuration could not be read.",
                )

            location = WeatherLocationSchema(
                location_name=ha_config.location_name,
                time_zone=ha_config.time_zone,
            )
            if settings.weather_provider != "open_meteo":
                return self._unavailable(
                    "WEATHER_PROVIDER_UNSUPPORTED",
                    "Configured weather provider is not supported.",
                    location=location,
                )

            try:
                raw = await open_meteo_service.get_forecast(
                    latitude=ha_config.latitude,
                    longitude=ha_config.longitude,
                    time_zone=ha_config.time_zone,
                )
            except httpx.TimeoutException:
                return self._unavailable(
                    "WEATHER_PROVIDER_TIMEOUT",
                    "Weather provider request timed out.",
                    location=location,
                )
            except (httpx.HTTPError, OSError, ValueError):
                return self._unavailable(
                    "WEATHER_PROVIDER_UNAVAILABLE",
                    "Weather provider request failed.",
                    location=location,
                )

            context = self._normalize(raw, location)
            if context.available:
                self._cached_context = context
                self._cache_expires_at = monotonic() + settings.weather_cache_seconds
            return context


weather_service = WeatherService()
