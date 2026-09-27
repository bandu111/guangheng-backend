from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.energy_state.schemas.energy_state import (
    EnergyStateResponseSchema,
)
from app.modules.energy_state.services.energy_state_service import (
    energy_state_service,
)
from app.modules.energy_state.schemas.energy_balance import (
    EnergyBalanceResponseSchema,
)
from app.modules.energy_state.services.energy_balance_service import (
    energy_balance_service,
)
from app.modules.energy_state.schemas.energy_today import EnergyTodayResponseSchema
from app.modules.energy_state.services.energy_today_service import energy_today_service
from app.modules.energy_state.schemas.energy_schedule import EnergyScheduleResponseSchema
from app.modules.energy_state.services.energy_schedule_service import energy_schedule_service

router = APIRouter(
    prefix="/energy",
    tags=["Energy State"],
)


@router.get(
    "/state",
    response_model=EnergyStateResponseSchema,
)
async def get_energy_state(
    db: Session = Depends(get_db),
):
    return await energy_state_service.get_energy_state(
        db=db,
    )

@router.get(
    "/balance",
    response_model=EnergyBalanceResponseSchema,
)
async def get_energy_balance(
    db: Session = Depends(get_db),
):
    return await energy_balance_service.get_energy_balance(
        db=db,
    )


@router.get(
    "/today",
    response_model=EnergyTodayResponseSchema,
)
async def get_energy_today():
    return await energy_today_service.get_today()


@router.get(
    "/schedule/24h",
    response_model=EnergyScheduleResponseSchema,
)
async def get_energy_schedule(
    db: Session = Depends(get_db),
):
    return await energy_schedule_service.get_schedule(db)
