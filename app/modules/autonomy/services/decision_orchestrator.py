import asyncio
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.modules.autonomy.models.autonomous_decision_run import (
    AutonomousDecisionRun,
    AutonomousRunStatus,
    AutonomousTriggerType,
)
from app.modules.autonomy.repositories.autonomous_decision_repository import (
    autonomous_decision_repository,
)
from app.modules.autonomy.services.autonomous_decision_service import (
    autonomous_decision_service,
)
from app.modules.autonomy.services.autonomy_policy_service import (
    AutonomyPolicy,
    autonomy_policy,
)
from app.modules.autonomy.services.notification_service import (
    NotificationService,
    notification_service,
)
from app.modules.autonomy.models.autonomy_config import AutonomyLevel
from app.modules.autonomy.services.autonomy_level_service import autonomy_level_service
from app.modules.decision_context.services.decision_context_service import (
    decision_context_service,
)
from app.modules.optimizer.schemas.optimizer_v2 import OptimizationDecisionV2Schema
from app.modules.optimizer.services.optimizer_evaluation_service import (
    optimizer_evaluation_service,
)
from app.modules.proposal.services.proposal_service import (
    ProposalPermissionError,
    RuntimeUnavailableError,
    proposal_service,
)


class AutonomousDecisionOrchestrator:
    def __init__(
        self,
        *,
        policy: AutonomyPolicy = autonomy_policy,
        context_service=decision_context_service,
        optimizer_service=optimizer_evaluation_service,
        proposal_creation_service=proposal_service,
        notifications: NotificationService = notification_service,
    ) -> None:
        self.policy = policy
        self.context_service = context_service
        self.optimizer_service = optimizer_service
        self.proposal_creation_service = proposal_creation_service
        self.notifications = notifications
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._lock.locked()

    async def run(
        self,
        db: Session,
        trigger_type: AutonomousTriggerType,
    ) -> AutonomousDecisionRun:
        if self._lock.locked():
            now = datetime.utcnow()
            return autonomous_decision_repository.create(
                db,
                AutonomousDecisionRun(
                    trigger_type=trigger_type,
                    status=AutonomousRunStatus.SKIPPED,
                    started_at=now,
                    completed_at=now,
                    result_code="RUN_ALREADY_IN_PROGRESS",
                    decision_version=self.policy.version,
                ),
            )

        await self._lock.acquire()
        try:
            run = autonomous_decision_repository.create(
                db,
                AutonomousDecisionRun(
                    trigger_type=trigger_type,
                    status=AutonomousRunStatus.RUNNING,
                    started_at=datetime.utcnow(),
                    decision_version=self.policy.version,
                ),
            )
            try:
                return await asyncio.wait_for(
                    self._evaluate(db, run),
                    timeout=self.policy.runtime.run_timeout_seconds,
                )
            except TimeoutError:
                return self._fail(db, run, "AUTONOMY_RUN_TIMEOUT")
            except Exception:
                return self._fail(db, run, "AUTONOMY_INTERNAL_ERROR")
        finally:
            self._lock.release()

    async def _evaluate(
        self,
        db: Session,
        run: AutonomousDecisionRun,
    ) -> AutonomousDecisionRun:
        try:
            context = await self.context_service.get_context(db=db)
        except Exception:
            return self._fail(db, run, "DECISION_CONTEXT_UNAVAILABLE")
        run.context_observed_at = self._db_time(context.observed_at)
        if not context.available:
            return self._fail(
                db,
                run,
                context.error_code or "DECISION_CONTEXT_UNAVAILABLE",
            )

        autonomy_level = autonomy_level_service.get_level(db)
        if autonomy_level == AutonomyLevel.OBSERVE:
            run.status = AutonomousRunStatus.COMPLETED
            run.result_code = "OBSERVATION_ONLY"
            run.completed_at = datetime.utcnow()
            return autonomous_decision_repository.save(db, run)

        try:
            decision = await self.optimizer_service.evaluate(db=db)
        except Exception:
            return self._fail(db, run, "OPTIMIZER_UNAVAILABLE")
        self._apply_decision(run, decision)
        if (
            decision.reason_code == "CONTEXT_UNAVAILABLE"
            or decision.decision_confidence == "UNAVAILABLE"
        ):
            return self._fail(db, run, "DECISION_CONTEXT_UNAVAILABLE")

        if not decision.action_required:
            run.status = AutonomousRunStatus.COMPLETED
            run.result_code = "NO_ACTION_REQUIRED"
            run.completed_at = datetime.utcnow()
            return autonomous_decision_repository.save(db, run)

        if autonomy_level == AutonomyLevel.SHADOW:
            run.status = AutonomousRunStatus.COMPLETED
            run.result_code = "SHADOW_ACTION_IDENTIFIED"
            run.completed_at = datetime.utcnow()
            return autonomous_decision_repository.save(db, run)

        if (
            decision.device_id is None
            or decision.current_value is None
            or decision.target_value is None
        ):
            return self._fail(db, run, "OPTIMIZER_DECISION_INCOMPLETE")

        pending = autonomous_decision_service.get_pending_for_capability(
            db,
            device_id=decision.device_id,
            capability=decision.capability,
        )
        if pending is not None:
            run.proposal_id = pending.id
            if pending.target_value == decision.target_value:
                run.result_code = "EXISTING_PENDING_PROPOSAL_REUSED"
                event, _ = self.notifications.action_required(
                    db,
                    run,
                    decision,
                    pending,
                    reuse=self.policy.deduplication.notification_reuse,
                )
                run.notification_event_id = event.id
            else:
                run.result_code = "PENDING_PROPOSAL_CONFLICT"
                event, _ = self.notifications.proposal_conflict(
                    db,
                    run,
                    decision,
                    pending,
                    reuse=self.policy.deduplication.notification_reuse,
                )
                run.notification_event_id = event.id
            run.status = AutonomousRunStatus.COMPLETED
            run.completed_at = datetime.utcnow()
            return autonomous_decision_repository.save(db, run)

        rejected = autonomous_decision_service.get_recent_matching_rejected(
            db,
            device_id=decision.device_id,
            capability=decision.capability,
            target_value=decision.target_value,
            cooldown_minutes=(
                self.policy.deduplication.rejected_reproposal_cooldown_minutes
            ),
            now=datetime.utcnow(),
        )
        if rejected is not None:
            run.proposal_id = rejected.id
            run.status = AutonomousRunStatus.SKIPPED
            run.result_code = "REJECTED_PROPOSAL_COOLDOWN"
            run.completed_at = datetime.utcnow()
            return autonomous_decision_repository.save(db, run)

        try:
            result = self.proposal_creation_service.create_from_decision(
                db=db,
                decision=decision,
            )
        except (ProposalPermissionError, RuntimeUnavailableError):
            return self._fail(db, run, "PROPOSAL_GENERATION_FAILED")
        if result.proposal is None:
            return self._fail(db, run, "PROPOSAL_GENERATION_FAILED")

        run.proposal_id = result.proposal.id
        run.result_code = (
            "PROPOSAL_CREATED"
            if result.created
            else "EXISTING_PENDING_PROPOSAL_REUSED"
        )
        event, _ = self.notifications.action_required(
            db,
            run,
            decision,
            result.proposal,
            reuse=self.policy.deduplication.notification_reuse,
        )
        run.notification_event_id = event.id
        run.status = AutonomousRunStatus.COMPLETED
        run.completed_at = datetime.utcnow()
        return autonomous_decision_repository.save(db, run)

    def _fail(
        self,
        db: Session,
        run: AutonomousDecisionRun,
        error_code: str,
    ) -> AutonomousDecisionRun:
        run.status = AutonomousRunStatus.FAILED
        run.result_code = "DECISION_FAILED"
        run.error_code = error_code
        run.completed_at = datetime.utcnow()
        saved = autonomous_decision_repository.save(db, run)
        event, _ = self.notifications.system_warning(
            db,
            saved,
            error_code,
            reuse=self.policy.deduplication.notification_reuse,
        )
        saved.notification_event_id = event.id
        return autonomous_decision_repository.save(db, saved)

    @staticmethod
    def _apply_decision(
        run: AutonomousDecisionRun,
        decision: OptimizationDecisionV2Schema,
    ) -> None:
        run.strategy = decision.strategy_mode.value
        run.capability = decision.capability
        run.current_value = decision.current_value
        run.target_value = decision.target_value
        run.action_required = decision.action_required
        run.reason_code = decision.reason_code
        run.confidence = decision.decision_confidence
        run.decision_version = decision.version

    @staticmethod
    def _db_time(value: datetime) -> datetime:
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


autonomous_decision_orchestrator = AutonomousDecisionOrchestrator()
