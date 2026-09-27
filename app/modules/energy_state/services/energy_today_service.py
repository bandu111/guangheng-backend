import asyncio
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.energy_state.schemas.energy_today import (
    EnergyTodayFlowPointSchema,
    EnergyTodayResponseSchema,
    EnergyTodaySourceSchema,
    EnergyTodaySummarySchema,
)
from app.modules.energy_state.services.energy_observation_history import (
    load_observation_histories,
    merge_histories,
)
from app.modules.energy_state.services.energy_observation_policy_service import (
    energy_observation_policy,
)
from app.modules.home_assistant.schemas.home_assistant import (
    HomeAssistantHistoryStateSchema,
)
from app.modules.home_assistant.services.home_assistant_service import (
    HomeAssistantConfigInvalidError,
    home_assistant_service,
)
from app.modules.tariff.services.tariff_service import tariff_service


@dataclass(frozen=True)
class _SeriesResult:
    energy_kwh: float | None
    hourly_average_w: dict[datetime, float]
    hourly_coverage_seconds: dict[datetime, float]
    coverage_percent: float
    sample_count: int


class EnergyTodayService:
    METHOD = "power_step_time_integral_v1"
    CAPABILITIES = {
        "solar": "solar_power",
        "home": "home_load",
        "grid": "grid_import_power",
    }

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _parse_power(value: str) -> float | None:
        normalized = value.strip().lower()
        if normalized in {"", "unknown", "unavailable", "none", "null"}:
            return None
        try:
            power = float(normalized)
        except ValueError:
            return None
        if not math.isfinite(power) or power < 0:
            return None
        return power

    @classmethod
    def _clean_history(
        cls,
        history: list[HomeAssistantHistoryStateSchema],
    ) -> list[tuple[datetime, float]]:
        samples: dict[datetime, float] = {}
        for item in history:
            timestamp = cls._parse_timestamp(item.last_updated or item.last_changed)
            power = cls._parse_power(item.state)
            if timestamp is not None and power is not None:
                samples[timestamp] = power
        return sorted(samples.items(), key=lambda item: item[0])

    @staticmethod
    def _next_local_hour(value: datetime, local_zone: ZoneInfo) -> datetime:
        local = value.astimezone(local_zone)
        next_local = local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return next_local.astimezone(timezone.utc)

    @classmethod
    def aggregate_series(
        cls,
        *,
        history: list[HomeAssistantHistoryStateSchema],
        start_at: datetime,
        end_at: datetime,
        local_zone: ZoneInfo,
        max_hold_seconds: int | None = None,
    ) -> _SeriesResult:
        cleaned = cls._clean_history(history)
        if not cleaned or end_at <= start_at:
            return _SeriesResult(None, {}, {}, 0, len(cleaned))

        total_watt_seconds = 0.0
        covered_seconds = 0.0
        hourly_watt_seconds: dict[datetime, float] = {}
        hourly_coverage: dict[datetime, float] = {}

        for index, (sample_at, power_w) in enumerate(cleaned):
            next_at = cleaned[index + 1][0] if index + 1 < len(cleaned) else end_at
            if max_hold_seconds is not None:
                next_at = min(
                    next_at,
                    sample_at + timedelta(seconds=max_hold_seconds),
                )
            segment_start = max(sample_at, start_at)
            segment_end = min(next_at, end_at)
            if segment_end <= segment_start:
                continue

            cursor = segment_start
            while cursor < segment_end:
                boundary = min(cls._next_local_hour(cursor, local_zone), segment_end)
                seconds = (boundary - cursor).total_seconds()
                hour = cursor.astimezone(local_zone).replace(minute=0, second=0, microsecond=0)
                total_watt_seconds += power_w * seconds
                covered_seconds += seconds
                hourly_watt_seconds[hour] = hourly_watt_seconds.get(hour, 0) + power_w * seconds
                hourly_coverage[hour] = hourly_coverage.get(hour, 0) + seconds
                cursor = boundary

        elapsed = (end_at - start_at).total_seconds()
        averages = {
            hour: hourly_watt_seconds[hour] / seconds
            for hour, seconds in hourly_coverage.items()
            if seconds > 0
        }
        return _SeriesResult(
            energy_kwh=(total_watt_seconds / 3_600_000 if covered_seconds else None),
            hourly_average_w=averages,
            hourly_coverage_seconds=hourly_coverage,
            coverage_percent=min(100.0, covered_seconds / elapsed * 100) if elapsed else 0,
            sample_count=len(cleaned),
        )

    @staticmethod
    def _change(current: float | None, previous: float | None) -> float | None:
        if current is None or previous is None or previous <= 0:
            return None
        return round((current - previous) / previous * 100, 1)

    @staticmethod
    def _round(value: float | None, digits: int = 3) -> float | None:
        return round(value, digits) if value is not None else None

    @classmethod
    def _legacy_capability_entity_ids(cls) -> dict[str, str]:
        matrix = device_discovery_service.load_capability_matrix()
        telemetry = matrix.get("telemetry", {})
        result: dict[str, str] = {}
        for key, capability_name in cls.CAPABILITIES.items():
            capability = telemetry.get(capability_name)
            if isinstance(capability, dict):
                entity_id = capability.get("entity_id")
                if isinstance(entity_id, str) and entity_id:
                    result[key] = entity_id
        return result

    @classmethod
    async def _capability_entity_ids(cls) -> dict[str, str]:
        try:
            dynamic = await device_discovery_service.resolve_storage_telemetry_entity_ids(
                cls.CAPABILITIES
            )
        except Exception:
            dynamic = {}
        return dynamic or cls._legacy_capability_entity_ids()

    @classmethod
    def from_histories(
        cls,
        *,
        histories: dict[str, list[HomeAssistantHistoryStateSchema]],
        time_zone: str,
        observed_at: datetime,
        tariff_price_per_kwh: float,
        currency: str = "CNY",
        max_hold_seconds: int | None = None,
        source_provider: str = "home_assistant_recorder",
    ) -> EnergyTodayResponseSchema:
        local_zone = ZoneInfo(time_zone)
        local_now = observed_at.astimezone(local_zone)
        today_start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = today_start_local.astimezone(timezone.utc)
        elapsed = observed_at - today_start
        previous_start = (today_start_local - timedelta(days=1)).astimezone(timezone.utc)
        previous_end = previous_start + elapsed

        today = {
            key: cls.aggregate_series(
                history=history,
                start_at=today_start,
                end_at=observed_at,
                local_zone=local_zone,
                max_hold_seconds=max_hold_seconds,
            )
            for key, history in histories.items()
        }
        previous = {
            key: cls.aggregate_series(
                history=history,
                start_at=previous_start,
                end_at=previous_end,
                local_zone=local_zone,
                max_hold_seconds=max_hold_seconds,
            )
            for key, history in histories.items()
        }

        generation = today.get("solar", _SeriesResult(None, {}, {}, 0, 0)).energy_kwh
        consumption = today.get("home", _SeriesResult(None, {}, {}, 0, 0)).energy_kwh
        grid_import = today.get("grid", _SeriesResult(None, {}, {}, 0, 0)).energy_kwh
        avoided = max(consumption - grid_import, 0) if consumption is not None and grid_import is not None else None
        savings = avoided * tariff_price_per_kwh if avoided is not None else None

        previous_consumption = previous.get("home", _SeriesResult(None, {}, {}, 0, 0)).energy_kwh
        previous_grid = previous.get("grid", _SeriesResult(None, {}, {}, 0, 0)).energy_kwh
        previous_avoided = max(previous_consumption - previous_grid, 0) if previous_consumption is not None and previous_grid is not None else None
        previous_savings = previous_avoided * tariff_price_per_kwh if previous_avoided is not None else None

        hours = sorted(set().union(*(series.hourly_average_w.keys() for series in today.values())))
        flow = []
        for hour in hours:
            coverage_values = [
                series.hourly_coverage_seconds.get(hour, 0)
                for series in today.values()
                if series.sample_count > 0
            ]
            coverage = min(coverage_values) if coverage_values else 0
            hour_end = min(hour + timedelta(hours=1), local_now)
            hour_elapsed = max((hour_end - hour).total_seconds(), 1)
            flow.append(
                EnergyTodayFlowPointSchema(
                    time=hour,
                    hour=hour.hour,
                    solar_power_w=cls._round(today.get("solar", _SeriesResult(None, {}, {}, 0, 0)).hourly_average_w.get(hour), 1),
                    home_load_w=cls._round(today.get("home", _SeriesResult(None, {}, {}, 0, 0)).hourly_average_w.get(hour), 1),
                    grid_import_w=cls._round(today.get("grid", _SeriesResult(None, {}, {}, 0, 0)).hourly_average_w.get(hour), 1),
                    coverage_percent=round(min(100.0, coverage / hour_elapsed * 100), 1),
                )
            )

        valid_coverage = [series.coverage_percent for series in today.values() if series.sample_count > 0]
        available = generation is not None and consumption is not None
        return EnergyTodayResponseSchema(
            available=available,
            date=local_now.date(),
            time_zone=time_zone,
            summary=EnergyTodaySummarySchema(
                generation_kwh=cls._round(generation),
                consumption_kwh=cls._round(consumption),
                grid_import_kwh=cls._round(grid_import),
                avoided_grid_kwh=cls._round(avoided),
                savings_cny=cls._round(savings, 2),
                generation_change_percent=cls._change(generation, previous.get("solar", _SeriesResult(None, {}, {}, 0, 0)).energy_kwh),
                consumption_change_percent=cls._change(consumption, previous_consumption),
                savings_change_percent=cls._change(savings, previous_savings),
                tariff_price_per_kwh=tariff_price_per_kwh,
                currency=currency,
            ),
            flow=flow,
            source=EnergyTodaySourceSchema(
                provider=source_provider,
                sample_count=sum(series.sample_count for series in today.values()),
                coverage_percent=round(min(valid_coverage), 1) if valid_coverage else 0,
            ),
            observed_at=observed_at,
            error_code=None if available else "INSUFFICIENT_ENERGY_HISTORY",
        )

    async def get_today(self) -> EnergyTodayResponseSchema:
        observed_at = datetime.now(timezone.utc)
        fallback_zone = "Asia/Shanghai"
        try:
            config = await home_assistant_service.get_config()
            local_zone = ZoneInfo(config.time_zone)
            entity_ids = await self._capability_entity_ids()
        except (HomeAssistantConfigInvalidError, ZoneInfoNotFoundError, OSError, KeyError, TypeError):
            return self._unavailable(fallback_zone, observed_at, "ENERGY_HISTORY_CONFIGURATION_INVALID")

        if set(entity_ids) != set(self.CAPABILITIES):
            return self._unavailable(config.time_zone, observed_at, "ENERGY_HISTORY_CAPABILITY_NOT_FOUND")

        local_now = observed_at.astimezone(local_zone)
        history_start = (local_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)).astimezone(timezone.utc)
        tasks = {
            key: home_assistant_service.get_history(entity_id=entity_id, start_time=history_start, end_time=observed_at)
            for key, entity_id in entity_ids.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        histories: dict[str, list[HomeAssistantHistoryStateSchema]] = {}
        for key, result in zip(tasks, results, strict=True):
            if isinstance(result, (httpx.HTTPError, OSError, ValueError)):
                continue
            if isinstance(result, Exception):
                continue
            histories[key] = result

        observation_histories = load_observation_histories(
            history_start,
            observed_at,
            set(self.CAPABILITIES),
        )
        histories = merge_histories(histories, observation_histories)

        try:
            tariff = tariff_service.get_context()
            price = tariff.current.price_per_kwh if tariff.current else None
            currency = tariff.current.currency if tariff.current else "CNY"
        except Exception:
            price = None
            currency = "CNY"
        if price is None:
            return self._unavailable(config.time_zone, observed_at, "TARIFF_REFERENCE_UNAVAILABLE")

        return self.from_histories(
            histories=histories,
            time_zone=config.time_zone,
            observed_at=observed_at,
            tariff_price_per_kwh=price,
            currency=currency,
            max_hold_seconds=energy_observation_policy.max_hold_seconds,
            source_provider="guangheng_observation_store+home_assistant_recorder",
        )

    @classmethod
    def _unavailable(cls, time_zone: str, observed_at: datetime, error_code: str) -> EnergyTodayResponseSchema:
        local_date = observed_at.astimezone(ZoneInfo(time_zone)).date()
        return EnergyTodayResponseSchema(
            available=False,
            date=local_date,
            time_zone=time_zone,
            summary=EnergyTodaySummarySchema(),
            source=EnergyTodaySourceSchema(),
            observed_at=observed_at,
            error_code=error_code,
        )


energy_today_service = EnergyTodayService()
