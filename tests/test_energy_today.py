from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.modules.energy_state.services.energy_today_service import EnergyTodayService
from app.modules.home_assistant.schemas.home_assistant import HomeAssistantHistoryStateSchema


OBSERVED_AT = datetime(2026, 9, 20, 4, 0, tzinfo=timezone.utc)
LOCAL_ZONE = ZoneInfo("Asia/Shanghai")
TODAY_START = datetime(2026, 9, 20, 0, 0, tzinfo=LOCAL_ZONE).astimezone(timezone.utc)
PREVIOUS_START = TODAY_START - timedelta(days=1)


def _item(at: datetime, value: str | float) -> HomeAssistantHistoryStateSchema:
    return HomeAssistantHistoryStateSchema(state=str(value), last_updated=at.isoformat())


def _history(previous_value: float, today_value: float):
    return [_item(PREVIOUS_START, previous_value), _item(TODAY_START, today_value)]


def test_today_totals_savings_hourly_flow_and_comparison():
    result = EnergyTodayService.from_histories(
        histories={
            "solar": _history(500, 1000),
            "home": _history(1500, 2000),
            "grid": _history(500, 500),
        },
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
        tariff_price_per_kwh=0.54,
    )

    assert result.available is True
    assert result.date.isoformat() == "2026-09-20"
    assert result.summary.generation_kwh == 12
    assert result.summary.consumption_kwh == 24
    assert result.summary.grid_import_kwh == 6
    assert result.summary.avoided_grid_kwh == 18
    assert result.summary.savings_cny == 9.72
    assert result.summary.generation_change_percent == 100
    assert result.summary.consumption_change_percent == 33.3
    assert result.summary.savings_change_percent == 50
    assert len(result.flow) == 12
    assert all(point.solar_power_w == 1000 for point in result.flow)
    assert all(point.home_load_w == 2000 for point in result.flow)
    assert result.source.coverage_percent == 100


def test_today_boundary_uses_household_timezone_not_utc_date():
    observed = datetime(2026, 9, 19, 17, 30, tzinfo=timezone.utc)
    local_start = datetime(2026, 9, 20, 0, 0, tzinfo=LOCAL_ZONE).astimezone(timezone.utc)
    result = EnergyTodayService.from_histories(
        histories={
            "solar": [_item(local_start, 2000)],
            "home": [_item(local_start, 1000)],
            "grid": [_item(local_start, 0)],
        },
        time_zone="Asia/Shanghai",
        observed_at=observed,
        tariff_price_per_kwh=0.54,
    )
    assert result.date.isoformat() == "2026-09-20"
    assert result.summary.generation_kwh == 3
    assert result.summary.consumption_kwh == 1.5


def test_invalid_states_are_not_converted_to_zero():
    invalid = [_item(TODAY_START, "unavailable"), _item(TODAY_START + timedelta(hours=1), "not-a-number")]
    result = EnergyTodayService.from_histories(
        histories={"solar": invalid, "home": invalid, "grid": invalid},
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
        tariff_price_per_kwh=0.54,
    )
    assert result.available is False
    assert result.summary.generation_kwh is None
    assert result.summary.consumption_kwh is None
    assert result.error_code == "INSUFFICIENT_ENERGY_HISTORY"


def test_savings_requires_grid_history_but_energy_totals_remain_available():
    result = EnergyTodayService.from_histories(
        histories={
            "solar": [_item(TODAY_START, 1000)],
            "home": [_item(TODAY_START, 2000)],
        },
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
        tariff_price_per_kwh=0.54,
    )
    assert result.available is True
    assert result.summary.generation_kwh == 12
    assert result.summary.consumption_kwh == 24
    assert result.summary.grid_import_kwh is None
    assert result.summary.savings_cny is None


def test_stale_sample_is_not_stretched_across_the_whole_day():
    result = EnergyTodayService.from_histories(
        histories={
            "solar": [_item(TODAY_START, 1000)],
            "home": [_item(TODAY_START, 2000)],
            "grid": [_item(TODAY_START, 500)],
        },
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
        tariff_price_per_kwh=0.54,
        max_hold_seconds=900,
    )

    assert result.summary.generation_kwh == 0.25
    assert result.summary.consumption_kwh == 0.5
    assert result.source.coverage_percent == 2.1
    assert result.flow[0].coverage_percent == 25
