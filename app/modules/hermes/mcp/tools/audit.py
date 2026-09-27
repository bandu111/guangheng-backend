from app.core.database import SessionLocal
from app.modules.execution.repositories.execution_repository import execution_repository
from app.modules.execution.schemas.execution import (
    ExecutionListResponseSchema,
    ExecutionResponseSchema,
)
from app.modules.hermes.mcp.tools.common import failure, success
from app.modules.hermes.schemas.tool import HermesToolResultSchema


async def get_execution(execution_id: int) -> HermesToolResultSchema:
    """Read one historical execution and its verification result."""
    try:
        with SessionLocal() as db:
            execution = execution_repository.get_by_id(db, execution_id)
            if execution is None:
                return failure(
                    "get_execution",
                    "EXECUTION_NOT_FOUND",
                    "The requested execution was not found.",
                )
            response = ExecutionResponseSchema.model_validate(execution)
        return success("get_execution", response)
    except Exception:
        return failure(
            "get_execution",
            "EXECUTION_READ_FAILED",
            "The execution record could not be read.",
        )


async def list_executions() -> HermesToolResultSchema:
    """List historical executions and readback verification results."""
    try:
        with SessionLocal() as db:
            executions = execution_repository.get_all(db)
            response = ExecutionListResponseSchema(
                count=len(executions),
                executions=[
                    ExecutionResponseSchema.model_validate(item)
                    for item in executions
                ],
            )
        return success("list_executions", response)
    except Exception:
        return failure(
            "list_executions",
            "EXECUTION_LIST_FAILED",
            "Execution records could not be listed.",
        )
