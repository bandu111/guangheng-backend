from app.core.database import SessionLocal
from app.modules.decision_context.services.decision_context_service import (
    decision_context_service,
)
from app.modules.hermes.mcp.tools.common import failure, success
from app.modules.hermes.schemas.tool import HermesToolResultSchema
from app.modules.load_forecast.services.load_forecast_service import (
    load_forecast_service,
)
from app.modules.solar_forecast.services.solar_forecast_service import (
    solar_forecast_service,
)
from app.modules.strategy.services.strategy_service import strategy_service
from app.modules.tariff.services.tariff_service import tariff_service
from app.modules.weather.services.weather_service import weather_service


async def get_weather() -> HermesToolResultSchema:
    """Read current weather and the normalized 24-hour weather context."""
    try:
        weather = await weather_service.get_weather()
        if not weather.available:
            return failure(
                "get_weather",
                weather.error_code or "WEATHER_UNAVAILABLE",
                "Weather context is unavailable.",
            )
        return success("get_weather", weather)
    except Exception:
        return failure(
            "get_weather",
            "WEATHER_UNAVAILABLE",
            "Weather context could not be read.",
        )


async def get_solar_forecast() -> HermesToolResultSchema:
    """Read the deterministic 24-hour photovoltaic forecast."""
    try:
        with SessionLocal() as db:
            forecast = await solar_forecast_service.get_forecast(db=db)
        if not forecast.available:
            return failure(
                "get_solar_forecast",
                forecast.error_code or "SOLAR_FORECAST_UNAVAILABLE",
                "Solar forecast is unavailable.",
            )
        return success("get_solar_forecast", forecast)
    except Exception:
        return failure(
            "get_solar_forecast",
            "SOLAR_FORECAST_UNAVAILABLE",
            "Solar forecast could not be read.",
        )


async def get_load_forecast() -> HermesToolResultSchema:
    """Read the deterministic 24-hour household load forecast."""
    try:
        with SessionLocal() as db:
            forecast = await load_forecast_service.get_forecast(db=db)
        if not forecast.available:
            return failure(
                "get_load_forecast",
                forecast.error_code or "LOAD_FORECAST_UNAVAILABLE",
                "Load forecast is unavailable.",
            )
        return success("get_load_forecast", forecast)
    except Exception:
        return failure(
            "get_load_forecast",
            "LOAD_FORECAST_UNAVAILABLE",
            "Load forecast could not be read.",
        )


async def get_tariff() -> HermesToolResultSchema:
    """Read the sourced non-realtime residential reference tariff context."""
    try:
        tariff = tariff_service.get_context()
        return success("get_tariff", tariff)
    except Exception:
        return failure(
            "get_tariff",
            "TARIFF_UNAVAILABLE",
            "Reference tariff context could not be read.",
        )


async def get_strategy() -> HermesToolResultSchema:
    """Read the user's current GuangHeng energy strategy."""
    try:
        with SessionLocal() as db:
            strategy = strategy_service.get_current(db)
        return success("get_strategy", strategy)
    except Exception:
        return failure(
            "get_strategy",
            "STRATEGY_UNAVAILABLE",
            "Current strategy could not be read.",
        )


async def get_decision_context() -> HermesToolResultSchema:
    """Read the aggregated energy, forecast, strategy, weather, and tariff context."""
    try:
        with SessionLocal() as db:
            context = await decision_context_service.get_context(db=db)
        if not context.available:
            return failure(
                "get_decision_context",
                context.error_code or "DECISION_CONTEXT_UNAVAILABLE",
                "Decision context is unavailable.",
            )
        return success("get_decision_context", context)
    except Exception:
        return failure(
            "get_decision_context",
            "DECISION_CONTEXT_UNAVAILABLE",
            "Decision context could not be read.",
        )
