import io
import importlib
import wave
from types import SimpleNamespace

import pytest

from app.modules.voice.models.voice_session import VoiceSession
from app.modules.voice.schemas.voice import VoiceIntent
from app.modules.voice.services.speech_to_text import (
    SpeechToTextError,
    TranscriptResult,
)
from app.modules.voice.services.voice_service import (
    InvalidVoiceAudioError,
    VoiceService,
    inspect_wav,
)


voice_service_module = importlib.import_module(
    "app.modules.voice.services.voice_service"
)


def _wav(seconds: float = 1.0, rate: int = 16000, channels: int = 1) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00\x00" * int(rate * seconds) * channels)
    return output.getvalue()


def test_voice_accepts_only_real_frozen_pcm_contract():
    assert inspect_wav(_wav()) == pytest.approx(1.0)
    with pytest.raises(InvalidVoiceAudioError):
        inspect_wav(_wav(rate=8000))
    with pytest.raises(InvalidVoiceAudioError):
        inspect_wav(_wav(channels=2))
    with pytest.raises(InvalidVoiceAudioError):
        inspect_wav(b"not-a-wave")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("家里现在用了多少电？", VoiceIntent.READ_STATUS),
        ("为什么现在在往电网送电？", VoiceIntent.EXPLAIN),
        ("如果切到备电会怎么样？", VoiceIntent.WHAT_IF),
        ("切到备电模式", VoiceIntent.STRATEGY_CHANGE_PROPOSAL),
        ("把 Solarbank Max AC 调成 1kW 充电", VoiceIntent.DEVICE_CONTROL_PROPOSAL),
        ("尽量别把太阳能送回电网", VoiceIntent.MULTI_DEVICE_GOAL),
        ("执行刚才那个方案", VoiceIntent.APPROVAL_INTENT),
        ("暂不执行", VoiceIntent.REJECT_INTENT),
        ("把那个插座关掉", VoiceIntent.AMBIGUOUS),
    ],
)
def test_voice_intent_safety_matrix(text, expected):
    assert VoiceService._preflight_intent(text) == expected


def test_voice_approval_intent_is_classification_not_approval():
    # This layer has no approve/execute dependency. It can only instruct the
    # ESP32-S3 to show the real pending Action Set for physical long press.
    assert VoiceService._preflight_intent("确认执行刚才的方案") == VoiceIntent.APPROVAL_INTENT


class _TranscriptProvider:
    name = "test-real-contract"

    def __init__(self, text: str) -> None:
        self.text = text

    def transcribe(self, wav_bytes: bytes) -> TranscriptResult:
        assert wav_bytes.startswith(b"RIFF")
        return TranscriptResult(text=self.text, language="zh")


class _FailingProvider:
    name = "test-real-contract"

    def transcribe(self, wav_bytes: bytes) -> TranscriptResult:
        raise SpeechToTextError("unavailable", "ASR_UNAVAILABLE")


def _repository_without_audio(monkeypatch):
    saved = []

    def save(_db, value):
        saved.append(value)
        return value

    monkeypatch.setattr(voice_service_module.voice_repository, "save", save)
    monkeypatch.setattr(
        voice_service_module.action_set_service, "pending", lambda _db: None
    )
    return saved


@pytest.mark.parametrize("text", ["确认执行刚才的方案", "暂不执行", "把那个插座关掉"])
def test_guarded_voice_intents_never_call_hermes_or_mutate(monkeypatch, text):
    _repository_without_audio(monkeypatch)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("Guarded voice intent must not reach Hermes")

    monkeypatch.setattr(voice_service_module.agent_service, "chat", forbidden)
    service = VoiceService(_TranscriptProvider(text))
    response = __import__("asyncio").run(
        service.process(None, SimpleNamespace(id=7), _wav())
    )
    assert response.tool_names == []
    assert response.hermes_message_id is None
    assert response.intent in {
        VoiceIntent.APPROVAL_INTENT,
        VoiceIntent.REJECT_INTENT,
        VoiceIntent.AMBIGUOUS,
    }
    assert response.raw_audio_persisted is False


def test_asr_failure_stops_before_hermes_and_records_only_metadata(monkeypatch):
    saved = _repository_without_audio(monkeypatch)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("ASR failure must stop before Hermes")

    monkeypatch.setattr(voice_service_module.agent_service, "chat", forbidden)
    service = VoiceService(_FailingProvider())
    with pytest.raises(SpeechToTextError):
        __import__("asyncio").run(
            service.process(None, SimpleNamespace(id=7), _wav())
        )
    assert saved[-1].status == "FAILED"
    assert saved[-1].error_code == "ASR_UNAVAILABLE"
    assert "audio" not in {column.name for column in VoiceSession.__table__.columns}


def test_hermes_failure_is_structured_and_creates_no_fake_result(monkeypatch):
    _repository_without_audio(monkeypatch)

    async def unavailable(*_args, **_kwargs):
        raise RuntimeError("gateway unavailable")

    monkeypatch.setattr(voice_service_module.agent_service, "chat", unavailable)
    service = VoiceService(_TranscriptProvider("家里的能源情况怎么样"))
    response = __import__("asyncio").run(
        service.process(None, SimpleNamespace(id=7), _wav())
    )
    assert response.status == "FAILED"
    assert response.error_code == "HERMES_UNAVAILABLE"
    assert response.tool_names == []
    assert response.pending_action_set is None
    assert "未创建或执行" in response.answer
