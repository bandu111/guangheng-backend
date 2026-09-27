import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from app.modules.energy_state.schemas.energy_state import (
    EnergyPowerStateSchema,
    EnergyStateResponseSchema,
    EnergyStorageStateSchema,
)
from app.modules.home_assistant.schemas.home_assistant import (
    HomeAssistantConfigSchema,
    HomeAssistantHistoryStateSchema,
)
from app.modules.load_forecast.schemas.load_forecast import LoadForecastConfidence
from app.modules.load_forecast.services.load_forecast_service import (
    LoadForecastService,
)


OBSERVED_AT = datetime(2026, 9, 20, 4, 30, tzinfo=timezone.utc)


def _history_item(time: datetime, state: str | float) -> HomeAssistantHistoryStateSchema:
    return HomeAssistantHistoryStateSchema(
        entity_id="sensor.from_capability_matrix",
        state=str(state),
        last_updated=time.isoformat(),
    )


def _seven_days(value_for_hour=None) -> list[HomeAssistantHistoryStateSchema]:
    start = OBSERVED_AT - timedelta(days=7, minutes=30)
    items = []
    for index in range(24 * 7):
        time = start + timedelta(hours=index)
        local_hour = time.astimezone(timezone(timedelta(hours=8))).hour
        value = value_for_hour(local_hour, index // 24) if value_for_hour else 1000
        items.append(_history_item(time, value))
    return items


def test_normal_seven_day_history_forecast_and_confidence():
    result = LoadForecastService().forecast_from_history(
        history=_seven_days(lambda hour, day: 1000 + hour * 10),
        current_load_w=1120,
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
    )
    assert result.available is True
    assert len(result.forecast) == 24
    assert result.forecast[0].time.utcoffset() == timedelta(hours=8)
    assert result.forecast[0].historical_samples == 7
    assert result.forecast[0].confidence == LoadForecastConfidence.HIGH


def test_short_history_has_low_confidence():
    result = LoadForecastService().forecast_from_history(
        history=_seven_days()[-48:],
        current_load_w=1000,
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
    )
    assert result.available is True
    assert all(
        point.confidence == LoadForecastConfidence.LOW
        for point in result.forecast
    )


def test_no_history_is_unavailable():
    result = LoadForecastService().forecast_from_history(
        history=[],
        current_load_w=1000,
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
    )
    assert result.available is False
    assert result.error_code == "INSUFFICIENT_LOAD_HISTORY"


def test_invalid_history_states_are_ignored_not_converted_to_zero():
    invalid = ["unknown", "unavailable", "none", "", "not-a-number", "-10"]
    history = [
        _history_item(OBSERVED_AT - timedelta(hours=index + 1), value)
        for index, value in enumerate(invalid)
    ]
    result = LoadForecastService().forecast_from_history(
        history=history,
        current_load_w=1000,
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
    )
    assert result.available is False
    assert result.history_samples == 0
    assert result.error_code == "INSUFFICIENT_LOAD_HISTORY"


def test_utc_history_is_grouped_by_household_local_hour():
    history = [
        _history_item(datetime(2026, 9, 19, 5, tzinfo=timezone.utc), 1300)
    ]
    result = LoadForecastService().forecast_from_history(
        history=history,
        current_load_w=1300,
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
    )
    point_at_13 = next(point for point in result.forecast if point.time.hour == 13)
    assert point_at_13.load_power_w == 1300
    assert point_at_13.historical_samples == 1


def test_median_rejects_single_load_spike():
    def values(hour, day):
        if hour == 13 and day == 6:
            return 20000
        return 1000

    result = LoadForecastService().forecast_from_history(
        history=_seven_days(values),
        current_load_w=1000,
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
    )
    assert result.forecast[0].time.hour == 13
    assert result.forecast[0].load_power_w == 1000


def test_confidence_thresholds():
    service = LoadForecastService()
    assert service._confidence(5) == LoadForecastConfidence.HIGH
    assert service._confidence(3) == LoadForecastConfidence.MEDIUM
    assert service._confidence(2) == LoadForecastConfidence.LOW
    assert service._confidence(0) == LoadForecastConfidence.UNAVAILABLE


def test_summary_and_peak_use_hourly_discrete_approximation():
    result = LoadForecastService().forecast_from_history(
        history=_seven_days(),
        current_load_w=1000,
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
    )
    assert result.summary.next_1h_energy_kwh == 1
    assert result.summary.next_3h_energy_kwh == 3
    assert result.summary.next_6h_energy_kwh == 6
    assert result.summary.next_24h_energy_kwh == 24
    assert result.summary.peak_power_w == 1000
    assert result.summary.peak_time == result.forecast[0].time


def test_current_load_calibration_decays_after_three_hours():
    result = LoadForecastService().forecast_from_history(
        history=_seven_days(),
        current_load_w=1600,
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
    )
    assert [point.load_power_w for point in result.forecast[:4]] == [
        1360,
        1210,
        1090,
        1000,
    ]


def test_history_provider_failure_is_structured(monkeypatch):
    service = LoadForecastService()

    async def get_energy_state(*, db):
        return EnergyStateResponseSchema(
            available=True,
            online=True,
            power=EnergyPowerStateSchema(home_load_w=1000),
            storage=EnergyStorageStateSchema(),
        )

    async def get_config():
        return HomeAssistantConfigSchema(
            latitude=1,
            longitude=1,
            time_zone="Asia/Shanghai",
        )

    async def get_history(**kwargs):
        raise httpx.ConnectError("history unavailable")

    monkeypatch.setattr(service, "_home_load_entity_id", lambda: "sensor.matrix")
    monkeypatch.setattr(
        "app.modules.load_forecast.services.load_forecast_service.energy_state_service.get_energy_state",
        get_energy_state,
    )
    monkeypatch.setattr(
        "app.modules.load_forecast.services.load_forecast_service.home_assistant_service.get_config",
        get_config,
    )
    monkeypatch.setattr(
        "app.modules.load_forecast.services.load_forecast_service.home_assistant_service.get_history",
        get_history,
    )
    result = asyncio.run(service.get_forecast(db=object()))
    assert result.available is False
    assert result.error_code == "HISTORY_PROVIDER_UNAVAILABLE"


def test_missing_capability_and_current_runtime_are_structured(monkeypatch):
    service = LoadForecastService()
    monkeypatch.setattr(service, "_home_load_entity_id", lambda: None)
    missing_capability = asyncio.run(service.get_forecast(db=object()))
    assert missing_capability.error_code == "HOME_LOAD_CAPABILITY_NOT_FOUND"

    monkeypatch.setattr(service, "_home_load_entity_id", lambda: "sensor.matrix")

    async def get_energy_state(*, db):
        return EnergyStateResponseSchema(
            available=False,
            online=False,
            power=EnergyPowerStateSchema(),
            storage=EnergyStorageStateSchema(),
        )

    monkeypatch.setattr(
        "app.modules.load_forecast.services.load_forecast_service.energy_state_service.get_energy_state",
        get_energy_state,
    )
    missing_runtime = asyncio.run(service.get_forecast(db=object()))
    assert missing_runtime.error_code == "CURRENT_LOAD_UNAVAILABLE"
