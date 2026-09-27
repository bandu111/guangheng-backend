import asyncio

from app.modules.autonomy.models.autonomous_decision_run import AutonomousTriggerType
from app.modules.autonomy.services.autonomy_policy_service import SchedulerPolicy
from app.modules.autonomy.services.scheduler_service import SchedulerService


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class CountingOrchestrator:
    def __init__(self):
        self.calls = 0
        self.running = False

    async def run(self, db, trigger_type):
        assert trigger_type == AutonomousTriggerType.SCHEDULED
        self.calls += 1


def test_scheduler_disabled_never_starts_background_run():
    async def scenario():
        orchestrator = CountingOrchestrator()
        scheduler = SchedulerService(
            policy=SchedulerPolicy(
                enabled=False,
                interval_seconds=1,
                initial_delay_seconds=1,
            ),
            orchestrator=orchestrator,
            session_factory=FakeSession,
        )
        scheduler.start()
        await asyncio.sleep(0)
        await scheduler.stop()
        return scheduler, orchestrator

    scheduler, orchestrator = asyncio.run(scenario())
    assert scheduler.started is False
    assert scheduler.next_run_at is None
    assert orchestrator.calls == 0


def test_scheduler_waits_initial_delay_and_runs_repeatedly():
    async def scenario():
        orchestrator = CountingOrchestrator()
        scheduler = SchedulerService(
            policy=SchedulerPolicy(
                enabled=True,
                interval_seconds=1,
                initial_delay_seconds=1,
            ),
            orchestrator=orchestrator,
            session_factory=FakeSession,
        )
        scheduler.start()
        await asyncio.sleep(0.1)
        assert orchestrator.calls == 0
        await asyncio.sleep(2.1)
        await scheduler.stop()
        return orchestrator.calls

    assert asyncio.run(scenario()) >= 2
