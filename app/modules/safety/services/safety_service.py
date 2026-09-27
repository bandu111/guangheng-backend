from datetime import datetime, timezone
from math import isclose

from app.modules.device_registry.models.device import Device
from app.modules.device_registry.schemas.device_registry import DiscoveredDeviceSchema
from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.proposal.models.proposal import Proposal, ProposalStatus
from app.modules.safety.schemas.safety import SafetyCheckResponseSchema


class SafetyService:
    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def runtime_unavailable_result(
        *,
        device_found: bool,
        ha_request_succeeded: bool,
        runtime_found: bool,
        detail: str | None = None,
    ) -> SafetyCheckResponseSchema:
        checks = {
            "device_found": device_found,
            "ha_request_succeeded": ha_request_succeeded,
            "runtime_found": runtime_found,
        }
        if not ha_request_succeeded:
            reason_code = "HOME_ASSISTANT_REQUEST_FAILED"
            message = "Home Assistant runtime observation failed."
        else:
            reason_code = "RUNTIME_DEVICE_UNAVAILABLE"
            message = "The bound device is unavailable in the current HA observation."
        if detail:
            message = f"{message} {detail}"
        return SafetyCheckResponseSchema(
            passed=False,
            checks=checks,
            reason_code=reason_code,
            message=message,
        )

    def check(
        self,
        *,
        proposal: Proposal,
        device: Device,
        runtime: DiscoveredDeviceSchema,
    ) -> SafetyCheckResponseSchema:
        safety = device_discovery_service.get_safety_policy()
        control_config = device_discovery_service.get_control_config(
            runtime.profile_id, proposal.capability, runtime.source_mode
        )
        runtime_capability = next(
            (item for item in runtime.controls if item.name == proposal.capability),
            None,
        )

        now = datetime.now(timezone.utc)
        observed_at = self._parse_timestamp(runtime_capability.observed_at) if runtime_capability else None
        observation_age = (
            (now - observed_at).total_seconds() if observed_at is not None else None
        )
        reported_at = self._parse_timestamp(runtime_capability.last_reported) if runtime_capability else None
        entity_report_age = (
            (now - reported_at).total_seconds() if reported_at is not None else None
        )
        max_age = float(safety.get("max_state_age_seconds", 30))

        checks: dict[str, bool] = {
            "ha_request_succeeded": True,
            "proposal_approved": proposal.status == ProposalStatus.APPROVED,
            "observe_enabled": device.observe_enabled,
            "propose_enabled": device.propose_enabled,
            "control_enabled": device.control_enabled,
            "device_online": runtime.online,
            "capability_declared": control_config is not None,
            "capability_available": bool(runtime_capability and runtime_capability.available),
            "runtime_observation_fresh": bool(
                observation_age is not None and 0 <= observation_age <= max_age
            ),
        }

        if safety.get("require_device_online", True) is False:
            checks["device_online"] = True
        if safety.get("require_user_approval", True) is False:
            checks["proposal_approved"] = True

        if control_config is not None:
            checks["read_write"] = bool(
                runtime_capability
                and runtime_capability.access == "read_write"
                and control_config.get("access") == "read_write"
            )
            checks["verified"] = bool(
                runtime_capability
                and runtime_capability.verified is True
                and control_config.get("verified", False)
            )
            minimum = control_config.get("min")
            maximum = control_config.get("max")
            step = control_config.get("step")
            checks["within_range"] = (
                (minimum is None or proposal.target_value >= float(minimum))
                and (maximum is None or proposal.target_value <= float(maximum))
            )
            if step in (None, 0):
                checks["valid_step"] = True
            else:
                origin = float(minimum or 0)
                quotient = (proposal.target_value - origin) / float(step)
                checks["valid_step"] = isclose(
                    quotient, round(quotient), abs_tol=1e-8
                )
        else:
            checks.update(
                read_write=False,
                verified=False,
                within_range=False,
                valid_step=False,
            )

        if safety.get("require_verified_control", True) is False:
            checks["verified"] = True

        if safety.get("require_fresh_state", True) is False:
            checks["runtime_observation_fresh"] = True

        warnings: list[str] = []
        if reported_at is None:
            warnings.append("ENTITY_REPORT_TIMESTAMP_MISSING")
        elif entity_report_age is not None and entity_report_age > max_age:
            warnings.append("ENTITY_REPORT_TIMESTAMP_OLD")

        diagnostics = {
            "value_changed_at": runtime_capability.last_changed if runtime_capability else None,
            "entity_reported_at": runtime_capability.last_reported if runtime_capability else None,
            "entity_updated_at": runtime_capability.last_updated if runtime_capability else None,
            "observed_at": runtime_capability.observed_at if runtime_capability else None,
            "runtime_observation_age_seconds": observation_age,
            "entity_report_age_seconds": entity_report_age,
            "device_online": runtime.online,
            "capability_available": bool(runtime_capability and runtime_capability.available),
        }

        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            reason_codes = {
                "proposal_approved": "USER_APPROVAL_REQUIRED",
                "observe_enabled": "DEVICE_OBSERVE_DISABLED",
                "propose_enabled": "DEVICE_PROPOSE_DISABLED",
                "control_enabled": "DEVICE_CONTROL_DISABLED",
                "device_online": "DEVICE_OFFLINE",
                "capability_declared": "CAPABILITY_NOT_DECLARED",
                "capability_available": "CAPABILITY_UNAVAILABLE",
                "runtime_observation_fresh": "RUNTIME_OBSERVATION_STALE",
                "read_write": "CAPABILITY_NOT_WRITABLE",
                "verified": "CAPABILITY_NOT_VERIFIED",
                "within_range": "TARGET_OUT_OF_RANGE",
                "valid_step": "TARGET_STEP_INVALID",
            }
            return SafetyCheckResponseSchema(
                passed=False,
                checks=checks,
                reason_code=reason_codes[failed[0]],
                message="Blocked by safety checks: " + ", ".join(failed),
                warnings=warnings,
                diagnostics=diagnostics,
            )
        return SafetyCheckResponseSchema(
            passed=True,
            checks=checks,
            reason_code="SAFETY_CHECK_PASSED",
            message="All permission, capability, range, freshness and approval checks passed.",
            warnings=warnings,
            diagnostics=diagnostics,
        )


safety_service = SafetyService()
