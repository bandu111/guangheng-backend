from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.device_registry.schemas.device_registry import (
    BatteryInsightSchema,
    DeviceBindRequestSchema,
    DeviceControlProposalRequestSchema,
    DeviceDiscoveryResponseSchema,
    DeviceListResponseSchema,
    DeviceProfileCatalogSchema,
    DeviceResponseSchema,
    DeviceStateResponseSchema,
    DeviceUpdateRequestSchema,
    SmartPlugProposalRequestSchema,
)
from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.device_registry.services.device_registry_service import (
    DeviceNotFoundError,
    device_registry_service,
)
from app.modules.device_registry.repositories.device_repository import device_repository
from app.modules.proposal.schemas.proposal import ProposalResponseSchema
from app.modules.proposal.services.proposal_service import (
    ProposalNotFoundError,
    ProposalPermissionError,
    RuntimeUnavailableError,
    proposal_service,
)


router = APIRouter(
    prefix="/devices",
    tags=["Device Registry"],
)


@router.get(
    "/discover",
    response_model=DeviceDiscoveryResponseSchema,
)
async def discover_devices():
    return await device_discovery_service.discover_devices()


@router.get("/profiles/catalog", response_model=DeviceProfileCatalogSchema)
def get_profile_catalog():
    return device_discovery_service.get_catalog()


@router.get("/discover/bound", response_model=DeviceDiscoveryResponseSchema)
async def discover_devices_with_bindings(db: Session = Depends(get_db)):
    discovery = await device_discovery_service.discover_devices()
    bound = {
        device.source_device_id: device
        for device in device_repository.get_all(db)
    }
    for runtime in discovery.devices:
        device = bound.get(runtime.device_id)
        if device is not None:
            runtime.bound_device_id = device.id
            runtime.control_enabled = device.control_enabled
    return discovery


@router.post(
    "/{device_id}/switch-proposals",
    response_model=ProposalResponseSchema,
)
async def create_switch_proposal(
    device_id: int,
    request: SmartPlugProposalRequestSchema,
    db: Session = Depends(get_db),
):
    try:
        return await proposal_service.create_smart_plug_proposal(
            db, device_id, request.target_on
        )
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProposalPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{device_id}/control-proposals",
    response_model=ProposalResponseSchema,
)
async def create_device_control_proposal(
    device_id: int,
    request: DeviceControlProposalRequestSchema,
    db: Session = Depends(get_db),
):
    try:
        return await proposal_service.create_device_control_proposal(
            db, device_id, request.capability, request.target_value
        )
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProposalPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{device_id}/bind",
    response_model=DeviceResponseSchema,
)
async def bind_device(
    device_id: str,
    request: DeviceBindRequestSchema,
    db: Session = Depends(get_db),
):
    try:
        return await device_registry_service.bind_device(
            db=db,
            source_device_id=device_id,
            request=request,
        )

    except DeviceNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=DeviceListResponseSchema,
)
async def get_devices(
    db: Session = Depends(get_db),
):
    devices = device_registry_service.get_bound_devices(
        db=db,
    )

    return DeviceListResponseSchema(
        count=len(devices),
        devices=devices,
    )

@router.get(
    "/{device_id}/state",
    response_model=DeviceStateResponseSchema,
)
async def get_device_state(
    device_id: int,
    db: Session = Depends(get_db),
):
    try:
        return await device_registry_service.get_device_state(
            db=db,
            device_id=device_id,
        )

    except DeviceNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get(
    "/{device_id}/battery-insight",
    response_model=BatteryInsightSchema,
)
async def get_battery_insight(
    device_id: int,
    db: Session = Depends(get_db),
):
    try:
        return await device_registry_service.get_battery_insight(db, device_id)
    except DeviceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch(
    "/{device_id}",
    response_model=DeviceResponseSchema,
)
async def update_device(
    device_id: int,
    request: DeviceUpdateRequestSchema,
    db: Session = Depends(get_db),
):
    try:
        return device_registry_service.update_device(
            db=db,
            device_id=device_id,
            request=request,
        )
    except DeviceNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
