from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.station.schemas.station import StationSummarySchema
from app.modules.station.services.station_service import station_service


router = APIRouter(prefix="/stations", tags=["Station"])


@router.get("/current", response_model=StationSummarySchema)
async def get_current_station(db: Session = Depends(get_db)):
    return await station_service.get_current(db)

