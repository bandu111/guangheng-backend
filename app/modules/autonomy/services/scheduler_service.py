import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.autonomy.models.autonomous_decision_run import (
    AutonomousTriggerType,
)
from app.modules.autonomy.services.autonomy_policy_service import (
    SchedulerPolicy,
    autonomy_policy,
)
from app.modules.autonomy.services.decision_orchestrator import (
    AutonomousDecisionOrchestrator,
    autonomous_decision_orchestrator,
)


class SchedulerService:
    def __init__(
        self,
        *,
        policy: SchedulerPolicy = autonomy_policy.scheduler,
        orchestrator: AutonomousDecisionOrchestrator = autonomous_decision_orchestrator,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.policy = policy
        self.orchestrator = orchestrator
        self.session_factory = session_factory
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self.next_run_at: datetime | None = None

    @property
    def running(self) -> bool:
        return self.orchestrator.running

    @property
    def started(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if not self.policy.enabled or self.started:
            return
        # A FastAPI app can be started more than once by tests or development
        # reloads. asyncio primitives must belong to the current event loop.
        self._stop_event = asyncio.Event()
        self.next_run_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.policy.initial_delay_seconds
        )
        self._task = asyncio.create_task(self._loop(), name="guangheng-autonomy")

    async def stop(self) -> None:
        task = self._task
        self._task = None
        self.next_run_at = None
        if task is None:
            return
        self._stop_event.set()
        await task

    async def _loop(self) -> None:
        if await self._wait_for_stop(self.policy.initial_delay_seconds):
            return
        while not self._stop_event.is_set():
            with self.session_factory() as db:
                await self.orchestrator.run(db, AutonomousTriggerType.SCHEDULED)
            if self._stop_event.is_set():
                return
            self.next_run_at = datetime.now(timezone.utc) + timedelta(
                seconds=self.policy.interval_seconds
            )
            if await self._wait_for_stop(self.policy.interval_seconds):
                return

    async def _wait_for_stop(self, delay_seconds: int) -> bool:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay_seconds)
            return True
        except TimeoutError:
            return False


scheduler_service = SchedulerService()
