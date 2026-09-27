from sqlalchemy.orm import Session

from app.modules.autonomy.models.autonomous_decision_run import (
    AutonomousDecisionRun,
)
from app.modules.autonomy.models.notification_event import (
    NotificationEvent,
    NotificationEventType,
    NotificationSeverity,
    NotificationStatus,
)
from app.modules.autonomy.repositories.notification_repository import (
    notification_repository,
)
from app.modules.autonomy.schemas.notification import NotificationPayloadSchema
from app.modules.optimizer.schemas.optimizer_v2 import OptimizationDecisionV2Schema
from app.modules.proposal.models.proposal import Proposal


class NotificationNotFoundError(LookupError):
    pass


class NotificationService:
    def action_required(
        self,
        db: Session,
        run: AutonomousDecisionRun,
        decision: OptimizationDecisionV2Schema,
        proposal: Proposal,
        reuse: bool = True,
    ) -> tuple[NotificationEvent, bool]:
        dedupe_key = f"proposal:{proposal.id}"
        payload = NotificationPayloadSchema(
            strategy=decision.strategy_mode.value,
            capability=decision.capability,
            current_value=decision.current_value,
            target_value=decision.target_value,
            reason_code=decision.reason_code,
            confidence=decision.decision_confidence,
            proposal_id=proposal.id,
        )
        return self._create_or_reuse(
            db=db,
            run=run,
            event_type=NotificationEventType.ACTION_REQUIRED,
            title="需要你的确认",
            message="建议调整家庭备电目标",
            severity=NotificationSeverity.ATTENTION,
            dedupe_key=dedupe_key,
            payload=payload,
            proposal_id=proposal.id,
            reuse=reuse,
        )

    def proposal_conflict(
        self,
        db: Session,
        run: AutonomousDecisionRun,
        decision: OptimizationDecisionV2Schema,
        existing: Proposal,
        reuse: bool = True,
    ) -> tuple[NotificationEvent, bool]:
        dedupe_key = (
            f"proposal-conflict:{existing.id}:{decision.capability}:"
            f"{decision.target_value}"
        )
        payload = NotificationPayloadSchema(
            strategy=decision.strategy_mode.value,
            capability=decision.capability,
            current_value=decision.current_value,
            target_value=decision.target_value,
            reason_code=decision.reason_code,
            confidence=decision.decision_confidence,
            existing_proposal_id=existing.id,
            recommended_target=decision.target_value,
        )
        return self._create_or_reuse(
            db=db,
            run=run,
            event_type=NotificationEventType.SYSTEM_WARNING,
            title="存在待确认方案",
            message="已有待确认能源方案，请先处理后再生成新的调整方案。",
            severity=NotificationSeverity.WARNING,
            dedupe_key=dedupe_key,
            payload=payload,
            proposal_id=existing.id,
            reuse=reuse,
        )

    def system_warning(
        self,
        db: Session,
        run: AutonomousDecisionRun,
        error_code: str,
        reuse: bool = True,
    ) -> tuple[NotificationEvent, bool]:
        return self._create_or_reuse(
            db=db,
            run=run,
            event_type=NotificationEventType.SYSTEM_WARNING,
            title="能源分析暂不可用",
            message="光衡暂时无法完成本次能源分析，请稍后重试。",
            severity=NotificationSeverity.WARNING,
            dedupe_key=f"autonomy-warning:{error_code}",
            payload=NotificationPayloadSchema(error_code=error_code),
            proposal_id=None,
            reuse=reuse,
        )

    def list(
        self,
        db: Session,
        limit: int,
        status: NotificationStatus | None = None,
    ) -> list[NotificationEvent]:
        return notification_repository.list(db, limit, status)

    def mark_read(self, db: Session, event_id: int) -> NotificationEvent:
        event = notification_repository.get_by_id(db, event_id)
        if event is None:
            raise NotificationNotFoundError(event_id)
        return notification_repository.mark_read(db, event)

    def _create_or_reuse(
        self,
        *,
        db: Session,
        run: AutonomousDecisionRun,
        event_type: NotificationEventType,
        title: str,
        message: str,
        severity: NotificationSeverity,
        dedupe_key: str,
        payload: NotificationPayloadSchema,
        proposal_id: int | None,
        reuse: bool,
    ) -> tuple[NotificationEvent, bool]:
        existing = (
            notification_repository.get_unread_by_dedupe_key(db, dedupe_key)
            if reuse
            else None
        )
        if existing is not None:
            return existing, True
        event = NotificationEvent(
            event_type=event_type,
            title=title,
            message=message,
            severity=severity,
            status=NotificationStatus.UNREAD,
            decision_run_id=run.id,
            proposal_id=proposal_id,
            dedupe_key=dedupe_key,
            payload=payload.model_dump(mode="json"),
        )
        return notification_repository.create(db, event), False


notification_service = NotificationService()
