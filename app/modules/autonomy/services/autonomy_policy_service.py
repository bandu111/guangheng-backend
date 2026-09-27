from dataclasses import dataclass
from pathlib import Path

import yaml

from app.core.database import BASE_DIR


@dataclass(frozen=True)
class SchedulerPolicy:
    enabled: bool
    interval_seconds: int
    initial_delay_seconds: int


@dataclass(frozen=True)
class DeduplicationPolicy:
    pending_proposal_reuse: bool
    notification_reuse: bool
    rejected_reproposal_cooldown_minutes: int


@dataclass(frozen=True)
class RuntimePolicy:
    run_timeout_seconds: int


@dataclass(frozen=True)
class AutonomyPolicy:
    version: str
    default_level: str
    scheduler: SchedulerPolicy
    deduplication: DeduplicationPolicy
    runtime: RuntimePolicy


def load_autonomy_policy(path: Path | None = None) -> AutonomyPolicy:
    policy_path = path or BASE_DIR / "config" / "autonomy_policy.yaml"
    with policy_path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    scheduler = value["scheduler"]
    deduplication = value["deduplication"]
    runtime = value["runtime"]
    return AutonomyPolicy(
        version=str(value["version"]),
        default_level=str(value.get("default_level", "CONFIRM")).upper(),
        scheduler=SchedulerPolicy(
            enabled=bool(scheduler["enabled"]),
            interval_seconds=max(1, int(scheduler["interval_seconds"])),
            initial_delay_seconds=max(1, int(scheduler["initial_delay_seconds"])),
        ),
        deduplication=DeduplicationPolicy(
            pending_proposal_reuse=bool(
                deduplication["pending_proposal_reuse"]
            ),
            notification_reuse=bool(deduplication["notification_reuse"]),
            rejected_reproposal_cooldown_minutes=max(
                0,
                int(deduplication["rejected_reproposal_cooldown_minutes"]),
            ),
        ),
        runtime=RuntimePolicy(
            run_timeout_seconds=max(1, int(runtime["run_timeout_seconds"]))
        ),
    )


autonomy_policy = load_autonomy_policy()
