from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.autonomy.models.autonomous_decision_run import (
    AutonomousRunStatus,
    AutonomousTriggerType,
)
from app.modules.autonomy.models.notification_event import NotificationStatus
from app.modules.autonomy.repositories.autonomous_decision_repository import (
    autonomous_decision_repository,
)
from app.modules.autonomy.repositories.notification_repository import (
    notification_repository,
)
from app.modules.autonomy.schemas.autonomous_decision import (
    AgentState,
    AutonomyStatusSchema,
    AutonomousDecisionListSchema,
    AutonomousDecisionRunSchema,
    LatestDecisionSchema,
    PendingProposalSummarySchema,
)
from app.modules.autonomy.schemas.notification import (
    NotificationEventListSchema,
    NotificationEventSchema,
)
from app.modules.autonomy.schemas.autonomy_level import (
    AutonomyLevelResponseSchema,
    AutonomyLevelUpdateSchema,
)
from app.modules.autonomy.services.autonomous_decision_service import (
    AutonomousDecisionNotFoundError,
    autonomous_decision_service,
)
from app.modules.autonomy.services.autonomy_policy_service import autonomy_policy
from app.modules.autonomy.services.decision_orchestrator import (
    autonomous_decision_orchestrator,
)
from app.modules.autonomy.services.notification_service import (
    NotificationNotFoundError,
    notification_service,
)
from app.modules.autonomy.services.scheduler_service import scheduler_service
from app.modules.autonomy.services.autonomy_level_service import (
    autonomy_level_service,
)
from app.modules.proposal.models.proposal import ProposalStatus
from app.modules.proposal.repositories.proposal_repository import proposal_repository


router = APIRouter(tags=["Autonomous Decision"])


@router.get("/autonomy/status", response_model=AutonomyStatusSchema)
def get_autonomy_status(db: Session = Depends(get_db)) -> AutonomyStatusSchema:
    latest = autonomous_decision_repository.get_latest(db)
    pending = None
    latest_decision = None
    if latest is not None and latest.action_required is not None:
        latest_decision = LatestDecisionSchema(
            run_id=latest.id,
            strategy=latest.strategy,
            optimizer_version=latest.decision_version,
            confidence=latest.confidence,
            capability=latest.capability,
            current_value=latest.current_value,
            target_value=latest.target_value,
            action_required=latest.action_required,
            reason_code=latest.reason_code,
            evaluated_at=latest.completed_at or latest.started_at,
            result_code=latest.result_code,
        )
    if latest is not None and latest.proposal_id is not None:
        proposal = proposal_repository.get_by_id(db, latest.proposal_id)
        if proposal is not None and proposal.status == ProposalStatus.PENDING:
            pending = PendingProposalSummarySchema.model_validate(
                {
                    "id": proposal.id,
                    "status": proposal.status.value,
                    "capability": proposal.capability,
                    "current_value": proposal.current_value,
                    "target_value": proposal.target_value,
                }
            )

    if pending is not None:
        state = AgentState.ACTION_REQUIRED
    elif latest is not None and latest.status == AutonomousRunStatus.FAILED:
        state = AgentState.DEGRADED
    elif latest is not None:
        state = AgentState.MONITORING
    else:
        state = (
            AgentState.MONITORING
            if autonomy_policy.scheduler.enabled
            else AgentState.DISABLED
        )

    return AutonomyStatusSchema(
        enabled=autonomy_policy.scheduler.enabled,
        interval_seconds=autonomy_policy.scheduler.interval_seconds,
        running=autonomous_decision_orchestrator.running,
        last_run=latest,
        next_run_at=scheduler_service.next_run_at,
        agent_state=state,
        autonomy_level=autonomy_level_service.get_level(db),
        latest_decision=latest_decision,
        pending_proposal=pending,
        unread_notification_count=notification_repository.count_unread(db),
    )


@router.get("/autonomy/level", response_model=AutonomyLevelResponseSchema)
def get_autonomy_level(db: Session = Depends(get_db)) -> AutonomyLevelResponseSchema:
    return autonomy_level_service.get(db)


@router.put("/autonomy/level", response_model=AutonomyLevelResponseSchema)
def update_autonomy_level(
    request: AutonomyLevelUpdateSchema,
    db: Session = Depends(get_db),
) -> AutonomyLevelResponseSchema:
    return autonomy_level_service.update(db, request.level)


@router.post("/autonomy/run", response_model=AutonomousDecisionRunSchema)
async def run_autonomy(db: Session = Depends(get_db)) -> AutonomousDecisionRunSchema:
    return await autonomous_decision_orchestrator.run(
        db,
        AutonomousTriggerType.MANUAL,
    )


@router.get(
    "/autonomy/decisions",
    response_model=AutonomousDecisionListSchema,
)
def list_autonomous_decisions(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> AutonomousDecisionListSchema:
    rows = autonomous_decision_service.list(db, limit)
    return AutonomousDecisionListSchema(count=len(rows), decisions=rows)


@router.get(
    "/autonomy/decisions/{run_id}",
    response_model=AutonomousDecisionRunSchema,
)
def get_autonomous_decision(
    run_id: int,
    db: Session = Depends(get_db),
) -> AutonomousDecisionRunSchema:
    try:
        return autonomous_decision_service.get(db, run_id)
    except AutonomousDecisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Decision run not found.") from exc


@router.get("/notifications", response_model=NotificationEventListSchema)
def list_notifications(
    status: NotificationStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> NotificationEventListSchema:
    rows = notification_service.list(db, limit, status)
    return NotificationEventListSchema(count=len(rows), notifications=rows)


@router.patch(
    "/notifications/{event_id}/read",
    response_model=NotificationEventSchema,
)
def read_notification(
    event_id: int,
    db: Session = Depends(get_db),
) -> NotificationEventSchema:
    try:
        return notification_service.mark_read(db, event_id)
    except NotificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Notification not found.") from exc
