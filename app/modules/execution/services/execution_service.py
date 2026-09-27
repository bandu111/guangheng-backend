import asyncio
from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.device_registry.schemas.device_registry import DiscoveredDeviceSchema
from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.execution.models.execution import Execution, ExecutionStatus
from app.modules.execution.repositories.execution_repository import execution_repository
from app.modules.home_assistant.services.home_assistant_service import (
    home_assistant_service,
)
from app.modules.proposal.models.proposal import Proposal, ProposalStatus
from app.modules.proposal.repositories.proposal_repository import proposal_repository


class UnsupportedExecutionError(RuntimeError):
    pass


class ExecutionService:
    READBACK_TIMEOUT_SECONDS = 10
    READBACK_INTERVAL_SECONDS = 1

    @staticmethod
    def _switch_value(value: object) -> float | None:
        normalized = str(value).strip().lower()
        if normalized in {"on", "connected", "enabled", "true", "1"}:
            return 1.0
        if normalized in {"off", "disconnected", "disabled", "false", "0"}:
            return 0.0
        return None

    @staticmethod
    def _select_value(value: object, options: dict) -> float | None:
        for code, option in options.items():
            if str(value).strip().lower() == str(option).strip().lower():
                return float(code)
        return None

    async def execute(
        self,
        *,
        db: Session,
        proposal: Proposal,
        runtime: DiscoveredDeviceSchema,
    ) -> Execution:
        if proposal.capability not in {
            "backup_reserve",
            "charging_limit",
            "discharge_limit",
            "battery_power_setpoint",
            "operating_mode",
            "battery_power_direction",
            "power_switch",
        }:
            raise UnsupportedExecutionError(
                f"Unsupported verified capability: {proposal.capability}"
            )

        capability = next(
            item for item in runtime.controls if item.name == proposal.capability
        )
        domain = capability.entity_id.split(".", 1)[0]
        if domain not in {"number", "select", "switch"}:
            raise UnsupportedExecutionError(f"Unsupported HA control domain: {domain}")
        config = device_discovery_service.get_control_config(
            runtime.profile_id, proposal.capability, runtime.source_mode
        ) or {}
        options = config.get("options", {})
        is_switch = domain == "switch"
        is_select = domain == "select"
        selected_option = None
        if is_select:
            selected_option = options.get(int(proposal.target_value))
            if selected_option is None:
                selected_option = options.get(str(int(proposal.target_value)))
            if selected_option is None:
                raise UnsupportedExecutionError("Select target is not mapped by the profile.")
        execution = execution_repository.create(
            db,
            Execution(
                proposal_id=proposal.id,
                device_id=proposal.device_id,
                capability=proposal.capability,
                ha_entity_id=capability.entity_id,
                requested_value=proposal.target_value,
                status=ExecutionStatus.EXECUTING,
                ha_domain=domain,
                ha_service=(
                    "turn_on" if proposal.target_value >= 0.5 else "turn_off"
                )
                if is_switch
                else ("select_option" if is_select else "set_value"),
            ),
        )

        try:
            await home_assistant_service.call_service(
                domain=execution.ha_domain,
                service=execution.ha_service,
                entity_id=execution.ha_entity_id,
                service_data=(
                    {}
                    if is_switch
                    else ({"option": selected_option} if is_select else {"value": execution.requested_value})
                ),
            )
            execution.executed_at = datetime.utcnow()

            step = float(capability.step or 0)
            tolerance = max(0.01, step / 2)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self.READBACK_TIMEOUT_SECONDS

            while loop.time() <= deadline:
                state = await home_assistant_service.get_state(execution.ha_entity_id)
                if is_switch:
                    readback = self._switch_value(state.state)
                elif is_select:
                    readback = self._select_value(state.state, options)
                else:
                    try:
                        readback = float(state.state)
                    except (TypeError, ValueError):
                        readback = None

                execution.readback_value = readback
                if (
                    readback is not None
                    and abs(readback - execution.requested_value) <= tolerance
                ):
                    execution.status = ExecutionStatus.SUCCEEDED
                    execution.verified_at = datetime.utcnow()
                    execution.completed_at = datetime.utcnow()
                    proposal.status = ProposalStatus.SUCCEEDED
                    execution_repository.save(db, execution)
                    proposal_repository.save(db, proposal)
                    return execution

                if loop.time() < deadline:
                    await asyncio.sleep(self.READBACK_INTERVAL_SECONDS)

            execution.status = ExecutionStatus.FAILED
            execution.error_code = "READBACK_TIMEOUT"
            execution.error_message = (
                "Home Assistant did not report the requested value within 10 seconds."
            )
        except Exception as exc:
            execution.status = ExecutionStatus.FAILED
            execution.error_code = "HA_SERVICE_ERROR"
            execution.error_message = str(exc)

        execution.completed_at = datetime.utcnow()
        proposal.status = ProposalStatus.FAILED
        proposal.error_code = execution.error_code
        proposal.error_message = execution.error_message
        execution_repository.save(db, execution)
        proposal_repository.save(db, proposal)
        return execution


execution_service = ExecutionService()
