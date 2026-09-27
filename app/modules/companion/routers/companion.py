import asyncio
from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.modules.action_set.services.action_set_service import (
    ActionSetNotFoundError,
    InvalidActionSetStateError,
    action_set_service,
)
from app.modules.action_set.repositories.action_set_repository import (
    action_set_repository,
)
from app.modules.companion.models.companion import CompanionDevice
from app.modules.companion.schemas.companion import (
    CompanionApprovalRequest,
    CompanionDeviceCodeRequest,
    CompanionDeviceCodeResponse,
    CompanionDeviceSchema,
    CompanionPairingConfirmRequest,
    CompanionPairingPollRequest,
    CompanionPairingPollResponse,
    CompanionSnapshotSchema,
)
from app.modules.companion.services.companion_service import companion_service
from app.modules.energy_state.services.energy_state_service import energy_state_service


router = APIRouter(prefix="/companion", tags=["Energy Companion"])


def authenticated_device(
    db: Session = Depends(get_db),
    device_uid: str = Header(alias="X-Companion-Device-Id"),
    credential: str = Header(alias="X-Companion-Credential"),
) -> CompanionDevice:
    return companion_service.authenticate(db, device_uid, credential)


async def build_snapshot(
    db: Session, device: CompanionDevice
) -> CompanionSnapshotSchema:
    energy = await energy_state_service.get_energy_state(db)
    pending = action_set_service.pending(db)
    latest = action_set_repository.latest(db)
    current = action_set_service.response(db, latest) if latest is not None else None
    challenge = companion_service.challenge_for_pending(db, device) if pending else None
    return CompanionSnapshotSchema(
        observed_at=datetime.utcnow(),
        energy=energy.model_dump(mode="json"),
        pending_action_set=pending.model_dump(mode="json") if pending else None,
        current_action_set=current.model_dump(mode="json") if current else None,
        approval_challenge=challenge,
    )


@router.post("/pairing/device-code", response_model=CompanionDeviceCodeResponse)
def create_device_code(
    body: CompanionDeviceCodeRequest, db: Session = Depends(get_db)
):
    return companion_service.create_device_code(db, body.device_uid, body.display_name)


@router.post("/pairing/confirm", response_model=CompanionDeviceSchema)
def confirm_pairing(
    body: CompanionPairingConfirmRequest, db: Session = Depends(get_db)
):
    return companion_service.confirm_pairing(db, body.code)


@router.post("/pairing/poll", response_model=CompanionPairingPollResponse)
def poll_pairing(body: CompanionPairingPollRequest, db: Session = Depends(get_db)):
    return companion_service.poll_pairing(db, body.code, body.poll_token)


@router.get("/devices", response_model=list[CompanionDeviceSchema])
def list_devices(db: Session = Depends(get_db)):
    return companion_service.list_devices(db)


@router.post("/devices/{device_uid}/revoke", response_model=CompanionDeviceSchema)
def revoke_device(device_uid: str, db: Session = Depends(get_db)):
    return companion_service.revoke(db, device_uid)


@router.get("/snapshot", response_model=CompanionSnapshotSchema)
async def get_snapshot(
    db: Session = Depends(get_db),
    device: CompanionDevice = Depends(authenticated_device),
):
    return await build_snapshot(db, device)


@router.post("/action-sets/{action_set_id}/approve")
def approve_from_companion(
    action_set_id: int,
    body: CompanionApprovalRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    device: CompanionDevice = Depends(authenticated_device),
):
    companion_service.consume_challenge(
        db, device, action_set_id, body.nonce, body.action_set_version
    )
    try:
        result = action_set_service.approve(db, action_set_id)
    except ActionSetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidActionSetStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(action_set_service.execute_approved, action_set_id)
    return result


@router.websocket("/ws")
async def companion_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        if auth.get("type") != "auth":
            await websocket.close(code=4401, reason="authentication required")
            return
        with SessionLocal() as db:
            device = companion_service.authenticate(
                db, str(auth.get("device_id", "")), str(auth.get("credential", ""))
            )
            await websocket.send_json({"type": "authenticated"})
            while True:
                snapshot = await build_snapshot(db, device)
                await websocket.send_json(
                    {"type": "snapshot", "data": snapshot.model_dump(mode="json")}
                )
                try:
                    message = await asyncio.wait_for(websocket.receive_json(), timeout=5)
                    if message.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except TimeoutError:
                    pass
                db.expire_all()
    except (WebSocketDisconnect, TimeoutError):
        return
    except HTTPException:
        await websocket.close(code=4401, reason="invalid device credential")
