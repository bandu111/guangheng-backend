from app.core.database import SessionLocal
from app.modules.energy_state.services.energy_balance_service import (
    energy_balance_service,
)
from app.modules.energy_state.services.energy_state_service import energy_state_service
from app.modules.hermes.mcp.tools.common import failure, success
from app.modules.hermes.schemas.tool import HermesToolResultSchema


async def get_energy_state() -> HermesToolResultSchema:
    """Read the current normalized household energy state."""
    try:
        with SessionLocal() as db:
            state = await energy_state_service.get_energy_state(db=db)
        if not state.available:
            return failure(
                "get_energy_state",
                "ENERGY_STATE_UNAVAILABLE",
                "Current household energy state is unavailable.",
            )
        return success("get_energy_state", state)
    except Exception:
        return failure(
            "get_energy_state",
            "ENERGY_STATE_UNAVAILABLE",
            "Current household energy state could not be read.",
        )


async def get_energy_balance() -> HermesToolResultSchema:
    """Read the current normalized household energy balance."""
    try:
        with SessionLocal() as db:
            balance = await energy_balance_service.get_energy_balance(db=db)
        if not balance.available:
            return failure(
                "get_energy_balance",
                "ENERGY_BALANCE_UNAVAILABLE",
                "Current household energy balance is unavailable.",
            )
        return success("get_energy_balance", balance)
    except Exception:
        return failure(
            "get_energy_balance",
            "ENERGY_BALANCE_UNAVAILABLE",
            "Current household energy balance could not be read.",
        )
