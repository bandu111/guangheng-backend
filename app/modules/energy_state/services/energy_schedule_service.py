from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.modules.energy_state.schemas.energy_schedule import (
    EnergyScheduleAction,
    EnergySchedulePointSchema,
    EnergyScheduleResponseSchema,
    EnergyScheduleSourceSchema,
    EnergyScheduleSummarySchema,
)
from app.modules.home_assistant.services.home_assistant_service import home_assistant_service
from app.modules.load_forecast.schemas.load_forecast import LoadForecastResponseSchema
from app.modules.load_forecast.services.load_forecast_service import load_forecast_service
from app.modules.solar_forecast.schemas.solar_forecast import SolarForecastResponseSchema
from app.modules.solar_forecast.services.solar_forecast_service import solar_forecast_service
from app.modules.strategy.services.strategy_service import strategy_service


class EnergyScheduleService:
    METHOD = "forecast_balance_advisory_v1"

    @staticmethod
    def _hour_key(value: datetime, zone: ZoneInfo) -> datetime:
        localized = value.replace(tzinfo=zone) if value.tzinfo is None else value
        return localized.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def _confidence(solar: str | None, load: str | None) -> str:
        levels = {"UNAVAILABLE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
        reverse = {value: key for key, value in levels.items()}
        return reverse[min(levels.get(solar or "UNAVAILABLE", 0), levels.get(load or "UNAVAILABLE", 0))]

    @staticmethod
    def _action(solar_w: float | None, load_w: float | None, strategy: str) -> EnergyScheduleAction:
        if solar_w is None or load_w is None:
            return EnergyScheduleAction.UNAVAILABLE
        if solar_w >= load_w * 1.1:
            return EnergyScheduleAction.STORE_SURPLUS
        if solar_w > 0:
            return EnergyScheduleAction.SOLAR_ASSIST
        if strategy == "BACKUP":
            return EnergyScheduleAction.PRESERVE_RESERVE
        return EnergyScheduleAction.COVER_DEFICIT

    @classmethod
    def from_forecasts(
        cls,
        *,
        solar: SolarForecastResponseSchema,
        load: LoadForecastResponseSchema,
        strategy: str,
        time_zone: str,
        observed_at: datetime,
    ) -> EnergyScheduleResponseSchema:
        zone = ZoneInfo(time_zone)
        solar_map = {cls._hour_key(point.time, zone): point for point in solar.forecast}
        load_map = {cls._hour_key(point.time, zone): point for point in load.forecast}
        hours = sorted(set(solar_map) | set(load_map))[:24]
        points: list[EnergySchedulePointSchema] = []
        solar_total = 0.0
        load_total = 0.0
        surplus_total = 0.0
        deficit_total = 0.0
        complete_count = 0
        for hour in hours:
            solar_point = solar_map.get(hour)
            load_point = load_map.get(hour)
            solar_w = solar_point.solar_power_w if solar_point else None
            load_w = load_point.load_power_w if load_point else None
            net_w = solar_w - load_w if solar_w is not None and load_w is not None else None
            if net_w is not None:
                complete_count += 1
                solar_total += solar_w
                load_total += load_w
                surplus_total += max(net_w, 0)
                deficit_total += max(-net_w, 0)
            local_hour = hour.astimezone(zone)
            points.append(EnergySchedulePointSchema(
                time=local_hour,
                hour=local_hour.hour,
                solar_power_w=round(solar_w, 1) if solar_w is not None else None,
                load_power_w=round(load_w, 1) if load_w is not None else None,
                net_power_w=round(net_w, 1) if net_w is not None else None,
                action=cls._action(solar_w, load_w, strategy),
                confidence=cls._confidence(
                    solar_point.confidence.value if solar_point else None,
                    load_point.confidence.value if load_point else None,
                ),
            ))
        available = complete_count > 0
        return EnergyScheduleResponseSchema(
            available=available,
            points=points,
            summary=EnergyScheduleSummarySchema(
                projected_solar_kwh=round(solar_total / 1000, 3) if complete_count else None,
                projected_load_kwh=round(load_total / 1000, 3) if complete_count else None,
                projected_surplus_kwh=round(surplus_total / 1000, 3) if complete_count else None,
                projected_deficit_kwh=round(deficit_total / 1000, 3) if complete_count else None,
            ),
            source=EnergyScheduleSourceSchema(
                strategy=strategy,
                solar_forecast_method=solar.method,
                load_forecast_method=load.method,
            ),
            observed_at=observed_at,
            error_code=None if available else "INSUFFICIENT_FORECAST_DATA",
        )

    async def get_schedule(self, db: Session) -> EnergyScheduleResponseSchema:
        observed_at = datetime.now(timezone.utc)
        strategy = strategy_service.get_current(db).mode.value
        try:
            config = await home_assistant_service.get_config()
            solar = await solar_forecast_service.get_forecast(db)
            load = await load_forecast_service.get_forecast(db)
            return self.from_forecasts(
                solar=solar,
                load=load,
                strategy=strategy,
                time_zone=config.time_zone,
                observed_at=observed_at,
            )
        except Exception:
            return EnergyScheduleResponseSchema(
                available=False,
                summary=EnergyScheduleSummarySchema(),
                source=EnergyScheduleSourceSchema(
                    strategy=strategy,
                    solar_forecast_method="unavailable",
                    load_forecast_method="unavailable",
                ),
                observed_at=observed_at,
                error_code="SCHEDULE_CONTEXT_UNAVAILABLE",
            )


energy_schedule_service = EnergyScheduleService()
