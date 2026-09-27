from fastapi import APIRouter

from app.modules.tariff.schemas.tariff import TariffContextSchema
from app.modules.tariff.services.tariff_service import tariff_service


router = APIRouter(prefix="/tariff", tags=["Tariff Context"])


@router.get("", response_model=TariffContextSchema)
def get_tariff():
    return tariff_service.get_context()
