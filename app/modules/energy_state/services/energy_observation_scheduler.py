import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.energy_state.services.energy_observation_policy_service import (
    EnergyObservationPolicy,
    energy_observation_policy,
)
from app.modules.energy_state.services.energy_observation_service import (
    EnergyObservationService,
    energy_observation_service,
)
from app.modules.energy_state.services.simulator_history_service import (
    simulator_history_service,
)


class EnergyObservationScheduler:
    def __init__(
        self,
        *,
        policy: EnergyObservationPolicy = energy_observation_policy,
        service: EnergyObservationService = energy_observation_service,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.policy = policy
        self.service = service
        self.session_factory = session_factory
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self.next_run_at: datetime | None = None
        self.last_success_at: datetime | None = None
        self.last_error: str | None = None
        self._simulator_history_initialized = False

    @property
    def started(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if not self.policy.enabled or self.started:
            return
        self._stop_event = asyncio.Event()
        self.next_run_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.policy.initial_delay_seconds
        )
        self._task = asyncio.create_task(
            self._loop(), name="guangheng-energy-observer"
        )

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
            try:
                with self.session_factory() as db:
                    observation = await self.service.capture(db)
                    if (
                        observation.source_mode == "simulator"
                        and not self._simulator_history_initialized
                    ):
                        simulator_history_service.ensure_recent_history(
                            db,
                            observed_at=observation.observed_at.replace(
                                tzinfo=timezone.utc
                            ),
                            soc_percent=observation.soc_percent,
                        )
                        self._simulator_history_initialized = True
                self.last_success_at = datetime.now(timezone.utc)
                self.last_error = None
            except Exception as exc:
                # Observation failure must not terminate the server scheduler.
                self.last_error = type(exc).__name__
            if self._stop_event.is_set():
                return
            self.next_run_at = datetime.now(timezone.utc) + timedelta(
                seconds=self.policy.interval_seconds
            )
            if await self._wait_for_stop(self.policy.interval_seconds):
                return

    async def _wait_for_stop(self, seconds: int) -> bool:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
            return True
        except TimeoutError:
            return False


energy_observation_scheduler = EnergyObservationScheduler()
