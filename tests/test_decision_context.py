import asyncio
from datetime import datetime, timezone

from app.modules.decision_context.services.decision_context_service import (
    DecisionContextService,
)
from app.modules.energy_state.schemas.energy_balance import (
    EnergyBalanceResponseSchema,
    EnergySinkPowerSchema,
    EnergySourcePowerSchema,
)
from app.modules.energy_state.schemas.energy_state import (
    EnergyPowerStateSchema,
    EnergyStateResponseSchema,
    EnergyStorageStateSchema,
)
from app.modules.load_forecast.schemas.load_forecast import (
    LoadForecastResponseSchema,
    LoadForecastSummarySchema,
)
from app.modules.strategy.models.strategy import StrategyMode
from app.modules.strategy.schemas.strategy import StrategyResponseSchema
from app.modules.weather.schemas.weather import (
    WeatherContextSchema,
    WeatherCurrentSchema,
    WeatherHourlySchema,
)


def _energy() -> EnergyStateResponseSchema:
    return EnergyStateResponseSchema(
        available=True,
        online=True,
        power=EnergyPowerStateSchema(solar_w=1000, home_load_w=800),
        storage=EnergyStorageStateSchema(soc_percent=70),
    )


def _balance() -> EnergyBalanceResponseSchema:
    return EnergyBalanceResponseSchema(
        available=True,
        online=True,
        sources=EnergySourcePowerSchema(solar_w=1000, total_w=1000),
        sinks=EnergySinkPowerSchema(home_load_w=1000, total_w=1000),
        balance_error_w=0,
        balanced=True,
    )


def _strategy() -> StrategyResponseSchema:
    now = datetime.now(timezone.utc)
    return StrategyResponseSchema(
        id=1,
        mode=StrategyMode.AUTO,
        backup_reserve_target=25,
        created_at=now,
        updated_at=now,
    )


def _patch_energy(monkeypatch):
    async def get_energy_state(*, db):
        return _energy()

    async def get_energy_balance(*, db):
        return _balance()

    def get_current(db):
        return _strategy()

    async def get_load_forecast(*, db):
        return LoadForecastResponseSchema(
            available=True,
            method="test_history_median",
            history_days_requested=7,
            history_samples=7,
            current_load_w=800,
            summary=LoadForecastSummarySchema(next_1h_energy_kwh=0.8),
            observed_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(
        "app.modules.decision_context.services.decision_context_service.energy_state_service.get_energy_state",
        get_energy_state,
    )
    monkeypatch.setattr(
        "app.modules.decision_context.services.decision_context_service.energy_balance_service.get_energy_balance",
        get_energy_balance,
    )
    monkeypatch.setattr(
        "app.modules.decision_context.services.decision_context_service.strategy_service.get_current",
        get_current,
    )
    monkeypatch.setattr(
        "app.modules.decision_context.services.decision_context_service.load_forecast_service.get_forecast",
        get_load_forecast,
    )


def test_decision_context_with_weather(monkeypatch):
    _patch_energy(monkeypatch)

    async def get_weather():
        return WeatherContextSchema(
            available=True,
            provider="open_meteo",
            observed_at=datetime.now(timezone.utc),
            current=WeatherCurrentSchema(
                condition="clear",
                is_day=True,
                shortwave_radiation_w_m2=500,
            ),
            hourly=[
                WeatherHourlySchema(
                    time=datetime.now(timezone.utc),
                    shortwave_radiation_w_m2=400,
                )
            ],
        )

    monkeypatch.setattr(
        "app.modules.decision_context.services.decision_context_service.weather_service.get_weather",
        get_weather,
    )
    result = asyncio.run(DecisionContextService().get_context(db=object()))

    assert result.available is True
    assert result.energy.available is True
    assert result.balance.balanced is True
    assert result.strategy.mode == StrategyMode.AUTO
    assert result.weather.available is True
    assert result.solar_forecast.available is True
    assert result.solar_forecast.forecast[0].solar_power_w == 800
    assert result.tariff.available is True
    assert result.tariff.source.pricing_type == "reference_average"
    assert result.tariff.source.realtime is False
    assert result.load_forecast.available is True


def test_decision_context_survives_weather_unavailable(monkeypatch):
    _patch_energy(monkeypatch)

    async def get_weather():
        return WeatherContextSchema(
            available=False,
            provider="open_meteo",
            error_code="WEATHER_PROVIDER_TIMEOUT",
        )

    monkeypatch.setattr(
        "app.modules.decision_context.services.decision_context_service.weather_service.get_weather",
        get_weather,
    )
    result = asyncio.run(DecisionContextService().get_context(db=object()))

    assert result.available is True
    assert result.weather.available is False
    assert result.weather.error_code == "WEATHER_PROVIDER_TIMEOUT"
    assert result.solar_forecast.available is False
    assert result.solar_forecast.error_code == "WEATHER_UNAVAILABLE"
    assert result.tariff.available is True
    assert result.load_forecast.available is True


def test_decision_context_survives_load_forecast_failure(monkeypatch):
    _patch_energy(monkeypatch)

    async def get_weather():
        return WeatherContextSchema(available=False, provider="open_meteo")

    async def get_load_forecast(*, db):
        return LoadForecastResponseSchema(
            available=False,
            method="historical_hour_slot_median_with_current_calibration_v1",
            history_days_requested=7,
            history_samples=0,
            summary=LoadForecastSummarySchema(),
            error_code="HISTORY_PROVIDER_UNAVAILABLE",
        )

    monkeypatch.setattr(
        "app.modules.decision_context.services.decision_context_service.weather_service.get_weather",
        get_weather,
    )
    monkeypatch.setattr(
        "app.modules.decision_context.services.decision_context_service.load_forecast_service.get_forecast",
        get_load_forecast,
    )
    result = asyncio.run(DecisionContextService().get_context(db=object()))

    assert result.available is True
    assert result.load_forecast.available is False
    assert result.load_forecast.error_code == "HISTORY_PROVIDER_UNAVAILABLE"


def test_decision_context_energy_unavailable_is_structured(monkeypatch):
    async def get_energy_state(*, db):
        energy = _energy()
        energy.available = False
        return energy

    async def get_weather():
        return WeatherContextSchema(available=False, provider="open_meteo")

    monkeypatch.setattr(
        "app.modules.decision_context.services.decision_context_service.energy_state_service.get_energy_state",
        get_energy_state,
    )
    monkeypatch.setattr(
        "app.modules.decision_context.services.decision_context_service.weather_service.get_weather",
        get_weather,
    )
    result = asyncio.run(DecisionContextService().get_context(db=object()))

    assert result.available is False
    assert result.error_code == "ENERGY_STATE_UNAVAILABLE"
