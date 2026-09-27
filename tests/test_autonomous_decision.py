import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.autonomy.models.autonomous_decision_run import (
    AutonomousDecisionRun,
    AutonomousRunStatus,
    AutonomousTriggerType,
)
from app.modules.autonomy.models.notification_event import (
    NotificationEvent,
    NotificationEventType,
    NotificationStatus,
)
from app.modules.autonomy.models.autonomy_config import AutonomyConfig, AutonomyLevel
from app.modules.autonomy.services.autonomy_policy_service import (
    AutonomyPolicy,
    DeduplicationPolicy,
    RuntimePolicy,
    SchedulerPolicy,
)
from app.modules.autonomy.services.decision_orchestrator import (
    AutonomousDecisionOrchestrator,
)
from app.modules.autonomy.services.notification_service import NotificationService
from app.modules.device_registry.models.device import Device
from app.modules.execution.models.execution import Execution
from app.modules.optimizer.schemas.optimizer_v2 import (
    OptimizationDecisionV2Schema,
    OptimizerV2EvidenceSchema,
)
from app.modules.proposal.models.proposal import Proposal, ProposalStatus
from app.modules.proposal.services.proposal_service import ProposalService
from app.modules.strategy.models.strategy import StrategyMode


NOW = datetime(2026, 9, 20, 4, 0, tzinfo=timezone.utc)


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _policy(cooldown=60, timeout=60) -> AutonomyPolicy:
    return AutonomyPolicy(
        version="v1",
        default_level="CONFIRM",
        scheduler=SchedulerPolicy(
            enabled=False,
            interval_seconds=300,
            initial_delay_seconds=30,
        ),
        deduplication=DeduplicationPolicy(
            pending_proposal_reuse=True,
            notification_reuse=True,
            rejected_reproposal_cooldown_minutes=cooldown,
        ),
        runtime=RuntimePolicy(run_timeout_seconds=timeout),
    )


def _decision(*, action=True, current=30.0, target=40.0):
    return OptimizationDecisionV2Schema(
        version="v2",
        action_required=action,
        device_id=1,
        capability="backup_reserve",
        current_value=current,
        target_value=target,
        strategy_mode=StrategyMode.AUTO,
        decision_confidence="HIGH",
        reason_code=(
            "AUTO_FORECAST_MODERATE_DEFICIT"
            if action
            else "TARGET_ALREADY_SATISFIED"
        ),
        reason="Test decision from Optimizer V2.",
        evidence=OptimizerV2EvidenceSchema(
            solar_forecast_confidence="HIGH",
            load_forecast_confidence="HIGH",
            decision_confidence="HIGH",
        ),
        policy_rule="test.optimizer.v2",
    )


class ContextService:
    def __init__(self, *, available=True, error_code=None, gate=None):
        self.available = available
        self.error_code = error_code
        self.gate = gate
        self.started = asyncio.Event() if gate is not None else None

    async def get_context(self, *, db):
        if self.started is not None:
            self.started.set()
            await self.gate.wait()
        return SimpleNamespace(
            available=self.available,
            observed_at=NOW,
            error_code=self.error_code,
        )


class OptimizerService:
    def __init__(self, decision=None, error=None):
        self.decision = decision
        self.error = error
        self.calls = 0

    async def evaluate(self, *, db):
        self.calls += 1
        if self.error:
            raise self.error
        return self.decision


def _device(db):
    db.add(
        Device(
            id=1,
            source_device_id="autonomy_test_device",
            vendor="anker_solix",
            model="test",
            device_type="storage",
            topology_role="storage",
            integration="anker_solix_official",
            source_mode="simulator",
            propose_enabled=True,
            control_enabled=True,
        )
    )
    db.commit()


def _orchestrator(decision, **kwargs):
    return AutonomousDecisionOrchestrator(
        policy=kwargs.pop("policy", _policy()),
        context_service=kwargs.pop("context", ContextService()),
        optimizer_service=kwargs.pop("optimizer", OptimizerService(decision)),
        proposal_creation_service=kwargs.pop("proposal", ProposalService()),
        notifications=kwargs.pop("notifications", NotificationService()),
    )


def _counts(db):
    return {
        "proposals": db.scalar(select(func.count(Proposal.id))),
        "notifications": db.scalar(select(func.count(NotificationEvent.id))),
        "executions": db.scalar(select(func.count(Execution.id))),
    }


def test_no_action_creates_run_without_proposal_or_action_notification():
    engine = _engine()
    with Session(engine) as db:
        _device(db)
        run = asyncio.run(
            _orchestrator(_decision(action=False, current=80, target=80)).run(
                db, AutonomousTriggerType.MANUAL
            )
        )
        assert run.status == AutonomousRunStatus.COMPLETED
        assert run.result_code == "NO_ACTION_REQUIRED"
        assert _counts(db) == {"proposals": 0, "notifications": 0, "executions": 0}


def test_observe_level_reads_context_without_optimizer_or_proposal():
    engine = _engine()
    optimizer = OptimizerService(_decision())
    with Session(engine) as db:
        _device(db)
        db.add(AutonomyConfig(level=AutonomyLevel.OBSERVE))
        db.commit()
        run = asyncio.run(
            _orchestrator(_decision(), optimizer=optimizer).run(
                db, AutonomousTriggerType.MANUAL
            )
        )
        assert run.result_code == "OBSERVATION_ONLY"
        assert optimizer.calls == 0
        assert _counts(db) == {"proposals": 0, "notifications": 0, "executions": 0}


def test_shadow_level_runs_optimizer_without_creating_proposal():
    engine = _engine()
    optimizer = OptimizerService(_decision())
    with Session(engine) as db:
        _device(db)
        db.add(AutonomyConfig(level=AutonomyLevel.SHADOW))
        db.commit()
        run = asyncio.run(
            _orchestrator(_decision(), optimizer=optimizer).run(
                db, AutonomousTriggerType.MANUAL
            )
        )
        assert run.result_code == "SHADOW_ACTION_IDENTIFIED"
        assert optimizer.calls == 1
        assert _counts(db) == {"proposals": 0, "notifications": 0, "executions": 0}


def test_action_required_creates_one_pending_proposal_and_notification():
    engine = _engine()
    with Session(engine) as db:
        _device(db)
        run = asyncio.run(
            _orchestrator(_decision()).run(db, AutonomousTriggerType.MANUAL)
        )
        proposal = db.get(Proposal, run.proposal_id)
        event = db.get(NotificationEvent, run.notification_event_id)
        assert run.result_code == "PROPOSAL_CREATED"
        assert proposal.status == ProposalStatus.PENDING
        assert event.event_type == NotificationEventType.ACTION_REQUIRED
        assert event.payload["target_value"] == 40.0
        assert event.dedupe_key == f"proposal:{proposal.id}"


def test_repeated_decision_reuses_pending_proposal_and_unread_notification():
    engine = _engine()
    orchestrator = _orchestrator(_decision())
    with Session(engine) as db:
        _device(db)
        first = asyncio.run(orchestrator.run(db, AutonomousTriggerType.MANUAL))
        second = asyncio.run(orchestrator.run(db, AutonomousTriggerType.SCHEDULED))
        assert second.result_code == "EXISTING_PENDING_PROPOSAL_REUSED"
        assert second.proposal_id == first.proposal_id
        assert second.notification_event_id == first.notification_event_id
        assert _counts(db)["proposals"] == 1
        assert _counts(db)["notifications"] == 1


def test_different_pending_target_blocks_second_proposal_and_warns():
    engine = _engine()
    with Session(engine) as db:
        _device(db)
        existing = Proposal(
            device_id=1,
            strategy_mode=StrategyMode.AUTO,
            capability="backup_reserve",
            current_value=30,
            target_value=35,
            reason_code="OLD",
            reason="Existing pending proposal.",
            status=ProposalStatus.PENDING,
        )
        db.add(existing)
        db.commit()
        run = asyncio.run(
            _orchestrator(_decision(target=40)).run(
                db, AutonomousTriggerType.SCHEDULED
            )
        )
        event = db.get(NotificationEvent, run.notification_event_id)
        assert run.result_code == "PENDING_PROPOSAL_CONFLICT"
        assert run.proposal_id == existing.id
        assert _counts(db)["proposals"] == 1
        assert event.event_type == NotificationEventType.SYSTEM_WARNING
        assert event.payload["existing_proposal_id"] == existing.id
        assert event.payload["recommended_target"] == 40.0


def test_recent_rejection_suppresses_same_reproposal_without_notification():
    engine = _engine()
    with Session(engine) as db:
        _device(db)
        rejected = Proposal(
            device_id=1,
            strategy_mode=StrategyMode.AUTO,
            capability="backup_reserve",
            current_value=30,
            target_value=40,
            reason_code="OLD",
            reason="Rejected proposal.",
            status=ProposalStatus.REJECTED,
            rejected_at=datetime.utcnow() - timedelta(minutes=10),
        )
        db.add(rejected)
        db.commit()
        run = asyncio.run(
            _orchestrator(_decision()).run(db, AutonomousTriggerType.SCHEDULED)
        )
        assert run.status == AutonomousRunStatus.SKIPPED
        assert run.result_code == "REJECTED_PROPOSAL_COOLDOWN"
        assert _counts(db)["proposals"] == 1
        assert _counts(db)["notifications"] == 0


def test_expired_rejection_cooldown_allows_new_pending_proposal():
    engine = _engine()
    with Session(engine) as db:
        _device(db)
        db.add(
            Proposal(
                device_id=1,
                strategy_mode=StrategyMode.AUTO,
                capability="backup_reserve",
                current_value=30,
                target_value=40,
                reason_code="OLD",
                reason="Old rejection.",
                status=ProposalStatus.REJECTED,
                rejected_at=datetime.utcnow() - timedelta(minutes=61),
            )
        )
        db.commit()
        run = asyncio.run(
            _orchestrator(_decision()).run(db, AutonomousTriggerType.SCHEDULED)
        )
        assert run.result_code == "PROPOSAL_CREATED"
        assert _counts(db)["proposals"] == 2


def test_decision_context_failure_creates_no_proposal():
    engine = _engine()
    context = ContextService(
        available=False,
        error_code="DECISION_CONTEXT_UNAVAILABLE",
    )
    with Session(engine) as db:
        _device(db)
        run = asyncio.run(
            _orchestrator(_decision(), context=context).run(
                db, AutonomousTriggerType.MANUAL
            )
        )
        assert run.status == AutonomousRunStatus.FAILED
        assert run.error_code == "DECISION_CONTEXT_UNAVAILABLE"
        assert _counts(db)["proposals"] == 0


def test_optimizer_failure_creates_no_proposal():
    engine = _engine()
    optimizer = OptimizerService(error=RuntimeError("unavailable"))
    with Session(engine) as db:
        _device(db)
        run = asyncio.run(
            _orchestrator(None, optimizer=optimizer).run(
                db, AutonomousTriggerType.MANUAL
            )
        )
        assert run.status == AutonomousRunStatus.FAILED
        assert run.error_code == "OPTIMIZER_UNAVAILABLE"
        assert _counts(db)["proposals"] == 0


def test_optimizer_unavailable_context_decision_creates_no_proposal():
    engine = _engine()
    decision = _decision()
    decision.reason_code = "CONTEXT_UNAVAILABLE"
    decision.decision_confidence = "UNAVAILABLE"
    with Session(engine) as db:
        _device(db)
        run = asyncio.run(
            _orchestrator(decision).run(db, AutonomousTriggerType.MANUAL)
        )
        assert run.status == AutonomousRunStatus.FAILED
        assert run.error_code == "DECISION_CONTEXT_UNAVAILABLE"
        assert _counts(db)["proposals"] == 0


def test_concurrent_second_run_is_skipped():
    engine = _engine()
    sessions = sessionmaker(engine, expire_on_commit=False)

    async def scenario():
        with sessions() as seed:
            _device(seed)
        gate = asyncio.Event()
        context = ContextService(gate=gate)
        orchestrator = _orchestrator(
            _decision(action=False, current=80, target=80),
            context=context,
        )
        with sessions() as first_db, sessions() as second_db:
            first_task = asyncio.create_task(
                orchestrator.run(first_db, AutonomousTriggerType.SCHEDULED)
            )
            await context.started.wait()
            second = await orchestrator.run(
                second_db, AutonomousTriggerType.SCHEDULED
            )
            gate.set()
            first = await first_task
        return first, second

    first, second = asyncio.run(scenario())
    assert first.result_code == "NO_ACTION_REQUIRED"
    assert second.status == AutonomousRunStatus.SKIPPED
    assert second.result_code == "RUN_ALREADY_IN_PROGRESS"


def test_notification_read_is_idempotent_and_does_not_execute():
    engine = _engine()
    service = NotificationService()
    with Session(engine) as db:
        _device(db)
        run = asyncio.run(
            _orchestrator(_decision()).run(db, AutonomousTriggerType.MANUAL)
        )
        before = _counts(db)
        event = service.mark_read(db, run.notification_event_id)
        again = service.mark_read(db, run.notification_event_id)
        after = _counts(db)
        assert event.status == NotificationStatus.READ
        assert event.read_at is not None
        assert again.id == event.id
        assert before["proposals"] == after["proposals"]
        assert before["executions"] == after["executions"] == 0
        assert db.get(Proposal, run.proposal_id).status == ProposalStatus.PENDING


def test_autonomy_never_calls_hermes_approval_execution_or_ha_write(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Forbidden high-privilege or LLM dependency was called")

    monkeypatch.setattr(
        "app.modules.hermes.services.hermes_client.hermes_client.chat", forbidden
    )
    monkeypatch.setattr(
        "app.modules.proposal.services.proposal_service.proposal_service.approve",
        forbidden,
    )
    monkeypatch.setattr(
        "app.modules.execution.services.execution_service.execution_service.execute",
        forbidden,
    )
    monkeypatch.setattr(
        "app.modules.home_assistant.services.home_assistant_service.home_assistant_service.call_service",
        forbidden,
    )
    engine = _engine()
    with Session(engine) as db:
        _device(db)
        run = asyncio.run(
            _orchestrator(_decision()).run(db, AutonomousTriggerType.MANUAL)
        )
        assert run.result_code == "PROPOSAL_CREATED"
        assert _counts(db)["executions"] == 0


def test_decision_and_notification_tables_store_only_bounded_structured_data():
    engine = _engine()
    with Session(engine) as db:
        _device(db)
        asyncio.run(_orchestrator(_decision()).run(db, AutonomousTriggerType.MANUAL))
        run = db.scalar(select(AutonomousDecisionRun))
        event = db.scalar(select(NotificationEvent))
        combined = f"{run.__dict__} {event.__dict__}".lower()
        assert "authorization" not in combined
        assert "api_key" not in combined
        assert "ha_token" not in combined
        assert "reasoning" not in combined
