from fastapi import APIRouter

from app.modules.report.schemas.energy_report import EnergyReportResponseSchema
from app.modules.report.services.energy_report_service import energy_report_service


router = APIRouter(prefix="/report", tags=["Energy Report"])


@router.get("/energy", response_model=EnergyReportResponseSchema)
async def get_energy_report():
    return await energy_report_service.get_report()
