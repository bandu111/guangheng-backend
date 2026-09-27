from app.modules.device_registry.schemas.device_registry import DeviceCapabilitySchema
from app.modules.energy_state.schemas.energy_balance import (
    EnergyBalanceResponseSchema,
    EnergySinkPowerSchema,
    EnergySourcePowerSchema,
)
from app.modules.energy_state.schemas.energy_state import (
    EnergyPowerStateSchema,
    EnergySourceSchema,
    EnergyStateResponseSchema,
    EnergyStorageStateSchema,
)
from app.modules.optimizer.services.optimizer_service import optimizer_service
from app.modules.strategy.models.strategy import StrategyMode


def test_optimizer_proposes_only_verified_v1_target_difference():
    state = EnergyStateResponseSchema(
        available=True,
        online=True,
        source=EnergySourceSchema(
            device_id=1,
            source_device_id="anker_solix_test",
            source_mode="simulator",
        ),
        power=EnergyPowerStateSchema(),
        storage=EnergyStorageStateSchema(),
    )
    balance = EnergyBalanceResponseSchema(
        available=True,
        online=True,
        sources=EnergySourcePowerSchema(),
        sinks=EnergySinkPowerSchema(),
        balanced=True,
    )
    capability = DeviceCapabilitySchema(
        name="backup_reserve",
        entity_id="number.test_backup_reserve",
        access="read_write",
        value=25,
        available=True,
        verified=True,
    )

    decision = optimizer_service.optimize(
        energy_state=state,
        energy_balance=balance,
        strategy_mode=StrategyMode.BACKUP,
        backup_reserve_target=80,
        capability=capability,
    )

    assert decision.action_required is True
    assert decision.capability == "backup_reserve"
    assert decision.current_value == 25
    assert decision.target_value == 80
