from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.modules.energy_state.schemas.energy_state import EnergyStateResponseSchema
from app.modules.energy_state.services.energy_state_service import energy_state_service
from app.modules.solar_forecast.schemas.solar_forecast import (
    SolarForecastConfidence,
    SolarForecastPointSchema,
    SolarForecastResponseSchema,
    SolarForecastSummarySchema,
)
from app.modules.weather.schemas.weather import WeatherContextSchema
from app.modules.weather.services.weather_service import weather_service


class SolarForecastService:
    METHOD = "current_pv_calibration_radiation_ratio_v1"
    MIN_CALIBRATION_RADIATION_W_M2 = 20.0
    HIGH_CONFIDENCE_RADIATION_W_M2 = 100.0
    HIGH_CLOUD_COVER_PERCENT = 70.0

    def __init__(self) -> None:
        self._last_valid_calibration_ratio: float | None = None
        self._last_valid_calibration_at: datetime | None = None

    def clear_calibration(self) -> None:
        self._last_valid_calibration_ratio = None
        self._last_valid_calibration_at = None

    @classmethod
    def _unavailable(
        cls,
        error_code: str,
        *,
        current_solar_w: float | None = None,
        current_radiation: float | None = None,
    ) -> SolarForecastResponseSchema:
        return SolarForecastResponseSchema(
            available=False,
            method=cls.METHOD,
            current_solar_w=current_solar_w,
            current_shortwave_radiation_w_m2=current_radiation,
            summary=SolarForecastSummarySchema(),
            error_code=error_code,
        )

    @staticmethod
    def _energy_for_hours(
        points: list[SolarForecastPointSchema],
        hours: int,
    ) -> float | None:
        selected = points[:hours]
        if len(selected) < hours or any(
            point.solar_power_w is None for point in selected
        ):
            return None

        # V1 uses an hourly discrete approximation: sum(power W * 1h) / 1000.
        return sum(point.solar_power_w for point in selected) / 1000

    @classmethod
    def _summary(
        cls,
        points: list[SolarForecastPointSchema],
    ) -> SolarForecastSummarySchema:
        complete = bool(points) and all(
            point.solar_power_w is not None for point in points
        )
        peak = (
            max(points, key=lambda point: point.solar_power_w)
            if complete
            else None
        )
        return SolarForecastSummarySchema(
            next_1h_energy_kwh=cls._energy_for_hours(points, 1),
            next_3h_energy_kwh=cls._energy_for_hours(points, 3),
            next_6h_energy_kwh=cls._energy_for_hours(points, 6),
            next_24h_energy_kwh=cls._energy_for_hours(points, 24),
            peak_power_w=peak.solar_power_w if peak else None,
            peak_time=peak.time if peak else None,
        )

    @classmethod
    def _calibration_confidence(
        cls,
        current_radiation: float,
        cloud_cover: float | None,
    ) -> SolarForecastConfidence:
        if (
            current_radiation >= cls.HIGH_CONFIDENCE_RADIATION_W_M2
            and (
                cloud_cover is None
                or cloud_cover < cls.HIGH_CLOUD_COVER_PERCENT
            )
        ):
            return SolarForecastConfidence.HIGH
        return SolarForecastConfidence.MEDIUM

    @staticmethod
    def _point_confidence(
        calibration_confidence: SolarForecastConfidence,
        cloud_cover: float | None,
    ) -> SolarForecastConfidence:
        if (
            calibration_confidence == SolarForecastConfidence.HIGH
            and cloud_cover is not None
            and cloud_cover >= 80
        ):
            return SolarForecastConfidence.MEDIUM
        return calibration_confidence

    def forecast_from_context(
        self,
        energy: EnergyStateResponseSchema,
        weather: WeatherContextSchema,
    ) -> SolarForecastResponseSchema:
        current_solar_w = energy.power.solar_w
        if not energy.available or not energy.online or current_solar_w is None:
            return self._unavailable("SOLAR_RUNTIME_UNAVAILABLE")

        if not weather.available or weather.current is None:
            return self._unavailable(
                "WEATHER_UNAVAILABLE",
                current_solar_w=current_solar_w,
            )

        current_radiation = weather.current.shortwave_radiation_w_m2
        if current_radiation is None:
            return self._unavailable(
                "CURRENT_RADIATION_UNAVAILABLE",
                current_solar_w=current_solar_w,
            )

        is_night = weather.current.is_day is False or current_radiation <= 0
        calibration_ratio: float | None = None
        calibration_confidence = SolarForecastConfidence.LOW
        calibration_source: str | None = None
        calibration_observed_at: datetime | None = None

        if (
            not is_night
            and current_solar_w > 0
            and current_radiation >= self.MIN_CALIBRATION_RADIATION_W_M2
        ):
            calibration_ratio = current_solar_w / current_radiation
            calibration_confidence = self._calibration_confidence(
                current_radiation,
                weather.current.cloud_cover_percent,
            )
            calibration_source = "current_daytime_observation"
            calibration_observed_at = datetime.now(timezone.utc)
            self._last_valid_calibration_ratio = calibration_ratio
            self._last_valid_calibration_at = calibration_observed_at
        elif self._last_valid_calibration_ratio is not None:
            calibration_ratio = self._last_valid_calibration_ratio
            calibration_confidence = SolarForecastConfidence.LOW
            calibration_source = "last_valid_daytime_observation"
            calibration_observed_at = self._last_valid_calibration_at
        elif is_night and current_solar_w > 0:
            # Some integrations and the simulator can expose a stable/stale PV
            # value at night. It cannot calibrate against zero current
            # radiation, but it can safely bound a LOW-confidence forecast by
            # normalizing that observed reference power to the strongest
            # radiation in the next 24 hours.
            future_radiation = [
                point.shortwave_radiation_w_m2
                for point in weather.hourly[:24]
                if point.shortwave_radiation_w_m2 is not None
                and point.shortwave_radiation_w_m2 > 0
            ]
            if future_radiation:
                calibration_ratio = current_solar_w / max(future_radiation)
                calibration_confidence = SolarForecastConfidence.LOW
                calibration_source = "night_runtime_reference_normalized"
                calibration_observed_at = datetime.now(timezone.utc)

        points: list[SolarForecastPointSchema] = []
        for hourly in weather.hourly[:24]:
            radiation = hourly.shortwave_radiation_w_m2
            if radiation is None:
                solar_power = None
                confidence = SolarForecastConfidence.UNAVAILABLE
            elif radiation <= 0:
                solar_power = 0.0
                confidence = SolarForecastConfidence.HIGH
            elif calibration_ratio is None:
                solar_power = None
                confidence = SolarForecastConfidence.LOW
            else:
                solar_power = radiation * calibration_ratio
                confidence = self._point_confidence(
                    calibration_confidence,
                    hourly.cloud_cover_percent,
                )

            points.append(
                SolarForecastPointSchema(
                    time=hourly.time,
                    solar_power_w=solar_power,
                    shortwave_radiation_w_m2=radiation,
                    cloud_cover_percent=hourly.cloud_cover_percent,
                    confidence=confidence,
                )
            )

        return SolarForecastResponseSchema(
            available=True,
            method=self.METHOD,
            current_solar_w=current_solar_w,
            current_shortwave_radiation_w_m2=current_radiation,
            calibration_ratio=calibration_ratio,
            calibration_source=calibration_source,
            calibration_observed_at=calibration_observed_at,
            forecast=points,
            summary=self._summary(points),
            observed_at=datetime.now(timezone.utc),
        )

    async def get_forecast(self, db: Session) -> SolarForecastResponseSchema:
        energy = await energy_state_service.get_energy_state(db=db)
        weather = await weather_service.get_weather()
        return self.forecast_from_context(energy, weather)


solar_forecast_service = SolarForecastService()
