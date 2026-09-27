from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.companion.models.companion import CompanionDevice
from app.modules.companion.routers.companion import authenticated_device
from app.modules.voice.schemas.voice import VoiceResponseSchema
from app.modules.voice.services.speech_to_text import SpeechToTextError
from app.modules.voice.services.voice_service import (
    InvalidVoiceAudioError,
    voice_service,
)


router = APIRouter(prefix="/companion/voice", tags=["Energy Companion Voice"])


@router.post("", response_model=VoiceResponseSchema)
async def process_voice(
    request: Request,
    hermes_session_id: str | None = Query(default=None, max_length=64),
    db: Session = Depends(get_db),
    device: CompanionDevice = Depends(authenticated_device),
):
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type not in {"audio/wav", "audio/x-wav"}:
        raise HTTPException(status_code=415, detail="仅支持 PCM WAV 语音。")
    payload = await request.body()
    try:
        return await voice_service.process(db, device, payload, hermes_session_id)
    except InvalidVoiceAudioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SpeechToTextError as exc:
        public = "没听清，请再说一次。"
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": public},
        ) from exc
