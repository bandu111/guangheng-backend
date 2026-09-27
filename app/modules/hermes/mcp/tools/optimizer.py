from app.core.database import SessionLocal
from app.modules.hermes.mcp.tools.common import failure, success
from app.modules.hermes.schemas.tool import HermesToolResultSchema
from app.modules.optimizer.services.optimizer_evaluation_service import (
    optimizer_evaluation_service,
)


async def evaluate_optimizer() -> HermesToolResultSchema:
    """Evaluate Optimizer V2 without creating a proposal or controlling a device."""
    try:
        with SessionLocal() as db:
            decision = await optimizer_evaluation_service.evaluate(db=db)
        return success("evaluate_optimizer", decision)
    except Exception:
        return failure(
            "evaluate_optimizer",
            "OPTIMIZER_EVALUATION_UNAVAILABLE",
            "Optimizer V2 evaluation could not be completed.",
        )
