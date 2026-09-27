import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.decision_context.schemas.decision_context import DecisionContextSchema
from app.modules.device_registry.models.device import Device
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
from app.modules.load_forecast.schemas.load_forecast import (
    LoadForecastConfidence,
    LoadForecastPointSchema,
    LoadForecastResponseSchema,
    LoadForecastSummarySchema,
)
from app.modules.optimizer.services.optimizer_v2_service import OptimizerV2Service
from app.modules.proposal.models.proposal import Proposal
from app.modules.proposal.services.proposal_service import proposal_service
from app.modules.solar_forecast.schemas.solar_forecast import (
    SolarForecastConfidence,
    SolarForecastPointSchema,
    SolarForecastResponseSchema,
    SolarForecastSummarySchema,
)
from app.modules.strategy.models.strategy import StrategyMode
from app.modules.strategy.schemas.strategy import StrategyResponseSchema
from app.modules.tariff.schemas.tariff import (
    TariffContextSchema,
    TariffCurrentSchema,
    TariffSourceSchema,
)
from app.modules.weather.schemas.weather import (
    WeatherContextSchema,
    WeatherCurrentSchema,
)


NOW = datetime(2026, 9, 20, 4, 0, tzinfo=timezone.utc)
BASELINES = {
    StrategyMode.SAVE: 20,
    StrategyMode.AUTO: 30,
    StrategyMode.BACKUP: 80,
}


def _context(
    *,
    mode: StrategyMode = StrategyMode.AUTO,
    solar_6h: float | None = 10,
    load_6h: float | None = 8,
    solar_24h: float | None = 30,
    load_24h: float | None = 35,
    solar_confidence: SolarForecastConfidence = SolarForecastConfidence.HIGH,
    load_confidence: LoadForecastConfidence = LoadForecastConfidence.HIGH,
    cloud_cover: float = 20,
) -> DecisionContextSchema:
    solar_points = [
        SolarForecastPointSchema(
            time=NOW + timedelta(hours=index + 1),
            solar_power_w=1000,
            shortwave_radiation_w_m2=200,
            cloud_cover_percent=cloud_cover,
            confidence=solar_confidence,
        )
        for index in range(24)
    ]
    load_points = [
        LoadForecastPointSchema(
            time=NOW + timedelta(hours=index + 1),
            load_power_w=1200,
            historical_samples=7,
            confidence=load_confidence,
        )
        for index in range(24)
    ]
    energy = EnergyStateResponseSchema(
        available=True,
        online=True,
        source=EnergySourceSchema(
            device_id=1,
            source_device_id="anker_solix_test",
            source_mode="simulator",
        ),
        power=EnergyPowerStateSchema(solar_w=1000, home_load_w=1200),
        storage=EnergyStorageStateSchema(
            soc_percent=70,
            capacity_kwh=10,
        ),
    )
    return DecisionContextSchema(
        available=True,
        observed_at=NOW,
        energy=energy,
        balance=EnergyBalanceResponseSchema(
            available=True,
            online=True,
            sources=EnergySourcePowerSchema(total_w=1200),
            sinks=EnergySinkPowerSchema(total_w=1200),
            balance_error_w=0,
            balanced=True,
        ),
        strategy=StrategyResponseSchema(
            id=1,
            mode=mode,
            backup_reserve_target=BASELINES[mode],
            created_at=NOW,
            updated_at=NOW,
        ),
        weather=WeatherContextSchema(
            available=True,
            provider="open_meteo",
            current=WeatherCurrentSchema(
                condition="clear",
                cloud_cover_percent=cloud_cover,
            ),
            observed_at=NOW,
        ),
        solar_forecast=SolarForecastResponseSchema(
            available=solar_6h is not None and solar_24h is not None,
            method="test_solar",
            current_solar_w=1000,
            current_shortwave_radiation_w_m2=200,
            calibration_ratio=5,
            forecast=solar_points,
            summary=SolarForecastSummarySchema(
                next_6h_energy_kwh=solar_6h,
                next_24h_energy_kwh=solar_24h,
            ),
            observed_at=NOW,
        ),
        load_forecast=LoadForecastResponseSchema(
            available=load_6h is not None and load_24h is not None,
            method="test_load",
            history_days_requested=7,
            history_samples=168,
            current_load_w=1200,
            forecast=load_points,
            summary=LoadForecastSummarySchema(
                next_6h_energy_kwh=load_6h,
                next_24h_energy_kwh=load_24h,
            ),
            observed_at=NOW,
        ),
        tariff=TariffContextSchema(
            available=True,
            current=TariffCurrentSchema(
                price_per_kwh=0.54,
                currency="CNY",
            ),
            source=TariffSourceSchema(
                provider="NDRC",
                pricing_type="reference_average",
                region="CN",
                reference_date="2019-08-23",
                realtime=False,
            ),
            observed_at=NOW,
        ),
    )


def _capability(value: float = 25) -> DeviceCapabilitySchema:
    return DeviceCapabilitySchema(
        name="backup_reserve",
        entity_id="number.test_backup_reserve",
        access="read_write",
        value=value,
        available=True,
        verified=True,
    )


def _optimize(**context_kwargs):
    return OptimizerV2Service().optimize(
        context=_context(**context_kwargs),
        capability=_capability(),
    )


def test_backup_always_uses_strategy_baseline():
    decision = _optimize(
        mode=StrategyMode.BACKUP,
        solar_6h=20,
        load_6h=1,
    )
    assert decision.target_value == 80
    assert decision.reason_code == "STRATEGY_BACKUP_BASELINE"


def test_save_always_uses_strategy_baseline():
    decision = _optimize(
        mode=StrategyMode.SAVE,
        solar_6h=0,
        load_6h=20,
    )
    assert decision.target_value == 20
    assert decision.reason_code == "STRATEGY_SAVE_BASELINE"


def test_auto_strong_surplus():
    decision = _optimize(solar_6h=10, load_6h=5)
    assert decision.target_value == 20
    assert decision.reason_code == "AUTO_FORECAST_STRONG_SURPLUS"


def test_auto_balanced():
    decision = _optimize(solar_6h=9, load_6h=8)
    assert decision.target_value == 30
    assert decision.reason_code == "AUTO_FORECAST_BALANCED"


def test_auto_moderate_deficit():
    decision = _optimize(solar_6h=5, load_6h=8)
    assert decision.target_value == 40
    assert decision.reason_code == "AUTO_FORECAST_MODERATE_DEFICIT"


def test_auto_strong_deficit():
    decision = _optimize(solar_6h=1, load_6h=8)
    assert decision.target_value == 50
    assert decision.reason_code == "AUTO_FORECAST_STRONG_DEFICIT"


def test_overall_confidence_uses_lower_forecast_confidence():
    decision = _optimize(
        solar_confidence=SolarForecastConfidence.MEDIUM,
        load_confidence=LoadForecastConfidence.LOW,
    )
    assert decision.evidence.solar_forecast_confidence == "MEDIUM"
    assert decision.evidence.load_forecast_confidence == "LOW"
    assert decision.decision_confidence == "LOW"


def test_low_confidence_keeps_auto_baseline():
    decision = _optimize(
        solar_6h=20,
        load_6h=1,
        load_confidence=LoadForecastConfidence.LOW,
    )
    assert decision.target_value == 30
    assert decision.reason_code == "FORECAST_CONFIDENCE_INSUFFICIENT"


def test_tariff_is_reference_cost_only_and_never_arbitrage_reason():
    decision = _optimize(solar_24h=30, load_24h=60)
    assert decision.evidence.projected_grid_energy_need_kwh == 30
    assert decision.evidence.estimated_reference_grid_cost_cny == 16.2
    assert decision.evidence.tariff_realtime is False
    assert "PRICE" not in decision.reason_code


def test_weather_does_not_multiply_solar_forecast_again():
    clear = _optimize(cloud_cover=0)
    cloudy = _optimize(cloud_cover=100)
    assert clear.target_value == cloudy.target_value
    assert clear.evidence.solar_6h_kwh == cloudy.evidence.solar_6h_kwh


def test_target_already_satisfied_requires_no_action():
    decision = OptimizerV2Service().optimize(
        context=_context(mode=StrategyMode.AUTO, solar_6h=9, load_6h=8),
        capability=_capability(30),
    )
    assert decision.action_required is False
    assert decision.reason_code == "TARGET_ALREADY_SATISFIED"


def test_missing_forecast_uses_context_fallback_baseline():
    decision = _optimize(solar_6h=None, solar_24h=None)
    assert decision.target_value == 30
    assert decision.reason_code == "CONTEXT_UNAVAILABLE"
    assert decision.action_required is True


def test_optimizer_v2_is_pure_and_does_not_call_home_assistant(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Optimizer V2 must not call Home Assistant")

    monkeypatch.setattr(
        "app.modules.home_assistant.services.home_assistant_service.home_assistant_service.get_states",
        forbidden,
    )
    decision = _optimize()
    assert decision.version == "v2"


def _database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def test_proposal_generate_uses_v2(monkeypatch):
    engine = _database()
    decision = _optimize(solar_6h=10, load_6h=5)

    async def evaluate(*, db):
        return decision

    monkeypatch.setattr(
        "app.modules.proposal.services.proposal_service.optimizer_evaluation_service.evaluate",
        evaluate,
    )
    with Session(engine) as db:
        db.add(
            Device(
                id=1,
                source_device_id="anker_solix_test",
                vendor="anker_solix",
                model="test",
                device_type="storage",
                topology_role="storage",
                integration="anker_solix_official",
                source_mode="simulator",
                propose_enabled=True,
            )
        )
        db.commit()
        result = asyncio.run(proposal_service.generate(db))

        assert result.created is True
        assert result.decision.version == "v2"
        assert result.proposal.reason_code == "AUTO_FORECAST_STRONG_SURPLUS"


def test_no_action_creates_no_proposal(monkeypatch):
    engine = _database()
    decision = OptimizerV2Service().optimize(
        context=_context(),
        capability=_capability(20),
    )

    async def evaluate(*, db):
        return decision

    monkeypatch.setattr(
        "app.modules.proposal.services.proposal_service.optimizer_evaluation_service.evaluate",
        evaluate,
    )
    with Session(engine) as db:
        result = asyncio.run(proposal_service.generate(db))
        proposals = list(db.scalars(select(Proposal)).all())

        assert result.created is False
        assert result.decision.reason_code == "TARGET_ALREADY_SATISFIED"
        assert proposals == []
