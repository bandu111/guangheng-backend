import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import Base, engine
from app.modules.device_registry.models.device import Device
from app.modules.execution.models.execution import Execution
from app.modules.hermes.models.agent_conversation import (
    AgentMessage,
    AgentSession,
    AgentToolCall,
)
from app.modules.proposal.models.proposal import Proposal
from app.modules.strategy.models.strategy import StrategyConfig
from app.modules.autonomy.models.autonomous_decision_run import AutonomousDecisionRun
from app.modules.autonomy.models.notification_event import NotificationEvent
from app.modules.autonomy.models.autonomy_config import AutonomyConfig
from app.modules.autonomy.services.scheduler_service import scheduler_service
from app.modules.energy_state.models.energy_observation import EnergyObservation
from app.modules.critical_load.models.critical_load import CriticalLoad
from app.modules.action_set.models.action_set import ActionSet, ActionSetItem
from app.modules.companion.models.companion import (
    CompanionApprovalChallenge,
    CompanionDevice,
    CompanionPairingSession,
)
from app.modules.voice.models.voice_session import VoiceSession
from app.modules.energy_state.services.energy_observation_scheduler import (
    energy_observation_scheduler,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler_service.start()
    energy_observation_scheduler.start()
    try:
        yield
    finally:
        await energy_observation_scheduler.stop()
        await scheduler_service.stop()

Base.metadata.create_all(bind=engine)
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="光衡 Autonomous Energy Agent 后端服务",
    lifespan=lifespan,
)


app.include_router(
    api_v1_router,
    prefix="/api/v1",
)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "energy_observer": {
            "enabled": energy_observation_scheduler.policy.enabled,
            "running": energy_observation_scheduler.started,
            "last_success_at": energy_observation_scheduler.last_success_at,
            "next_run_at": energy_observation_scheduler.next_run_at,
            "last_error": energy_observation_scheduler.last_error,
        },
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level="info",
    )
