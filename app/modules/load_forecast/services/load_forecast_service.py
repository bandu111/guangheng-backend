import math
from datetime import datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from sqlalchemy.orm import Session

from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.energy_state.services.energy_state_service import energy_state_service
from app.modules.home_assistant.schemas.home_assistant import (
    HomeAssistantHistoryStateSchema,
)
from app.modules.home_assistant.services.home_assistant_service import (
    HomeAssistantConfigInvalidError,
    home_assistant_service,
)
from app.modules.load_forecast.schemas.load_forecast import (
    LoadForecastConfidence,
    LoadForecastPointSchema,
    LoadForecastResponseSchema,
    LoadForecastSummarySchema,
)


class LoadForecastService:
    METHOD = "historical_hour_slot_median_with_current_calibration_v1"
    HISTORY_DAYS = 7
    CALIBRATION_WEIGHTS = (0.60, 0.35, 0.15)

    @classmethod
    def _unavailable(
        cls,
        error_code: str,
        *,
        current_load_w: float | None = None,
    ) -> LoadForecastResponseSchema:
        return LoadForecastResponseSchema(
            available=False,
            method=cls.METHOD,
            history_days_requested=cls.HISTORY_DAYS,
            history_samples=0,
            current_load_w=current_load_w,
            summary=LoadForecastSummarySchema(),
            error_code=error_code,
        )

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
        return parsed

    @staticmethod
    def _parse_load(value: str) -> float | None:
        normalized = value.strip().lower()
        if normalized in {"", "unknown", "unavailable", "none", "null"}:
            return None
        try:
            number = float(normalized)
        except ValueError:
            return None
        if not math.isfinite(number) or number < 0:
            return None
        return number

    @classmethod
    def _clean_history(
        cls,
        history: list[HomeAssistantHistoryStateSchema],
    ) -> list[tuple[datetime, float]]:
        cleaned: list[tuple[datetime, float]] = []
        for item in history:
            value = cls._parse_load(item.state)
            timestamp = cls._parse_timestamp(
                item.last_updated or item.last_changed
            )
            if value is None or timestamp is None:
                continue
            cleaned.append((timestamp.astimezone(timezone.utc), value))
        return sorted(cleaned, key=lambda sample: sample[0])

    @staticmethod
    def _ceil_local_hour(value: datetime) -> datetime:
        hour = value.replace(minute=0, second=0, microsecond=0)
        if value == hour:
            return hour
        return hour + timedelta(hours=1)

    @classmethod
    def _hourly_observations(
        cls,
        cleaned: list[tuple[datetime, float]],
        local_zone: ZoneInfo,
        observed_at: datetime,
    ) -> list[tuple[datetime, float]]:
        if not cleaned:
            return []

        first_local = cleaned[0][0].astimezone(local_zone)
        current_hour = observed_at.astimezone(local_zone).replace(
            minute=0,
            second=0,
            microsecond=0,
        )
        cursor = cls._ceil_local_hour(first_local)
        sample_index = 0
        active_value: float | None = None
        observations: list[tuple[datetime, float]] = []

        while cursor < current_hour:
            cursor_utc = cursor.astimezone(timezone.utc)
            while (
                sample_index < len(cleaned)
                and cleaned[sample_index][0] <= cursor_utc
            ):
                active_value = cleaned[sample_index][1]
                sample_index += 1
            if active_value is not None:
                observations.append((cursor, active_value))
            cursor += timedelta(hours=1)

        # Very short Recorder windows may contain a valid state but no full hour yet.
        if not observations:
            return [
                (timestamp.astimezone(local_zone), value)
                for timestamp, value in cleaned
            ]
        return observations

    @staticmethod
    def _confidence(sample_count: int) -> LoadForecastConfidence:
        if sample_count >= 5:
            return LoadForecastConfidence.HIGH
        if sample_count >= 3:
            return LoadForecastConfidence.MEDIUM
        if sample_count >= 1:
            return LoadForecastConfidence.LOW
        return LoadForecastConfidence.UNAVAILABLE

    @staticmethod
    def _energy_for_hours(
        points: list[LoadForecastPointSchema],
        hours: int,
    ) -> float | None:
        selected = points[:hours]
        if len(selected) < hours or any(
            point.load_power_w is None for point in selected
        ):
            return None
        # V1 uses an hourly discrete approximation: sum(power W * 1h) / 1000.
        return sum(point.load_power_w for point in selected) / 1000

    @classmethod
    def _summary(
        cls,
        points: list[LoadForecastPointSchema],
    ) -> LoadForecastSummarySchema:
        complete = len(points) == 24 and all(
            point.load_power_w is not None for point in points
        )
        peak = (
            max(points, key=lambda point: point.load_power_w)
            if complete
            else None
        )
        return LoadForecastSummarySchema(
            next_1h_energy_kwh=cls._energy_for_hours(points, 1),
            next_3h_energy_kwh=cls._energy_for_hours(points, 3),
            next_6h_energy_kwh=cls._energy_for_hours(points, 6),
            next_24h_energy_kwh=cls._energy_for_hours(points, 24),
            peak_power_w=peak.load_power_w if peak else None,
            peak_time=peak.time if peak else None,
        )

    @staticmethod
    def _home_load_entity_id() -> str | None:
        matrix = device_discovery_service.load_capability_matrix()
        capability = matrix.get("telemetry", {}).get("home_load")
        if not isinstance(capability, dict):
            return None
        entity_id = capability.get("entity_id")
        return entity_id if isinstance(entity_id, str) and entity_id else None

    def forecast_from_history(
        self,
        *,
        history: list[HomeAssistantHistoryStateSchema],
        current_load_w: float,
        time_zone: str,
        observed_at: datetime,
    ) -> LoadForecastResponseSchema:
        try:
            local_zone = ZoneInfo(time_zone)
        except ZoneInfoNotFoundError:
            return self._unavailable(
                "HISTORY_PROVIDER_UNAVAILABLE",
                current_load_w=current_load_w,
            )

        cleaned = self._clean_history(history)
        if not cleaned:
            return self._unavailable(
                "INSUFFICIENT_LOAD_HISTORY",
                current_load_w=current_load_w,
            )

        observations = self._hourly_observations(
            cleaned,
            local_zone,
            observed_at,
        )
        if not observations:
            return self._unavailable(
                "INSUFFICIENT_LOAD_HISTORY",
                current_load_w=current_load_w,
            )

        slots: dict[int, list[float]] = {}
        for local_time, value in observations:
            slots.setdefault(local_time.hour, []).append(value)

        baselines = {
            hour: float(median(values))
            for hour, values in slots.items()
        }
        observed_local = observed_at.astimezone(local_zone)
        current_baseline = baselines.get(observed_local.hour)
        current_deviation = (
            current_load_w - current_baseline
            if current_baseline is not None
            else None
        )
        next_hour = observed_local.replace(
            minute=0,
            second=0,
            microsecond=0,
        ) + timedelta(hours=1)

        points: list[LoadForecastPointSchema] = []
        for index in range(24):
            forecast_time = next_hour + timedelta(hours=index)
            values = slots.get(forecast_time.hour, [])
            baseline = baselines.get(forecast_time.hour)
            sample_count = len(values)
            forecast_value = baseline
            if (
                forecast_value is not None
                and current_deviation is not None
                and index < len(self.CALIBRATION_WEIGHTS)
            ):
                forecast_value = max(
                    0.0,
                    forecast_value
                    + current_deviation * self.CALIBRATION_WEIGHTS[index],
                )

            points.append(
                LoadForecastPointSchema(
                    time=forecast_time,
                    load_power_w=forecast_value,
                    historical_samples=sample_count,
                    confidence=self._confidence(sample_count),
                )
            )

        return LoadForecastResponseSchema(
            available=True,
            method=self.METHOD,
            history_days_requested=self.HISTORY_DAYS,
            history_samples=len(observations),
            history_start_at=cleaned[0][0],
            history_end_at=observed_at,
            current_load_w=current_load_w,
            forecast=points,
            summary=self._summary(points),
            observed_at=observed_at,
        )

    async def get_forecast(self, db: Session) -> LoadForecastResponseSchema:
        try:
            entity_id = self._home_load_entity_id()
        except (OSError, KeyError, TypeError):
            entity_id = None
        if entity_id is None:
            return self._unavailable("HOME_LOAD_CAPABILITY_NOT_FOUND")

        try:
            energy = await energy_state_service.get_energy_state(db=db)
        except Exception:
            return self._unavailable("CURRENT_LOAD_UNAVAILABLE")
        current_load_w = energy.power.home_load_w
        if not energy.available or not energy.online or current_load_w is None:
            return self._unavailable("CURRENT_LOAD_UNAVAILABLE")

        observed_at = datetime.now(timezone.utc)
        try:
            config = await home_assistant_service.get_config()
            history = await home_assistant_service.get_history(
                entity_id=entity_id,
                start_time=observed_at - timedelta(days=self.HISTORY_DAYS),
                end_time=observed_at,
            )
        except (
            HomeAssistantConfigInvalidError,
            httpx.HTTPError,
            OSError,
            ValueError,
        ):
            return self._unavailable(
                "HISTORY_PROVIDER_UNAVAILABLE",
                current_load_w=current_load_w,
            )

        return self.forecast_from_history(
            history=history,
            current_load_w=current_load_w,
            time_zone=config.time_zone,
            observed_at=observed_at,
        )


load_forecast_service = LoadForecastService()
