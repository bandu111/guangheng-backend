from fastapi import APIRouter

from app.modules.device_registry.routers.device_registry import (
    router as device_registry_router,
)
from app.modules.home_assistant.routers.home_assistant import (
    router as home_assistant_router,
)

from app.modules.energy_state.routers.energy_state import (
    router as energy_state_router,
)
from app.modules.execution.routers.execution import (
    router as execution_router,
)
from app.modules.proposal.routers.proposal import (
    router as proposal_router,
)
from app.modules.strategy.routers.strategy import (
    router as strategy_router,
)
from app.modules.weather.routers.weather import router as weather_router
from app.modules.decision_context.routers.decision_context import (
    router as decision_context_router,
)
from app.modules.solar_forecast.routers.solar_forecast import (
    router as solar_forecast_router,
)
from app.modules.tariff.routers.tariff import router as tariff_router
from app.modules.load_forecast.routers.load_forecast import (
    router as load_forecast_router,
)
from app.modules.optimizer.routers.optimizer import router as optimizer_router
from app.modules.hermes.routers.hermes import router as hermes_router
from app.modules.autonomy.routers.autonomy import router as autonomy_router
from app.modules.report.routers.energy_report import router as energy_report_router
from app.modules.station.routers.station import router as station_router
from app.modules.critical_load.routers.critical_load import router as critical_load_router
from app.modules.system_health.routers.system_health import router as system_health_router
from app.modules.area_energy.routers.area_energy import router as area_energy_router
from app.modules.solar_array.routers.solar_array import router as solar_array_router
from app.modules.household_graph.routers.household_graph import (
    router as household_graph_router,
)
from app.modules.action_set.routers.action_set import router as action_set_router
from app.modules.companion.routers.companion import router as companion_router
from app.modules.voice.routers.voice import router as voice_router

api_v1_router = APIRouter()


api_v1_router.include_router(
    home_assistant_router,
)

api_v1_router.include_router(
    device_registry_router,
)

api_v1_router.include_router(
    energy_state_router,
)

api_v1_router.include_router(
    strategy_router,
)

api_v1_router.include_router(
    proposal_router,
)

api_v1_router.include_router(
    execution_router,
)

api_v1_router.include_router(
    weather_router,
)

api_v1_router.include_router(
    decision_context_router,
)

api_v1_router.include_router(
    solar_forecast_router,
)

api_v1_router.include_router(
    tariff_router,
)

api_v1_router.include_router(
    load_forecast_router,
)

api_v1_router.include_router(
    optimizer_router,
)

api_v1_router.include_router(
    hermes_router,
)

api_v1_router.include_router(
    autonomy_router,
)

api_v1_router.include_router(
    energy_report_router,
)

api_v1_router.include_router(
    station_router,
)

api_v1_router.include_router(
    critical_load_router,
)

api_v1_router.include_router(
    system_health_router,
)

api_v1_router.include_router(
    area_energy_router,
)

api_v1_router.include_router(
    solar_array_router,
)

api_v1_router.include_router(
    household_graph_router,
)

api_v1_router.include_router(
    action_set_router,
)

api_v1_router.include_router(
    companion_router,
)

api_v1_router.include_router(
    voice_router,
)
