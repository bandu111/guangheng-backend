from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.modules.decision_context.schemas.decision_context import DecisionContextSchema
from app.modules.energy_state.services.energy_balance_service import energy_balance_service
from app.modules.energy_state.services.energy_state_service import energy_state_service
from app.modules.load_forecast.schemas.load_forecast import (
    LoadForecastResponseSchema,
    LoadForecastSummarySchema,
)
from app.modules.load_forecast.services.load_forecast_service import (
    load_forecast_service,
)
from app.modules.solar_forecast.schemas.solar_forecast import (
    SolarForecastResponseSchema,
    SolarForecastSummarySchema,
)
from app.modules.solar_forecast.services.solar_forecast_service import (
    solar_forecast_service,
)
from app.modules.strategy.services.strategy_service import strategy_service
from app.modules.tariff.services.tariff_service import tariff_service
from app.modules.weather.schemas.weather import WeatherContextSchema
from app.modules.weather.services.weather_service import weather_service
from app.modules.household_graph.services.household_graph_service import household_graph_service


class DecisionContextService:
    @staticmethod
    def _weather_fallback() -> WeatherContextSchema:
        return WeatherContextSchema(
            available=False,
            provider="unknown",
            error_code="WEATHER_CONTEXT_UNAVAILABLE",
            error_message="Weather context could not be assembled.",
        )

    @staticmethod
    def _solar_forecast_fallback() -> SolarForecastResponseSchema:
        return SolarForecastResponseSchema(
            available=False,
            method=solar_forecast_service.METHOD,
            summary=SolarForecastSummarySchema(),
            error_code="SOLAR_FORECAST_UNAVAILABLE",
        )

    @staticmethod
    def _load_forecast_fallback() -> LoadForecastResponseSchema:
        return LoadForecastResponseSchema(
            available=False,
            method=load_forecast_service.METHOD,
            history_days_requested=load_forecast_service.HISTORY_DAYS,
            history_samples=0,
            summary=LoadForecastSummarySchema(),
            error_code="LOAD_FORECAST_UNAVAILABLE",
        )

    async def get_context(self, db: Session) -> DecisionContextSchema:
        try:
            household_graph = await household_graph_service.get_current()
        except Exception:
            household_graph = None
        try:
            tariff = tariff_service.get_context()
        except Exception:
            tariff = None

        try:
            load_forecast = await load_forecast_service.get_forecast(db=db)
        except Exception:
            load_forecast = self._load_forecast_fallback()

        try:
            weather = await weather_service.get_weather()
        except Exception:
            weather = self._weather_fallback()

        observed_at = datetime.now(timezone.utc)
        solar_forecast = self._solar_forecast_fallback()
        try:
            energy = await energy_state_service.get_energy_state(db=db)
            try:
                solar_forecast = solar_forecast_service.forecast_from_context(
                    energy,
                    weather,
                )
            except Exception:
                solar_forecast = self._solar_forecast_fallback()

            if not energy.available:
                return DecisionContextSchema(
                    available=False,
                    observed_at=observed_at,
                    energy=energy,
                    weather=weather,
                    solar_forecast=solar_forecast,
                    load_forecast=load_forecast,
                    tariff=tariff,
                    household_graph=household_graph,
                    error_code="ENERGY_STATE_UNAVAILABLE",
                    error_message="Current energy state is unavailable.",
                )

            balance = await energy_balance_service.get_energy_balance(db=db)
            if not balance.available:
                return DecisionContextSchema(
                    available=False,
                    observed_at=observed_at,
                    energy=energy,
                    balance=balance,
                    weather=weather,
                    solar_forecast=solar_forecast,
                    load_forecast=load_forecast,
                    tariff=tariff,
                    household_graph=household_graph,
                    error_code="ENERGY_BALANCE_UNAVAILABLE",
                    error_message="Current energy balance is unavailable.",
                )

            strategy = strategy_service.get_current(db)
        except Exception:
            return DecisionContextSchema(
                available=False,
                observed_at=observed_at,
                weather=weather,
                solar_forecast=solar_forecast,
                load_forecast=load_forecast,
                tariff=tariff,
                household_graph=household_graph,
                error_code="ENERGY_CONTEXT_UNAVAILABLE",
                error_message="Energy decision context could not be assembled.",
            )

        return DecisionContextSchema(
            available=True,
            observed_at=observed_at,
            energy=energy,
            balance=balance,
            strategy=strategy,
            weather=weather,
            solar_forecast=solar_forecast,
            load_forecast=load_forecast,
            tariff=tariff,
            household_graph=household_graph,
        )


decision_context_service = DecisionContextService()
