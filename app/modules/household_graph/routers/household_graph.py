from fastapi import APIRouter

from app.modules.household_graph.schemas.household_graph import HouseholdEnergyGraphSchema
from app.modules.household_graph.services.household_graph_service import household_graph_service


router = APIRouter(prefix="/household-energy", tags=["Household Energy Graph"])


@router.get("/graph", response_model=HouseholdEnergyGraphSchema)
async def get_household_energy_graph():
    return await household_graph_service.get_current()

