from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.proposal.models.proposal import Proposal, ProposalStatus


class ProposalRepository:
    def create(self, db: Session, proposal: Proposal) -> Proposal:
        try:
            db.add(proposal)
            db.commit()
            db.refresh(proposal)
        except Exception:
            db.rollback()
            raise
        return proposal

    def save(self, db: Session, proposal: Proposal) -> Proposal:
        try:
            db.add(proposal)
            db.commit()
            db.refresh(proposal)
        except Exception:
            db.rollback()
            raise
        return proposal

    def get_by_id(self, db: Session, proposal_id: int) -> Proposal | None:
        return db.get(Proposal, proposal_id)

    def get_all(self, db: Session) -> list[Proposal]:
        return list(db.scalars(select(Proposal).order_by(Proposal.id.desc())).all())

    def get_matching_pending(
        self, db: Session, device_id: int, capability: str, target_value: float
    ) -> Proposal | None:
        statement = select(Proposal).where(
            Proposal.device_id == device_id,
            Proposal.capability == capability,
            Proposal.target_value == target_value,
            Proposal.status == ProposalStatus.PENDING,
        )
        return db.scalar(statement)

    def transition(
        self,
        db: Session,
        proposal_id: int,
        expected: ProposalStatus,
        new_status: ProposalStatus,
    ) -> Proposal | None:
        values = {"status": new_status, "updated_at": datetime.utcnow()}
        if new_status == ProposalStatus.APPROVED:
            values["approved_at"] = datetime.utcnow()
        elif new_status == ProposalStatus.REJECTED:
            values["rejected_at"] = datetime.utcnow()
        try:
            result = db.execute(
                update(Proposal)
                .where(Proposal.id == proposal_id, Proposal.status == expected)
                .values(**values)
            )
            if result.rowcount != 1:
                db.rollback()
                return None
            db.commit()
        except Exception:
            db.rollback()
            raise
        return self.get_by_id(db, proposal_id)


proposal_repository = ProposalRepository()
