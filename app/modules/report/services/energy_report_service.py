import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, Field, ValidationError

from app.modules.device_registry.services.device_discovery_service import device_discovery_service
from app.modules.energy_state.services.energy_today_service import EnergyTodayService
from app.modules.energy_state.services.energy_observation_history import (
    load_observation_histories,
    merge_histories,
)
from app.modules.energy_state.services.energy_observation_policy_service import (
    energy_observation_policy,
)
from app.modules.home_assistant.schemas.home_assistant import HomeAssistantHistoryStateSchema
from app.modules.home_assistant.services.home_assistant_service import HomeAssistantConfigInvalidError, home_assistant_service
from app.modules.report.schemas.energy_report import (
    EnergyReportCarbonSourceSchema,
    EnergyReportDailyPointSchema,
    EnergyReportMetricsSchema,
    EnergyReportPeriodSchema,
    EnergyReportResponseSchema,
    EnergyReportSourceSchema,
    EnergyReportTariffSourceSchema,
)
from app.modules.tariff.services.tariff_service import tariff_service


BASE_DIR = Path(__file__).resolve().parents[4]
REPORT_POLICY_PATH = BASE_DIR / "config" / "report_policy.yaml"


class _CarbonPolicy(BaseModel):
    factor_kg_co2_per_kwh: float = Field(gt=0)
    provider: str
    reference_year: int
    published_date: str
    source_url: str


class _CostPolicy(BaseModel):
    baseline_method: str
    actual_method: str
    savings_method: str


class _ReportPolicy(BaseModel):
    country: str
    carbon: _CarbonPolicy
    cost: _CostPolicy


class EnergyReportService:
    CAPABILITIES = {
        "solar": "solar_power",
        "home": "home_load",
        "grid_import": "grid_import_power",
        "grid_export": "grid_export_power",
    }

    @staticmethod
    def load_policy() -> _ReportPolicy:
        try:
            with REPORT_POLICY_PATH.open("r", encoding="utf-8") as file:
                return _ReportPolicy.model_validate(yaml.safe_load(file) or {})
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            raise RuntimeError("Report policy is invalid.") from exc

    @classmethod
    def _legacy_entity_ids(cls) -> dict[str, str]:
        telemetry = device_discovery_service.load_capability_matrix().get("telemetry", {})
        result: dict[str, str] = {}
        for key, capability_name in cls.CAPABILITIES.items():
            capability = telemetry.get(capability_name)
            if isinstance(capability, dict) and isinstance(capability.get("entity_id"), str):
                result[key] = capability["entity_id"]
        return result

    @classmethod
    async def _entity_ids(cls) -> dict[str, str]:
        try:
            dynamic = await device_discovery_service.resolve_storage_telemetry_entity_ids(
                cls.CAPABILITIES
            )
        except Exception:
            dynamic = {}
        return dynamic or cls._legacy_entity_ids()

    @staticmethod
    def _period_starts(local_now: datetime) -> dict[str, datetime]:
        today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        return {
            "today": today,
            "week": today - timedelta(days=today.weekday()),
            "month": today.replace(day=1),
        }

    @staticmethod
    def _value(series: dict[str, Any], key: str) -> float | None:
        result = series.get(key)
        return result.energy_kwh if result is not None else None

    @classmethod
    def _metrics(
        cls,
        series: dict[str, Any],
        *,
        tariff: float,
        carbon_factor: float,
    ) -> EnergyReportMetricsSchema:
        consumption = cls._value(series, "home")
        generation = cls._value(series, "solar")
        grid_import = cls._value(series, "grid_import")
        grid_export = cls._value(series, "grid_export")
        self_consumption = max(generation - grid_export, 0) if generation is not None and grid_export is not None else None
        self_use = self_consumption / generation * 100 if self_consumption is not None and generation and generation > 0 else None
        baseline = consumption * tariff if consumption is not None else None
        actual = grid_import * tariff if grid_import is not None else None
        savings = max(baseline - actual, 0) if baseline is not None and actual is not None else None
        avoided = max(consumption - grid_import, 0) if consumption is not None and grid_import is not None else None
        return EnergyReportMetricsSchema(
            consumption_kwh=EnergyTodayService._round(consumption),
            generation_kwh=EnergyTodayService._round(generation),
            grid_import_kwh=EnergyTodayService._round(grid_import),
            grid_export_kwh=EnergyTodayService._round(grid_export),
            solar_self_consumption_kwh=EnergyTodayService._round(self_consumption),
            solar_self_use_percent=EnergyTodayService._round(self_use, 1),
            reference_baseline_cost_cny=EnergyTodayService._round(baseline, 2),
            actual_grid_cost_cny=EnergyTodayService._round(actual, 2),
            savings_cny=EnergyTodayService._round(savings, 2),
            savings_percent=EnergyTodayService._round(savings / baseline * 100, 1) if savings is not None and baseline and baseline > 0 else None,
            carbon_reduction_kg=EnergyTodayService._round(avoided * carbon_factor, 2) if avoided is not None else None,
        )

    @classmethod
    def from_histories(
        cls,
        *,
        histories: dict[str, list[HomeAssistantHistoryStateSchema]],
        time_zone: str,
        observed_at: datetime,
        tariff_price_per_kwh: float,
        tariff_source: EnergyReportTariffSourceSchema,
        policy: _ReportPolicy,
        max_hold_seconds: int | None = None,
        source_provider: str = "home_assistant_recorder",
    ) -> EnergyReportResponseSchema:
        zone = ZoneInfo(time_zone)
        local_now = observed_at.astimezone(zone)
        periods: dict[str, EnergyReportPeriodSchema] = {}
        for name, local_start in cls._period_starts(local_now).items():
            start_at = local_start.astimezone(timezone.utc)
            series = {
                key: EnergyTodayService.aggregate_series(
                    history=history,
                    start_at=start_at,
                    end_at=observed_at,
                    local_zone=zone,
                    max_hold_seconds=max_hold_seconds,
                )
                for key, history in histories.items()
            }
            metrics = cls._metrics(series, tariff=tariff_price_per_kwh, carbon_factor=policy.carbon.factor_kg_co2_per_kwh)
            daily: list[EnergyReportDailyPointSchema] = []
            cursor = local_start
            while cursor < local_now:
                day_end_local = min(cursor + timedelta(days=1), local_now)
                day_series = {
                    key: EnergyTodayService.aggregate_series(
                        history=history,
                        start_at=cursor.astimezone(timezone.utc),
                        end_at=day_end_local.astimezone(timezone.utc),
                        local_zone=zone,
                        max_hold_seconds=max_hold_seconds,
                    )
                    for key, history in histories.items()
                }
                day_metrics = cls._metrics(day_series, tariff=tariff_price_per_kwh, carbon_factor=policy.carbon.factor_kg_co2_per_kwh)
                daily.append(EnergyReportDailyPointSchema(
                    date=cursor.date(),
                    consumption_kwh=day_metrics.consumption_kwh,
                    generation_kwh=day_metrics.generation_kwh,
                    grid_import_kwh=day_metrics.grid_import_kwh,
                    actual_grid_cost_cny=day_metrics.actual_grid_cost_cny,
                    savings_cny=day_metrics.savings_cny,
                    carbon_reduction_kg=day_metrics.carbon_reduction_kg,
                ))
                cursor += timedelta(days=1)
            coverages = [item.coverage_percent for item in series.values() if item.sample_count > 0]
            periods[name] = EnergyReportPeriodSchema(
                period=name,
                start_at=local_start,
                end_at=local_now,
                metrics=metrics,
                daily=daily,
                coverage_percent=round(min(coverages), 1) if coverages else 0,
            )

        available = bool(periods.get("today") and periods["today"].metrics.consumption_kwh is not None)
        return EnergyReportResponseSchema(
            available=available,
            periods=periods,
            tariff=tariff_source,
            carbon=EnergyReportCarbonSourceSchema(
                factor_kg_co2_per_kwh=policy.carbon.factor_kg_co2_per_kwh,
                provider=policy.carbon.provider,
                region=policy.country,
                reference_year=policy.carbon.reference_year,
                published_date=policy.carbon.published_date,
                source_url=policy.carbon.source_url,
            ),
            source=EnergyReportSourceSchema(
                provider=source_provider,
                cost_baseline_method=policy.cost.baseline_method,
                actual_cost_method=policy.cost.actual_method,
                savings_method=policy.cost.savings_method,
            ),
            observed_at=observed_at,
            error_code=None if available else "INSUFFICIENT_REPORT_HISTORY",
        )

    async def get_report(self) -> EnergyReportResponseSchema:
        observed_at = datetime.now(timezone.utc)
        policy = self.load_policy()
        try:
            config = await home_assistant_service.get_config()
            zone = ZoneInfo(config.time_zone)
            entity_ids = await self._entity_ids()
            tariff = tariff_service.get_context()
            if tariff.current is None:
                raise RuntimeError("Tariff current value unavailable.")
        except (HomeAssistantConfigInvalidError, ZoneInfoNotFoundError, OSError, RuntimeError, KeyError, TypeError):
            return self._unavailable(observed_at, policy, "REPORT_CONTEXT_UNAVAILABLE")

        local_now = observed_at.astimezone(zone)
        earliest = min(self._period_starts(local_now).values()).astimezone(timezone.utc)
        tasks = {
            key: home_assistant_service.get_history(entity_id=entity_id, start_time=earliest, end_time=observed_at)
            for key, entity_id in entity_ids.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        histories = {
            key: result
            for key, result in zip(tasks, results, strict=True)
            if isinstance(result, list)
        }
        observation_histories = load_observation_histories(
            earliest,
            observed_at,
            set(self.CAPABILITIES),
        )
        histories = merge_histories(histories, observation_histories)
        tariff_source = EnergyReportTariffSourceSchema(
            price_per_kwh=tariff.current.price_per_kwh,
            currency=tariff.current.currency,
            provider=tariff.source.provider,
            pricing_type=tariff.source.pricing_type,
            realtime=tariff.source.realtime,
            reference_date=tariff.source.reference_date,
        )
        return self.from_histories(
            histories=histories,
            time_zone=config.time_zone,
            observed_at=observed_at,
            tariff_price_per_kwh=tariff.current.price_per_kwh,
            tariff_source=tariff_source,
            policy=policy,
            max_hold_seconds=energy_observation_policy.max_hold_seconds,
            source_provider="guangheng_observation_store+home_assistant_recorder",
        )

    @staticmethod
    def _unavailable(observed_at: datetime, policy: _ReportPolicy, error_code: str) -> EnergyReportResponseSchema:
        return EnergyReportResponseSchema(
            available=False,
            source=EnergyReportSourceSchema(
                cost_baseline_method=policy.cost.baseline_method,
                actual_cost_method=policy.cost.actual_method,
                savings_method=policy.cost.savings_method,
            ),
            observed_at=observed_at,
            error_code=error_code,
        )


energy_report_service = EnergyReportService()
