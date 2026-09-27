from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.autonomy.models.autonomous_decision_run import (
    AutonomousDecisionRun,
)
from app.modules.autonomy.repositories.autonomous_decision_repository import (
    autonomous_decision_repository,
)
from app.modules.proposal.models.proposal import Proposal, ProposalStatus


class AutonomousDecisionNotFoundError(LookupError):
    pass


class AutonomousDecisionService:
    def get(self, db: Session, run_id: int) -> AutonomousDecisionRun:
        run = autonomous_decision_repository.get_by_id(db, run_id)
        if run is None:
            raise AutonomousDecisionNotFoundError(run_id)
        return run

    def list(self, db: Session, limit: int) -> list[AutonomousDecisionRun]:
        return autonomous_decision_repository.list(db, limit)

    @staticmethod
    def get_pending_for_capability(
        db: Session,
        device_id: int,
        capability: str,
    ) -> Proposal | None:
        statement = (
            select(Proposal)
            .where(
                Proposal.device_id == device_id,
                Proposal.capability == capability,
                Proposal.status == ProposalStatus.PENDING,
            )
            .order_by(Proposal.id.desc())
        )
        return db.scalar(statement)

    @staticmethod
    def get_recent_matching_rejected(
        db: Session,
        device_id: int,
        capability: str,
        target_value: float,
        cooldown_minutes: int,
        now: datetime,
    ) -> Proposal | None:
        cutoff = now - timedelta(minutes=cooldown_minutes)
        statement = (
            select(Proposal)
            .where(
                Proposal.device_id == device_id,
                Proposal.capability == capability,
                Proposal.target_value == target_value,
                Proposal.status == ProposalStatus.REJECTED,
                Proposal.rejected_at.is_not(None),
                Proposal.rejected_at >= cutoff,
            )
            .order_by(Proposal.rejected_at.desc())
        )
        return db.scalar(statement)


autonomous_decision_service = AutonomousDecisionService()
