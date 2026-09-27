from sqlalchemy.orm import Session

from app.modules.device_registry.repositories.device_repository import device_repository
from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.execution.services.execution_service import execution_service
from app.modules.optimizer.services.optimizer_evaluation_service import (
    optimizer_evaluation_service,
)
from app.modules.optimizer.schemas.optimizer_v2 import OptimizationDecisionV2Schema
from app.modules.proposal.models.proposal import Proposal, ProposalStatus
from app.modules.proposal.repositories.proposal_repository import proposal_repository
from app.modules.proposal.schemas.proposal import (
    ProposalActionResponseSchema,
    ProposalGenerationResponseSchema,
)
from app.modules.safety.services.safety_service import safety_service
from app.modules.strategy.models.strategy import StrategyMode


class ProposalNotFoundError(Exception):
    pass


class InvalidProposalStateError(Exception):
    pass


class ProposalPermissionError(Exception):
    pass


class RuntimeUnavailableError(Exception):
    pass


class ProposalService:
    @staticmethod
    def _numeric_control_value(value: object, config: dict | None) -> float | None:
        if config:
            for code, option in config.get("options", {}).items():
                if str(value).strip().lower() == str(option).strip().lower():
                    return float(code)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _switch_value(value: object) -> float | None:
        normalized = str(value).strip().lower()
        if normalized in {"on", "connected", "enabled", "true", "1"}:
            return 1.0
        if normalized in {"off", "disconnected", "disabled", "false", "0"}:
            return 0.0
        return None

    async def create_smart_plug_proposal(
        self, db: Session, device_id: int, target_on: bool
    ) -> Proposal:
        device = device_repository.get_by_id(db, device_id)
        if device is None:
            raise ProposalNotFoundError(f"Device not found: {device_id}")
        if device.device_type != "smart_plug":
            raise ProposalPermissionError("The selected device is not a smart plug.")
        if not device.observe_enabled or not device.propose_enabled:
            raise ProposalPermissionError(
                "The bound device does not allow observation and proposals."
            )
        try:
            discovery = await device_discovery_service.discover_devices()
        except Exception as exc:
            raise RuntimeUnavailableError(
                f"Current Home Assistant observation failed: {exc}"
            ) from exc
        runtime = next(
            (
                item
                for item in discovery.devices
                if item.device_id == device.source_device_id
            ),
            None,
        )
        if runtime is None or not runtime.online:
            raise RuntimeUnavailableError("Smart plug is unavailable or offline.")
        capability = next(
            (item for item in runtime.controls if item.name == "power_switch"),
            None,
        )
        if capability is None or not capability.available:
            raise RuntimeUnavailableError("Smart plug power control is unavailable.")
        current = self._switch_value(capability.value)
        if current is None:
            raise RuntimeUnavailableError("Smart plug readback state is not recognized.")
        target = 1.0 if target_on else 0.0
        existing = proposal_repository.get_matching_pending(
            db,
            device_id=device.id,
            capability="power_switch",
            target_value=target,
        )
        if existing is not None:
            return existing
        return proposal_repository.create(
            db,
            Proposal(
                device_id=device.id,
                strategy_mode=StrategyMode.AUTO,
                capability="power_switch",
                current_value=current,
                target_value=target,
                reason_code="USER_REQUESTED_LOAD_CONTROL",
                reason=(
                    "用户请求开启 Smart Plug Gen 2。"
                    if target_on
                    else "用户请求关闭 Smart Plug Gen 2。"
                ),
                status=ProposalStatus.PENDING,
            ),
        )

    async def create_device_control_proposal(
        self, db: Session, device_id: int, capability_name: str, target: float
    ) -> Proposal:
        device = device_repository.get_by_id(db, device_id)
        if device is None:
            raise ProposalNotFoundError(f"Device not found: {device_id}")
        if device.device_type != "storage":
            raise ProposalPermissionError("The selected device is not an energy storage device.")
        if not device.observe_enabled or not device.propose_enabled:
            raise ProposalPermissionError(
                "The bound device does not allow observation and proposals."
            )
        try:
            discovery = await device_discovery_service.discover_devices()
        except Exception as exc:
            raise RuntimeUnavailableError(
                f"Current Home Assistant observation failed: {exc}"
            ) from exc
        runtime = next(
            (item for item in discovery.devices if item.device_id == device.source_device_id),
            None,
        )
        if runtime is None or not runtime.online:
            raise RuntimeUnavailableError("Energy storage device is unavailable or offline.")
        capability = next(
            (item for item in runtime.controls if item.name == capability_name), None
        )
        if capability is None or not capability.available:
            raise RuntimeUnavailableError(
                f"Control capability is unavailable: {capability_name}"
            )
        if capability.access != "read_write":
            raise ProposalPermissionError("The capability is not writable.")
        config = device_discovery_service.get_control_config(
            runtime.profile_id, capability_name, runtime.source_mode
        )
        current = self._numeric_control_value(capability.value, config)
        if current is None:
            raise RuntimeUnavailableError("Current control readback is not recognized.")
        minimum = float(capability.min) if capability.min is not None else None
        maximum = float(capability.max) if capability.max is not None else None
        step = float(capability.step or 0)
        if minimum is not None and target < minimum or maximum is not None and target > maximum:
            raise ProposalPermissionError("Target value is outside the device capability range.")
        options = (config or {}).get("options", {})
        if options:
            option = options.get(int(target))
            if option is None:
                option = options.get(str(int(target)))
            if target != int(target) or option is None:
                raise ProposalPermissionError("Target value is not a declared select option.")
        if step > 0 and minimum is not None:
            offset = (target - minimum) / step
            if abs(offset - round(offset)) > 1e-6:
                raise ProposalPermissionError("Target value does not match the capability step.")
        existing = proposal_repository.get_matching_pending(
            db,
            device_id=device.id,
            capability=capability_name,
            target_value=target,
        )
        if existing is not None:
            return existing
        return proposal_repository.create(
            db,
            Proposal(
                device_id=device.id,
                strategy_mode=StrategyMode.AUTO,
                capability=capability_name,
                current_value=current,
                target_value=target,
                reason_code="USER_REQUESTED_STORAGE_CONTROL",
                reason=f"用户请求将储能能力 {capability_name} 调整为 {target:g}。",
                status=ProposalStatus.PENDING,
            ),
        )

    async def generate(self, db: Session) -> ProposalGenerationResponseSchema:
        try:
            decision = await optimizer_evaluation_service.evaluate(db=db)
        except Exception as exc:
            raise RuntimeUnavailableError(
                f"Optimizer V2 evaluation is unavailable: {exc}"
            ) from exc

        return self.create_from_decision(db=db, decision=decision)

    def create_from_decision(
        self,
        db: Session,
        decision: OptimizationDecisionV2Schema,
    ) -> ProposalGenerationResponseSchema:
        """Create only a PENDING proposal from an existing Optimizer V2 result.

        This entry point deliberately performs no optimization and no execution.
        It lets trusted orchestration layers preserve one evaluated decision
        across deterministic deduplication and proposal creation.
        """
        if not decision.action_required:
            return ProposalGenerationResponseSchema(created=False, decision=decision)
        if decision.current_value is None or decision.target_value is None:
            raise RuntimeUnavailableError(
                "Optimizer V2 did not provide a complete proposal target."
            )
        device = (
            device_repository.get_by_id(db, decision.device_id)
            if decision.device_id is not None
            else None
        )
        if device is None or not device.propose_enabled:
            raise ProposalPermissionError(
                "The bound device does not allow proposal generation."
            )

        existing = proposal_repository.get_matching_pending(
            db,
            device_id=device.id,
            capability=decision.capability,
            target_value=decision.target_value,
        )
        if existing is not None:
            return ProposalGenerationResponseSchema(
                created=False, decision=decision, proposal=existing
            )

        proposal = proposal_repository.create(
            db,
            Proposal(
                device_id=device.id,
                strategy_mode=decision.strategy_mode,
                capability=decision.capability,
                current_value=decision.current_value,
                target_value=decision.target_value,
                reason_code=decision.reason_code,
                reason=decision.reason,
                status=ProposalStatus.PENDING,
            ),
        )
        return ProposalGenerationResponseSchema(
            created=True, decision=decision, proposal=proposal
        )

    def get(self, db: Session, proposal_id: int) -> Proposal:
        proposal = proposal_repository.get_by_id(db, proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(f"Proposal not found: {proposal_id}")
        return proposal

    def reject(self, db: Session, proposal_id: int) -> ProposalActionResponseSchema:
        self.get(db, proposal_id)
        proposal = proposal_repository.transition(
            db, proposal_id, ProposalStatus.PENDING, ProposalStatus.REJECTED
        )
        if proposal is None:
            raise InvalidProposalStateError(
                "Only a PENDING proposal can be rejected."
            )
        return ProposalActionResponseSchema(proposal=proposal)

    async def approve(
        self, db: Session, proposal_id: int
    ) -> ProposalActionResponseSchema:
        self.get(db, proposal_id)
        proposal = proposal_repository.transition(
            db, proposal_id, ProposalStatus.PENDING, ProposalStatus.APPROVED
        )
        if proposal is None:
            raise InvalidProposalStateError(
                "Only a PENDING proposal can be approved; repeat execution is blocked."
            )

        device = device_repository.get_by_id(db, proposal.device_id)
        try:
            discovery = await device_discovery_service.discover_devices()
            runtime = next(
                (
                    item
                    for item in discovery.devices
                    if device is not None and item.device_id == device.source_device_id
                ),
                None,
            )
        except Exception as exc:
            runtime = None
            discovery_error = str(exc)
        else:
            discovery_error = None

        if device is None or runtime is None:
            safety = safety_service.runtime_unavailable_result(
                device_found=device is not None,
                ha_request_succeeded=discovery_error is None,
                runtime_found=runtime is not None,
                detail=discovery_error,
            )
        else:
            safety = safety_service.check(
                proposal=proposal, device=device, runtime=runtime
            )

        if not safety.passed:
            proposal.status = ProposalStatus.BLOCKED
            proposal.error_code = safety.reason_code
            proposal.error_message = safety.message
            proposal_repository.save(db, proposal)
            return ProposalActionResponseSchema(proposal=proposal, safety=safety)

        executing = proposal_repository.transition(
            db, proposal.id, ProposalStatus.APPROVED, ProposalStatus.EXECUTING
        )
        if executing is None:
            raise InvalidProposalStateError("Proposal execution could not be claimed.")

        execution = await execution_service.execute(
            db=db, proposal=executing, runtime=runtime
        )
        final_proposal = self.get(db, proposal.id)
        return ProposalActionResponseSchema(
            proposal=final_proposal, safety=safety, execution=execution
        )


proposal_service = ProposalService()
