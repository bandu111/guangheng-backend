import asyncio
import hashlib
import io
import time
import wave
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.action_set.services.action_set_service import action_set_service
from app.modules.companion.models.companion import CompanionDevice
from app.modules.hermes.schemas.hermes import AgentIntent, AgentResponseStatus
from app.modules.hermes.services.agent_service import agent_service
from app.modules.voice.models.voice_session import VoiceSession
from app.modules.voice.repositories.voice_repository import voice_repository
from app.modules.voice.schemas.voice import (
    VoiceIntent,
    VoiceResponseSchema,
    VoiceTimingSchema,
)
from app.modules.voice.services.speech_to_text import (
    SpeechToTextError,
    SpeechToTextProvider,
    create_speech_provider,
)


class InvalidVoiceAudioError(ValueError):
    pass


def inspect_wav(payload: bytes) -> float:
    if len(payload) > settings.voice_max_audio_bytes:
        raise InvalidVoiceAudioError("语音数据超过大小限制。")
    try:
        with wave.open(io.BytesIO(payload), "rb") as audio:
            if (
                audio.getnchannels() != 1
                or audio.getsampwidth() != 2
                or audio.getframerate() != 16000
                or audio.getcomptype() != "NONE"
            ):
                raise InvalidVoiceAudioError(
                    "仅支持 16 kHz、16-bit、单声道 PCM WAV。"
                )
            duration = audio.getnframes() / audio.getframerate()
    except (wave.Error, EOFError) as exc:
        raise InvalidVoiceAudioError("语音数据不是有效的 PCM WAV。") from exc
    if duration < 0.25 or duration > settings.voice_max_duration_seconds:
        raise InvalidVoiceAudioError("语音时长不在允许范围内。")
    return duration


class VoiceService:
    def __init__(self, provider: SpeechToTextProvider | None = None) -> None:
        self._provider = provider

    @property
    def provider(self) -> SpeechToTextProvider:
        if self._provider is None:
            self._provider = create_speech_provider()
        return self._provider

    async def process(
        self,
        db: Session,
        device: CompanionDevice,
        payload: bytes,
        hermes_session_id: str | None = None,
    ) -> VoiceResponseSchema:
        started = time.perf_counter()
        duration = inspect_wav(payload)
        row = voice_repository.save(
            db,
            VoiceSession(
                id=str(uuid4()),
                companion_device_id=device.id,
                audio_sha256=hashlib.sha256(payload).hexdigest(),
                audio_duration_seconds=duration,
                asr_provider=self.provider.name,
                status="TRANSCRIBING",
            ),
        )
        asr_started = time.perf_counter()
        try:
            transcript = await asyncio.wait_for(
                asyncio.to_thread(self.provider.transcribe, payload),
                timeout=settings.voice_asr_timeout_seconds,
            )
        except TimeoutError as exc:
            row.status = "FAILED"
            row.error_code = "ASR_TIMEOUT"
            row.completed_at = datetime.utcnow()
            voice_repository.save(db, row)
            raise SpeechToTextError("Speech recognition timed out.", "ASR_TIMEOUT") from exc
        except SpeechToTextError as exc:
            row.status = "FAILED"
            row.error_code = exc.code
            row.completed_at = datetime.utcnow()
            voice_repository.save(db, row)
            raise
        except Exception as exc:
            row.status = "FAILED"
            row.error_code = "ASR_UNAVAILABLE"
            row.completed_at = datetime.utcnow()
            voice_repository.save(db, row)
            raise SpeechToTextError(
                "Speech recognition is unavailable.", "ASR_UNAVAILABLE"
            ) from exc
        asr_ms = int((time.perf_counter() - asr_started) * 1000)
        if not transcript.text.strip():
            row.status = "FAILED"
            row.error_code = "ASR_EMPTY_TRANSCRIPT"
            row.completed_at = datetime.utcnow()
            voice_repository.save(db, row)
            raise SpeechToTextError(
                "Speech recognition returned no transcript.",
                "ASR_EMPTY_TRANSCRIPT",
            )
        row.transcript = transcript.text
        row.status = "UNDERSTANDING"
        row.asr_latency_ms = asr_ms
        voice_repository.save(db, row)

        intent = self._preflight_intent(transcript.text)
        pending = action_set_service.pending(db)
        guarded_intent = intent in {
            VoiceIntent.APPROVAL_INTENT,
            VoiceIntent.REJECT_INTENT,
            VoiceIntent.AMBIGUOUS,
        }
        agent = None
        hermes_ms = 0
        if not guarded_intent:
            hermes_started = time.perf_counter()
            try:
                agent = await agent_service.chat(
                    db=db, session_id=hermes_session_id, message=transcript.text
                )
            except Exception:
                row.status = "FAILED"
                row.error_code = "HERMES_UNAVAILABLE"
                row.completed_at = datetime.utcnow()
                voice_repository.save(db, row)
                total_ms = int((time.perf_counter() - started) * 1000)
                return VoiceResponseSchema(
                    voice_session_id=row.id,
                    transcript=transcript.text,
                    intent=intent,
                    answer="智能服务暂时不可用，未创建或执行任何设备操作。",
                    status="FAILED",
                    requires_touch_approval=False,
                    clarification=None,
                    pending_action_set=None,
                    hermes_session_id=None,
                    hermes_message_id=None,
                    tool_names=[],
                    asr_provider=self.provider.name,
                    raw_audio_persisted=False,
                    timing=VoiceTimingSchema(
                        audio_duration_ms=int(duration * 1000),
                        asr_latency_ms=asr_ms,
                        hermes_latency_ms=0,
                        total_latency_ms=total_ms,
                    ),
                    error_code=row.error_code,
                )
            hermes_ms = int((time.perf_counter() - hermes_started) * 1000)
            intent = self._final_intent(transcript.text, intent, agent.intent)
        requires_touch = intent in {
            VoiceIntent.APPROVAL_INTENT,
            VoiceIntent.REJECT_INTENT,
        } or pending is not None
        clarification = (
            "请在屏幕上选择具体设备后再继续。"
            if intent == VoiceIntent.AMBIGUOUS
            else None
        )
        answer = agent.answer if agent is not None else None
        if intent == VoiceIntent.APPROVAL_INTENT:
            answer = "已为你显示当前方案。语音不会执行设备操作，请在终端上长按确认。"
        elif intent == VoiceIntent.REJECT_INTENT:
            answer = "已识别暂不执行意图，请在终端上确认取消，语音不会直接改变方案状态。"
        elif intent == VoiceIntent.AMBIGUOUS:
            answer = clarification

        row.intent = intent.value
        row.status = (
            "COMPLETED"
            if agent is None or agent.status != AgentResponseStatus.FAILED
            else "FAILED"
        )
        row.hermes_session_id = agent.session_id if agent is not None else None
        row.hermes_message_id = agent.message_id if agent is not None else None
        row.hermes_latency_ms = hermes_ms
        row.error_code = agent.error.code if agent is not None and agent.error else None
        row.completed_at = datetime.utcnow()
        voice_repository.save(db, row)
        total_ms = int((time.perf_counter() - started) * 1000)
        return VoiceResponseSchema(
            voice_session_id=row.id,
            transcript=transcript.text,
            intent=intent,
            answer=answer,
            status=row.status,
            requires_touch_approval=requires_touch,
            clarification=clarification,
            pending_action_set=(
                pending.model_dump(mode="json") if pending is not None else None
            ),
            hermes_session_id=agent.session_id if agent is not None else None,
            hermes_message_id=agent.message_id if agent is not None else None,
            tool_names=[item.tool_name for item in agent.tools] if agent is not None else [],
            asr_provider=self.provider.name,
            raw_audio_persisted=False,
            timing=VoiceTimingSchema(
                audio_duration_ms=int(duration * 1000),
                asr_latency_ms=asr_ms,
                hermes_latency_ms=hermes_ms,
                total_latency_ms=total_ms,
            ),
            error_code=row.error_code,
        )

    @staticmethod
    def _preflight_intent(text: str) -> VoiceIntent:
        normalized = text.replace(" ", "")
        if any(word in normalized for word in ("执行刚才", "确认执行", "批准方案")):
            return VoiceIntent.APPROVAL_INTENT
        if any(word in normalized for word in ("暂不执行", "拒绝方案", "取消方案")):
            return VoiceIntent.REJECT_INTENT
        if "那个插座" in normalized or "这个插座" in normalized:
            return VoiceIntent.AMBIGUOUS
        if any(word in normalized for word in ("如果", "会怎么样", "假如")):
            return VoiceIntent.WHAT_IF
        if any(word in normalized for word in ("切到备电", "切换策略", "改成备电")):
            return VoiceIntent.STRATEGY_CHANGE_PROPOSAL
        if any(word in normalized for word in ("所有电池", "别把太阳能送回", "零回流")):
            return VoiceIntent.MULTI_DEVICE_GOAL
        if any(word in normalized for word in ("调成", "设为", "关闭插座", "打开插座")):
            return VoiceIntent.DEVICE_CONTROL_PROPOSAL
        if "为什么" in normalized:
            return VoiceIntent.EXPLAIN
        if any(word in normalized for word in ("方案", "建议")):
            return VoiceIntent.EXPLAIN_PROPOSAL
        if any(word in normalized for word in ("多少电", "能源情况", "现在用电", "电池电量")):
            return VoiceIntent.READ_STATUS
        return VoiceIntent.UNKNOWN

    @staticmethod
    def _final_intent(
        text: str, preflight: VoiceIntent, agent_intent: AgentIntent
    ) -> VoiceIntent:
        if preflight != VoiceIntent.UNKNOWN:
            return preflight
        if agent_intent == AgentIntent.ENERGY_STATUS:
            return VoiceIntent.READ_STATUS
        if agent_intent == AgentIntent.ENERGY_DECISION:
            return VoiceIntent.WHAT_IF
        if agent_intent == AgentIntent.PROPOSAL_REQUEST:
            return VoiceIntent.EXPLAIN_PROPOSAL
        return VoiceIntent.UNKNOWN


voice_service = VoiceService()
