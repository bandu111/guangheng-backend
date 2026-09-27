from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.modules.home_assistant.schemas.home_assistant import HomeAssistantHistoryStateSchema
from app.modules.report.schemas.energy_report import EnergyReportTariffSourceSchema
from app.modules.report.services.energy_report_service import EnergyReportService


OBSERVED_AT = datetime(2026, 9, 20, 4, 0, tzinfo=timezone.utc)
LOCAL_START = datetime(2026, 9, 20, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc)


def _history(value: float) -> list[HomeAssistantHistoryStateSchema]:
    return [HomeAssistantHistoryStateSchema(state=str(value), last_updated=LOCAL_START.isoformat())]


def _tariff() -> EnergyReportTariffSourceSchema:
    return EnergyReportTariffSourceSchema(
        price_per_kwh=0.54,
        currency="CNY",
        provider="NDRC",
        pricing_type="reference_average",
        realtime=False,
        reference_date="2019-08-23",
    )


def test_report_uses_recorder_energy_for_cost_savings_and_carbon():
    result = EnergyReportService.from_histories(
        histories={
            "solar": _history(1000),
            "home": _history(2000),
            "grid_import": _history(500),
            "grid_export": _history(100),
        },
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
        tariff_price_per_kwh=0.54,
        tariff_source=_tariff(),
        policy=EnergyReportService.load_policy(),
    )

    metrics = result.periods["today"].metrics
    assert result.available is True
    assert metrics.generation_kwh == 12
    assert metrics.consumption_kwh == 24
    assert metrics.grid_import_kwh == 6
    assert metrics.grid_export_kwh == 1.2
    assert metrics.solar_self_consumption_kwh == 10.8
    assert metrics.solar_self_use_percent == 90
    assert metrics.reference_baseline_cost_cny == 12.96
    assert metrics.actual_grid_cost_cny == 3.24
    assert metrics.savings_cny == 9.72
    assert metrics.savings_percent == 75
    assert metrics.carbon_reduction_kg == 10.97
    assert len(result.periods["today"].daily) == 1
    assert result.periods["today"].daily[0].actual_grid_cost_cny == 3.24
    assert result.tariff is not None and result.tariff.realtime is False
    assert result.carbon is not None and result.carbon.factor_kg_co2_per_kwh == 0.6096


def test_report_does_not_turn_missing_history_into_zero():
    result = EnergyReportService.from_histories(
        histories={},
        time_zone="Asia/Shanghai",
        observed_at=OBSERVED_AT,
        tariff_price_per_kwh=0.54,
        tariff_source=_tariff(),
        policy=EnergyReportService.load_policy(),
    )

    assert result.available is False
    assert result.periods["today"].metrics.consumption_kwh is None
    assert result.error_code == "INSUFFICIENT_REPORT_HISTORY"
