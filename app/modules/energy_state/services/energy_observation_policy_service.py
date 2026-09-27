from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError


BASE_DIR = Path(__file__).resolve().parents[4]
POLICY_PATH = BASE_DIR / "config" / "energy_observation_policy.yaml"


class EnergyObservationPolicy(BaseModel):
    version: str = "v1"
    enabled: bool = True
    interval_seconds: int = Field(default=300, ge=30)
    initial_delay_seconds: int = Field(default=5, ge=1)
    retention_days: int = Field(default=400, ge=1)
    max_hold_seconds: int = Field(default=900, ge=30)


def load_energy_observation_policy() -> EnergyObservationPolicy:
    try:
        with POLICY_PATH.open("r", encoding="utf-8") as file:
            return EnergyObservationPolicy.model_validate(yaml.safe_load(file) or {})
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise RuntimeError("Energy observation policy is invalid.") from exc


energy_observation_policy = load_energy_observation_policy()
