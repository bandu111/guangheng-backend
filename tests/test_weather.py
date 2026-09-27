import asyncio

import httpx

from app.modules.home_assistant.schemas.home_assistant import HomeAssistantConfigSchema
from app.modules.home_assistant.services.home_assistant_service import (
    HomeAssistantConfigInvalidError,
)
from app.modules.weather.services.weather_service import WeatherService


def _ha_config() -> HomeAssistantConfigSchema:
    return HomeAssistantConfigSchema(
        latitude=22.5,
        longitude=114.0,
        location_name="Test Home",
        time_zone="Asia/Shanghai",
    )


def _provider_response() -> dict:
    return {
        "current": {
            "time": "2026-09-19T14:00",
            "temperature_2m": 28.3,
            "apparent_temperature": 30.1,
            "relative_humidity_2m": 72,
            "precipitation": 0.0,
            "weather_code": 1,
            "cloud_cover": 25,
            "wind_speed_10m": 8.4,
            "is_day": 1,
            "shortwave_radiation": 510.0,
            "direct_normal_irradiance": 430.0,
        },
        "hourly": {
            "time": ["2026-09-19T14:00", "2026-09-19T15:00"],
            "temperature_2m": [28.3, 28.0],
            "precipitation_probability": [10, 15],
            "precipitation": [0.0, 0.1],
            "cloud_cover": [25, 30],
            "shortwave_radiation": [510.0, 420.0],
            "direct_normal_irradiance": [430.0, 350.0],
        },
    }


def _patch_config(monkeypatch):
    async def get_config():
        return _ha_config()

    monkeypatch.setattr(
        "app.modules.weather.services.weather_service.home_assistant_service.get_config",
        get_config,
    )


def test_weather_normalizes_provider_response(monkeypatch):
    _patch_config(monkeypatch)

    async def get_forecast(**kwargs):
        assert kwargs["time_zone"] == "Asia/Shanghai"
        return _provider_response()

    monkeypatch.setattr(
        "app.modules.weather.services.weather_service.open_meteo_service.get_forecast",
        get_forecast,
    )
    result = asyncio.run(WeatherService().get_weather())

    assert result.available is True
    assert result.location.location_name == "Test Home"
    assert result.current.condition == "partly_cloudy"
    assert result.current.temperature_c == 28.3
    assert result.current.shortwave_radiation_w_m2 == 510.0
    assert len(result.hourly) == 2
    assert result.observed_at is not None
    assert "latitude" not in result.model_dump()
    assert "longitude" not in result.model_dump()


def test_weather_timeout_is_structured(monkeypatch):
    _patch_config(monkeypatch)

    async def get_forecast(**kwargs):
        raise httpx.ReadTimeout("provider timeout")

    monkeypatch.setattr(
        "app.modules.weather.services.weather_service.open_meteo_service.get_forecast",
        get_forecast,
    )
    result = asyncio.run(WeatherService().get_weather())

    assert result.available is False
    assert result.error_code == "WEATHER_PROVIDER_TIMEOUT"
    assert result.current is None
    assert result.observed_at is None


def test_weather_missing_home_coordinates_is_structured(monkeypatch):
    async def get_config():
        raise HomeAssistantConfigInvalidError("missing coordinates")

    monkeypatch.setattr(
        "app.modules.weather.services.weather_service.home_assistant_service.get_config",
        get_config,
    )
    result = asyncio.run(WeatherService().get_weather())

    assert result.available is False
    assert result.error_code == "HOME_LOCATION_UNAVAILABLE"
    assert result.location is None


def test_weather_cache_hit_and_expiry(monkeypatch):
    _patch_config(monkeypatch)
    calls = 0

    async def get_forecast(**kwargs):
        nonlocal calls
        calls += 1
        return _provider_response()

    monkeypatch.setattr(
        "app.modules.weather.services.weather_service.open_meteo_service.get_forecast",
        get_forecast,
    )
    service = WeatherService()

    async def scenario():
        first = await service.get_weather()
        second = await service.get_weather()
        assert first is second
        assert calls == 1

        service._cache_expires_at = 0.0
        third = await service.get_weather()
        assert third.available is True
        assert calls == 2

    asyncio.run(scenario())


def test_weather_missing_provider_field_is_none_not_zero(monkeypatch):
    _patch_config(monkeypatch)
    raw = _provider_response()
    del raw["current"]["cloud_cover"]
    del raw["hourly"]["direct_normal_irradiance"]

    async def get_forecast(**kwargs):
        return raw

    monkeypatch.setattr(
        "app.modules.weather.services.weather_service.open_meteo_service.get_forecast",
        get_forecast,
    )
    result = asyncio.run(WeatherService().get_weather())

    assert result.available is True
    assert result.current.cloud_cover_percent is None
    assert result.hourly[0].direct_normal_irradiance_w_m2 is None
