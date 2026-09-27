from datetime import datetime, timedelta, timezone

from app.modules.energy_state.schemas.energy_schedule import EnergyScheduleAction
from app.modules.energy_state.services.energy_schedule_service import EnergyScheduleService
from app.modules.load_forecast.schemas.load_forecast import (
    LoadForecastConfidence,
    LoadForecastPointSchema,
    LoadForecastResponseSchema,
    LoadForecastSummarySchema,
)
from app.modules.solar_forecast.schemas.solar_forecast import (
    SolarForecastConfidence,
    SolarForecastPointSchema,
    SolarForecastResponseSchema,
    SolarForecastSummarySchema,
)


OBSERVED_AT = datetime(2026, 9, 20, 4, 0, tzinfo=timezone.utc)


def _solar(values: list[float | None]) -> SolarForecastResponseSchema:
    return SolarForecastResponseSchema(
        available=True,
        method="weather_calibrated_v1",
        forecast=[
            SolarForecastPointSchema(
                time=OBSERVED_AT + timedelta(hours=index),
                solar_power_w=value,
                confidence=SolarForecastConfidence.MEDIUM,
            )
            for index, value in enumerate(values)
        ],
        summary=SolarForecastSummarySchema(),
    )


def _load(values: list[float | None]) -> LoadForecastResponseSchema:
    return LoadForecastResponseSchema(
        available=True,
        method="historical_hourly_median_v1",
        history_days_requested=7,
        history_samples=24,
        forecast=[
            LoadForecastPointSchema(
                time=OBSERVED_AT + timedelta(hours=index),
                load_power_w=value,
                historical_samples=7,
                confidence=LoadForecastConfidence.HIGH,
            )
            for index, value in enumerate(values)
        ],
        summary=LoadForecastSummarySchema(),
    )


def test_schedule_is_forecast_based_and_advisory_only():
    result = EnergyScheduleService.from_forecasts(
        solar=_solar([0, 1000, 3000]),
        load=_load([1000, 1500, 1000]),
        strategy="BACKUP",
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
    )

    assert result.available is True
    assert [point.action for point in result.points] == [
        EnergyScheduleAction.PRESERVE_RESERVE,
        EnergyScheduleAction.SOLAR_ASSIST,
        EnergyScheduleAction.STORE_SURPLUS,
    ]
    assert result.summary.projected_solar_kwh == 4
    assert result.summary.projected_load_kwh == 3.5
    assert result.summary.projected_surplus_kwh == 2
    assert result.summary.projected_deficit_kwh == 1.5
    assert result.source.advisory_only is True
    assert result.source.executable is False


def test_schedule_marks_missing_forecast_values_unavailable():
    result = EnergyScheduleService.from_forecasts(
        solar=_solar([None]),
        load=_load([1000]),
        strategy="AUTO",
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
    )

    assert result.available is False
    assert result.points[0].action == EnergyScheduleAction.UNAVAILABLE
    assert result.error_code == "INSUFFICIENT_FORECAST_DATA"
