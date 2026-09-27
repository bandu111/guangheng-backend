from app.core.database import SessionLocal
from app.modules.hermes.mcp.tools.common import failure, success
from app.modules.hermes.schemas.tool import HermesToolResultSchema
from app.modules.proposal.models.proposal import ProposalStatus
from app.modules.proposal.repositories.proposal_repository import proposal_repository
from app.modules.proposal.schemas.proposal import (
    ProposalListResponseSchema,
    ProposalResponseSchema,
)
from app.modules.proposal.services.proposal_service import proposal_service
from app.modules.action_set.models.action_set import ActionSetStatus
from app.modules.action_set.services.action_set_service import action_set_service


async def generate_proposal(
    opportunity_code: str | None = None,
) -> HermesToolResultSchema:
    """Generate a PENDING proposal or coordinated action set only.

    Supplying an opportunity code from Household Energy Graph creates one
    approval unit containing ordered child proposals. This tool never approves
    or executes either form.
    """
    try:
        with SessionLocal() as db:
            if opportunity_code:
                action_set = await action_set_service.generate(
                    db=db, opportunity_code=opportunity_code
                )
                if action_set.status != ActionSetStatus.PENDING:
                    return failure(
                        "generate_proposal",
                        "ACTION_SET_STATE_INVALID",
                        "Only a PENDING action set may be returned to Hermes.",
                    )
                return success(
                    "generate_proposal",
                    {"created": True, "proposal": None, "action_set": action_set},
                )
            result = await proposal_service.generate(db=db)
        if (
            result.proposal is not None
            and result.proposal.status != ProposalStatus.PENDING
        ):
            return failure(
                "generate_proposal",
                "PROPOSAL_STATE_INVALID",
                "Only a PENDING proposal may be returned to Hermes.",
            )
        return success("generate_proposal", result)
    except Exception:
        return failure(
            "generate_proposal",
            "PROPOSAL_GENERATION_FAILED",
            "A pending proposal could not be generated.",
        )


async def get_proposal(proposal_id: int) -> HermesToolResultSchema:
    """Read one proposal by ID without changing its state."""
    try:
        with SessionLocal() as db:
            proposal = proposal_repository.get_by_id(db, proposal_id)
            if proposal is None:
                return failure(
                    "get_proposal",
                    "PROPOSAL_NOT_FOUND",
                    "The requested proposal was not found.",
                )
            response = ProposalResponseSchema.model_validate(proposal)
        return success("get_proposal", response)
    except Exception:
        return failure(
            "get_proposal",
            "PROPOSAL_READ_FAILED",
            "The proposal could not be read.",
        )


async def list_proposals() -> HermesToolResultSchema:
    """List proposals for audit and user explanation without modifying them."""
    try:
        with SessionLocal() as db:
            proposals = proposal_repository.get_all(db)
            response = ProposalListResponseSchema(
                count=len(proposals),
                proposals=[
                    ProposalResponseSchema.model_validate(item)
                    for item in proposals
                ],
            )
        return success("list_proposals", response)
    except Exception:
        return failure(
            "list_proposals",
            "PROPOSAL_LIST_FAILED",
            "Proposals could not be listed.",
        )
