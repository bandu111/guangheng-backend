from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.modules.energy_state.models.energy_observation import EnergyObservation
from app.modules.energy_state.repositories.energy_observation_repository import (
    energy_observation_repository,
)
from app.modules.energy_state.services.simulator_history_service import (
    simulator_history_service,
)
from app.modules.energy_state.services.energy_today_service import EnergyTodayService
from app.modules.home_assistant.schemas.home_assistant import (
    HomeAssistantHistoryStateSchema,
)

from app.modules.energy_state.services.simulator_energy_service import (
    simulator_energy_service,
)


def _assert_balanced(state) -> None:
    supply = state.solar_w + state.battery_discharging_w + state.grid_import_w
    demand = state.home_load_w + state.battery_charging_w + state.grid_export_w
    assert abs(supply - demand) <= 0.2


def test_simulator_buys_from_grid_at_night_when_reserve_is_protected():
    # 2026-09-23 00:00 Asia/Shanghai
    state = simulator_energy_service.calculate(
        datetime(2026, 9, 22, 16, tzinfo=timezone.utc),
        soc_percent=77,
        reserve_percent=82,
    )

    assert state.solar_w == 0
    assert state.battery_discharging_w == 0
    assert state.grid_import_w == state.home_load_w
    assert state.grid_import_w > 0
    assert state.battery_status == "idle"
    _assert_balanced(state)


def test_simulator_uses_solar_surplus_for_charging_before_export():
    # 2026-09-23 12:00 Asia/Shanghai
    state = simulator_energy_service.calculate(
        datetime(2026, 9, 23, 4, tzinfo=timezone.utc),
        soc_percent=77,
        reserve_percent=35,
    )

    assert state.solar_w > state.home_load_w
    assert state.battery_charging_w > 0
    assert state.grid_import_w == 0
    assert state.battery_status == "charging"
    _assert_balanced(state)


def test_simulator_evening_deficit_uses_battery_and_grid_together():
    # 2026-09-23 20:00 Asia/Shanghai
    state = simulator_energy_service.calculate(
        datetime(2026, 9, 23, 12, tzinfo=timezone.utc),
        soc_percent=77,
        reserve_percent=35,
    )

    assert state.solar_w == 0
    assert state.battery_discharging_w == 800
    assert state.grid_import_w > 0
    assert state.battery_status == "discharging"
    _assert_balanced(state)


def test_simulator_history_is_immediately_available_without_touching_real_rows():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    EnergyObservation.__table__.create(engine)
    session_factory = sessionmaker(bind=engine)
    observed_at = datetime(2026, 9, 23, 14, tzinfo=timezone.utc)

    with session_factory() as db:
        db.add(
            EnergyObservation(
                observed_at=datetime(2026, 9, 23, 13),
                available=True,
                online=True,
                source_mode="home_assistant",
                grid_import_w=432.1,
            )
        )
        db.commit()
        created = simulator_history_service.ensure_recent_history(
            db,
            observed_at=observed_at,
            soc_percent=77,
        )
        rows = energy_observation_repository.list_between(
            db,
            observed_at.replace(tzinfo=None) - timedelta(days=8),
            observed_at.replace(tzinfo=None),
        )

    simulator_rows = [row for row in rows if row.source_mode == "simulator"]
    real_row = next(row for row in rows if row.source_mode == "home_assistant")
    assert created >= 7 * 90
    assert any((row.grid_import_w or 0) > 0 for row in simulator_rows)
    assert real_row.grid_import_w == 432.1

    histories = {
        "solar": [
            HomeAssistantHistoryStateSchema(
                state=str(row.solar_w),
                last_updated=row.observed_at.replace(tzinfo=timezone.utc).isoformat(),
            )
            for row in simulator_rows
        ],
        "home": [
            HomeAssistantHistoryStateSchema(
                state=str(row.home_load_w),
                last_updated=row.observed_at.replace(tzinfo=timezone.utc).isoformat(),
            )
            for row in simulator_rows
        ],
        "grid": [
            HomeAssistantHistoryStateSchema(
                state=str(row.grid_import_w),
                last_updated=row.observed_at.replace(tzinfo=timezone.utc).isoformat(),
            )
            for row in simulator_rows
        ],
    }
    today = EnergyTodayService.from_histories(
        histories=histories,
        time_zone="Asia/Shanghai",
        observed_at=observed_at,
        tariff_price_per_kwh=0.54,
        max_hold_seconds=900,
        source_provider="guangheng_simulator_observation_store",
    )
    assert today.summary.grid_import_kwh is not None
    assert today.summary.grid_import_kwh > 0
    assert today.summary.grid_import_kwh * 0.54 > 0
