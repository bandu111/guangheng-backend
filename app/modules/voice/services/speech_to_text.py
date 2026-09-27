import os
import tempfile
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


class SpeechToTextError(RuntimeError):
    def __init__(self, message: str, code: str = "ASR_FAILED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    language: str | None = None
    language_probability: float | None = None


class SpeechToTextProvider(Protocol):
    name: str

    def transcribe(self, wav_bytes: bytes) -> TranscriptResult: ...


class FasterWhisperProvider:
    name = "faster_whisper"

    def __init__(self) -> None:
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise SpeechToTextError(
                    "Speech provider is not installed.", "ASR_PROVIDER_UNAVAILABLE"
                ) from exc
            self._model = WhisperModel(
                settings.voice_asr_model,
                device=settings.voice_asr_device,
                compute_type=settings.voice_asr_compute_type,
            )
        return self._model

    def transcribe(self, wav_bytes: bytes) -> TranscriptResult:
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                handle.write(wav_bytes)
                path = handle.name
            segments, info = self._get_model().transcribe(
                path,
                language=settings.voice_asr_language or None,
                vad_filter=True,
                beam_size=5,
                condition_on_previous_text=False,
            )
            text = "".join(item.text for item in segments).strip()
            if not text:
                raise SpeechToTextError("No speech was recognized.", "ASR_NO_SPEECH")
            return TranscriptResult(
                text=text,
                language=getattr(info, "language", None),
                language_probability=getattr(info, "language_probability", None),
            )
        except SpeechToTextError:
            raise
        except Exception as exc:
            raise SpeechToTextError("Speech recognition failed.") from exc
        finally:
            if path:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass


def create_speech_provider() -> SpeechToTextProvider:
    if settings.voice_asr_provider == "faster_whisper":
        return FasterWhisperProvider()
    raise SpeechToTextError(
        "No production speech provider is configured.", "ASR_PROVIDER_UNAVAILABLE"
    )
