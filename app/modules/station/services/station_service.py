from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.modules.energy_state.schemas.energy_state import EnergyStateResponseSchema
from app.modules.energy_state.schemas.energy_today import EnergyTodayResponseSchema
from app.modules.energy_state.services.energy_state_service import energy_state_service
from app.modules.energy_state.services.energy_today_service import energy_today_service
from app.modules.station.schemas.station import (
    StationNodeSchema,
    StationSourceSchema,
    StationSummarySchema,
    StationTodaySchema,
)


class StationService:
    @staticmethod
    def _direction(value: float | None, positive: str) -> str:
        if value is None or abs(value) < 50:
            return "idle"
        return positive

    @classmethod
    def compose(
        cls,
        state: EnergyStateResponseSchema,
        today: EnergyTodayResponseSchema,
        observed_at: datetime,
    ) -> StationSummarySchema:
        charging = state.power.battery_charging_w or 0
        discharging = state.power.battery_discharging_w or 0
        battery_power = discharging - charging
        grid_import = state.power.grid_import_w or 0
        grid_export = state.power.grid_export_w or 0
        grid_power = grid_import - grid_export
        nodes = [
            StationNodeSchema(
                key="solar",
                label="光伏",
                available=state.power.solar_w is not None,
                power_w=state.power.solar_w,
                direction=cls._direction(state.power.solar_w, "out"),
            ),
            StationNodeSchema(
                key="home",
                label="家庭",
                available=state.power.home_load_w is not None,
                power_w=state.power.home_load_w,
                direction=cls._direction(state.power.home_load_w, "in"),
            ),
            StationNodeSchema(
                key="battery",
                label="储能",
                available=(
                    state.storage.soc_percent is not None
                    or state.power.battery_charging_w is not None
                    or state.power.battery_discharging_w is not None
                ),
                power_w=abs(battery_power),
                direction="out" if battery_power > 50 else "in" if battery_power < -50 else "idle",
                status=state.storage.status,
            ),
            StationNodeSchema(
                key="grid",
                label="电网",
                available=(
                    state.power.grid_import_w is not None
                    or state.power.grid_export_w is not None
                ),
                power_w=abs(grid_power),
                direction="in" if grid_power > 50 else "out" if grid_power < -50 else "idle",
            ),
        ]
        coverage = today.source.coverage_percent
        quality = "missing" if not state.available else "degraded" if coverage < 80 else "good"
        diagnostic = None
        if not state.available:
            diagnostic = "ENERGY_STATE_UNAVAILABLE"
        elif not state.online:
            diagnostic = "DEVICE_OFFLINE"
        elif not today.available:
            diagnostic = today.error_code or "ENERGY_HISTORY_UNAVAILABLE"
        return StationSummarySchema(
            available=state.available,
            online=state.online,
            data_quality=quality,
            source=StationSourceSchema(
                device_id=state.source.device_id if state.source else None,
                source_device_id=state.source.source_device_id if state.source else None,
                display_name=state.source.display_name if state.source else None,
                source_mode=state.source.source_mode if state.source else None,
            ),
            nodes=nodes,
            today=StationTodaySchema(
                date=today.date,
                generation_kwh=today.summary.generation_kwh,
                consumption_kwh=today.summary.consumption_kwh,
                grid_import_kwh=today.summary.grid_import_kwh,
                savings_cny=today.summary.savings_cny,
                coverage_percent=coverage,
            ),
            observed_at=observed_at,
            last_updated=state.last_updated,
            diagnostic=diagnostic,
        )

    async def get_current(self, db: Session) -> StationSummarySchema:
        observed_at = datetime.now(timezone.utc)
        state = await energy_state_service.get_energy_state(db)
        today = await energy_today_service.get_today()
        return self.compose(state, today, observed_at)


station_service = StationService()

