from datetime import datetime

from pydantic import BaseModel

from app.modules.energy_state.schemas.energy_balance import EnergyBalanceResponseSchema
from app.modules.energy_state.schemas.energy_state import EnergyStateResponseSchema
from app.modules.strategy.schemas.strategy import StrategyResponseSchema
from app.modules.tariff.schemas.tariff import TariffContextSchema
from app.modules.load_forecast.schemas.load_forecast import (
    LoadForecastResponseSchema,
)
from app.modules.solar_forecast.schemas.solar_forecast import (
    SolarForecastResponseSchema,
)
from app.modules.weather.schemas.weather import WeatherContextSchema
from app.modules.household_graph.schemas.household_graph import HouseholdEnergyGraphSchema


class DecisionContextSchema(BaseModel):
    available: bool
    observed_at: datetime
    energy: EnergyStateResponseSchema | None = None
    balance: EnergyBalanceResponseSchema | None = None
    strategy: StrategyResponseSchema | None = None
    weather: WeatherContextSchema
    solar_forecast: SolarForecastResponseSchema
    load_forecast: LoadForecastResponseSchema
    tariff: TariffContextSchema | None = None
    household_graph: HouseholdEnergyGraphSchema | None = None
    error_code: str | None = None
    error_message: str | None = None
