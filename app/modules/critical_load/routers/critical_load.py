from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.critical_load.schemas.critical_load import (
    CriticalLoadCreateSchema,
    CriticalLoadListSchema,
    CriticalLoadSchema,
    CriticalLoadUpdateSchema,
)
from app.modules.critical_load.services.critical_load_service import (
    CriticalLoadNotFoundError,
    critical_load_service,
)


router = APIRouter(prefix="/critical-loads", tags=["Critical Loads"])


@router.get("", response_model=CriticalLoadListSchema)
def list_critical_loads(db: Session = Depends(get_db)):
    return critical_load_service.list(db)


@router.post("", response_model=CriticalLoadSchema, status_code=status.HTTP_201_CREATED)
def create_critical_load(request: CriticalLoadCreateSchema, db: Session = Depends(get_db)):
    return critical_load_service.create(db, request)


@router.patch("/{load_id}", response_model=CriticalLoadSchema)
def update_critical_load(load_id: int, request: CriticalLoadUpdateSchema, db: Session = Depends(get_db)):
    try:
        return critical_load_service.update(db, load_id, request)
    except CriticalLoadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{load_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_critical_load(load_id: int, db: Session = Depends(get_db)):
    try:
        critical_load_service.delete(db, load_id)
    except CriticalLoadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)

