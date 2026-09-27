from app.modules.device_registry.schemas.device_registry import DeviceCapabilitySchema
from app.modules.energy_state.schemas.energy_balance import EnergyBalanceResponseSchema
from app.modules.energy_state.schemas.energy_state import EnergyStateResponseSchema
from app.modules.optimizer.schemas.optimizer import OptimizerDecisionSchema
from app.modules.strategy.models.strategy import StrategyMode


class OptimizerService:
    """Deterministic, side-effect-free optimizer for the verified V1 control."""

    @staticmethod
    def optimize(
        *,
        energy_state: EnergyStateResponseSchema,
        energy_balance: EnergyBalanceResponseSchema,
        strategy_mode: StrategyMode,
        backup_reserve_target: float,
        capability: DeviceCapabilitySchema | None,
    ) -> OptimizerDecisionSchema:
        common = {"strategy_mode": strategy_mode, "target_value": backup_reserve_target}

        if not energy_state.available or not energy_state.online:
            return OptimizerDecisionSchema(
                **common,
                action_required=False,
                reason_code="ENERGY_STATE_UNAVAILABLE",
                reason="Real-time energy state is unavailable or the device is offline.",
            )
        if not energy_balance.available:
            return OptimizerDecisionSchema(
                **common,
                action_required=False,
                device_id=energy_state.source.device_id if energy_state.source else None,
                reason_code="ENERGY_BALANCE_UNAVAILABLE",
                reason="Energy balance is incomplete; no proposal was generated.",
            )
        if capability is None or not capability.available:
            return OptimizerDecisionSchema(
                **common,
                action_required=False,
                device_id=energy_state.source.device_id if energy_state.source else None,
                reason_code="CAPABILITY_UNAVAILABLE",
                reason="The backup reserve capability is unavailable in Home Assistant.",
            )

        try:
            current = float(capability.value)
        except (TypeError, ValueError):
            return OptimizerDecisionSchema(
                **common,
                action_required=False,
                device_id=energy_state.source.device_id if energy_state.source else None,
                reason_code="CURRENT_VALUE_INVALID",
                reason="The current backup reserve value is not numeric.",
            )

        action_required = abs(current - backup_reserve_target) > 0.01
        return OptimizerDecisionSchema(
            **common,
            action_required=action_required,
            device_id=energy_state.source.device_id if energy_state.source else None,
            current_value=current,
            reason_code="TARGET_DIFFERS" if action_required else "ALREADY_AT_TARGET",
            reason=(
                f"{strategy_mode.value} requires backup reserve "
                f"{backup_reserve_target:g}%; current value is {current:g}%."
                if action_required
                else f"Backup reserve is already at the {strategy_mode.value} target."
            ),
        )


optimizer_service = OptimizerService()
