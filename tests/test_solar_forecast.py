from datetime import datetime, timedelta

from app.modules.energy_state.schemas.energy_state import (
    EnergyPowerStateSchema,
    EnergyStateResponseSchema,
    EnergyStorageStateSchema,
)
from app.modules.solar_forecast.schemas.solar_forecast import SolarForecastConfidence
from app.modules.solar_forecast.services.solar_forecast_service import (
    SolarForecastService,
)
from app.modules.weather.schemas.weather import (
    WeatherContextSchema,
    WeatherCurrentSchema,
    WeatherHourlySchema,
)


START = datetime(2026, 9, 19, 12, 0)


def _energy(solar_w: float | None = 1000) -> EnergyStateResponseSchema:
    return EnergyStateResponseSchema(
        available=solar_w is not None,
        online=True,
        power=EnergyPowerStateSchema(solar_w=solar_w),
        storage=EnergyStorageStateSchema(),
    )


def _weather(
    *,
    available: bool = True,
    current_radiation: float | None = 500,
    is_day: bool = True,
    current_cloud: float | None = 20,
    hourly_radiation: list[float | None] | None = None,
    hourly_cloud: list[float | None] | None = None,
) -> WeatherContextSchema:
    radiation = hourly_radiation or [400.0] * 24
    clouds = hourly_cloud or [20.0] * len(radiation)
    return WeatherContextSchema(
        available=available,
        provider="open_meteo",
        current=(
            WeatherCurrentSchema(
                condition="clear",
                is_day=is_day,
                cloud_cover_percent=current_cloud,
                shortwave_radiation_w_m2=current_radiation,
            )
            if available
            else None
        ),
        hourly=[
            WeatherHourlySchema(
                time=START + timedelta(hours=index),
                shortwave_radiation_w_m2=value,
                cloud_cover_percent=clouds[index],
            )
            for index, value in enumerate(radiation)
        ],
    )


def test_normal_daytime_forecast_uses_calibrated_radiation_ratio():
    result = SolarForecastService().forecast_from_context(
        _energy(1000),
        _weather(current_radiation=500, hourly_radiation=[400.0] * 24),
    )

    assert result.available is True
    assert result.calibration_ratio == 2.0
    assert result.forecast[0].solar_power_w == 800.0
    assert result.forecast[0].confidence == SolarForecastConfidence.HIGH


def test_nighttime_radiation_forecasts_physical_zero():
    result = SolarForecastService().forecast_from_context(
        _energy(0),
        _weather(
            current_radiation=0,
            is_day=False,
            hourly_radiation=[0.0] * 24,
        ),
    )

    assert result.available is True
    assert result.calibration_ratio is None
    assert all(point.solar_power_w == 0 for point in result.forecast)
    assert result.summary.next_24h_energy_kwh == 0


def test_nighttime_uses_last_valid_daytime_calibration_for_future_sun():
    service = SolarForecastService()
    service.forecast_from_context(
        _energy(1000),
        _weather(current_radiation=500, hourly_radiation=[500.0] * 24),
    )
    result = service.forecast_from_context(
        _energy(0),
        _weather(
            current_radiation=0,
            is_day=False,
            hourly_radiation=[0.0, 200.0, 500.0] + [0.0] * 21,
        ),
    )

    assert result.calibration_ratio == 2.0
    assert result.calibration_source == "last_valid_daytime_observation"
    assert result.forecast[1].solar_power_w == 400.0
    assert result.forecast[1].confidence == SolarForecastConfidence.LOW


def test_inconsistent_night_runtime_is_low_confidence_reference_not_missing():
    result = SolarForecastService().forecast_from_context(
        _energy(3700),
        _weather(
            current_radiation=0,
            is_day=False,
            hourly_radiation=[0.0, 350.0, 700.0] + [0.0] * 21,
        ),
    )

    assert result.calibration_source == "night_runtime_reference_normalized"
    assert result.forecast[1].solar_power_w == 1850.0
    assert result.forecast[2].solar_power_w == 3700.0
    assert result.forecast[1].confidence == SolarForecastConfidence.LOW
    assert result.summary.next_24h_energy_kwh is not None


def test_weather_unavailable():
    result = SolarForecastService().forecast_from_context(
        _energy(),
        _weather(available=False),
    )

    assert result.available is False
    assert result.error_code == "WEATHER_UNAVAILABLE"


def test_solar_runtime_unavailable():
    result = SolarForecastService().forecast_from_context(
        _energy(None),
        _weather(),
    )

    assert result.available is False
    assert result.error_code == "SOLAR_RUNTIME_UNAVAILABLE"


def test_low_current_radiation_does_not_create_extreme_ratio():
    result = SolarForecastService().forecast_from_context(
        _energy(1000),
        _weather(current_radiation=10, hourly_radiation=[500.0] * 24),
    )

    assert result.available is True
    assert result.calibration_ratio is None
    assert result.forecast[0].solar_power_w is None
    assert result.forecast[0].confidence == SolarForecastConfidence.LOW
    assert result.summary.next_1h_energy_kwh is None


def test_missing_hourly_radiation_remains_unavailable_not_zero():
    result = SolarForecastService().forecast_from_context(
        _energy(),
        _weather(hourly_radiation=[None] + [400.0] * 23),
    )

    assert result.forecast[0].solar_power_w is None
    assert result.forecast[0].confidence == SolarForecastConfidence.UNAVAILABLE
    assert result.summary.next_1h_energy_kwh is None


def test_hourly_summary_uses_discrete_energy_approximation():
    result = SolarForecastService().forecast_from_context(
        _energy(200),
        _weather(current_radiation=100, hourly_radiation=[100.0] * 24),
    )

    assert result.summary.next_1h_energy_kwh == 0.2
    assert result.summary.next_3h_energy_kwh == 0.6
    assert result.summary.next_6h_energy_kwh == 1.2
    assert result.summary.next_24h_energy_kwh == 4.8
    assert result.summary.peak_power_w == 200
    assert result.summary.peak_time == START


def test_confidence_reflects_calibration_and_cloud_cover():
    high = SolarForecastService().forecast_from_context(
        _energy(),
        _weather(
            current_radiation=500,
            current_cloud=20,
            hourly_cloud=[85.0] + [20.0] * 23,
        ),
    )
    medium = SolarForecastService().forecast_from_context(
        _energy(),
        _weather(current_radiation=50),
    )

    assert high.forecast[0].confidence == SolarForecastConfidence.MEDIUM
    assert high.forecast[1].confidence == SolarForecastConfidence.HIGH
    assert medium.forecast[0].confidence == SolarForecastConfidence.MEDIUM
