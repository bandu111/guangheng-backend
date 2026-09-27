from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    # Application
    app_name: str = "GuangHeng Server"
    app_version: str = "1.6.0"
    environment: str = "development"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = True

    # Home Assistant
    ha_url: str
    ha_token: str

    # External Weather Runtime Context
    weather_provider: str = "open_meteo"
    weather_base_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = 10.0
    weather_cache_seconds: int = 300

    # Official Hermes Agent API Server (local gateway access, not DeepSeek)
    hermes_base_url: str = "http://127.0.0.1:8642"
    hermes_api_key: str = ""
    hermes_model: str = "hermes-agent"
    hermes_timeout_seconds: float = 120.0

    # Companion speech gateway. Raw audio is processed ephemerally and is not
    # persisted. The local provider avoids placing any third-party key on the
    # ESP32-S3.
    voice_asr_provider: str = "faster_whisper"
    voice_asr_model: str = "small"
    voice_asr_device: str = "cpu"
    voice_asr_compute_type: str = "int8"
    voice_asr_language: str = "zh"
    voice_max_audio_bytes: int = 512_000
    voice_max_duration_seconds: float = 12.0
    voice_asr_timeout_seconds: float = 45.0

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
