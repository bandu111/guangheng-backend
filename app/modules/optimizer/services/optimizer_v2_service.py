from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.modules.decision_context.schemas.decision_context import DecisionContextSchema
from app.modules.device_registry.schemas.device_registry import DeviceCapabilitySchema
from app.modules.optimizer.schemas.optimizer_v2 import (
    OptimizationDecisionV2Schema,
    OptimizerV2EvidenceSchema,
)
from app.modules.strategy.models.strategy import StrategyMode


BASE_DIR = Path(__file__).resolve().parents[4]
OPTIMIZER_POLICY_V2_PATH = BASE_DIR / "config" / "optimizer_policy_v2.yaml"


class OptimizerV2PolicyError(RuntimeError):
    pass


class _HorizonsPolicy(BaseModel):
    primary_hours: int = Field(gt=0)
    secondary_hours: int = Field(gt=0)


class _NetThresholdsPolicy(BaseModel):
    strong_surplus: float
    balanced_lower: float
    balanced_upper: float
    moderate_deficit: float

    @model_validator(mode="after")
    def validate_order(self):
        if not (
            self.moderate_deficit
            < self.balanced_lower
            <= self.balanced_upper
            <= self.strong_surplus
        ):
            raise ValueError("Net-energy thresholds are not ordered.")
        return self


class _ReserveTargetsPolicy(BaseModel):
    strong_surplus: float
    balanced: float
    moderate_deficit: float
    strong_deficit: float


class _AutoPolicy(BaseModel):
    baseline_reserve_percent: float
    minimum_reserve_percent: float
    maximum_reserve_percent: float
    horizons: _HorizonsPolicy
    net_energy_thresholds_kwh: _NetThresholdsPolicy
    reserve_targets: _ReserveTargetsPolicy

    @model_validator(mode="after")
    def validate_reserve_range(self):
        if self.minimum_reserve_percent > self.maximum_reserve_percent:
            raise ValueError("AUTO reserve bounds are invalid.")
        return self


class _ConfidencePolicy(BaseModel):
    minimum_for_dynamic_adjustment: str


class _OptimizerV2Policy(BaseModel):
    version: str
    auto: _AutoPolicy
    confidence: _ConfidencePolicy


class OptimizerV2Service:
    CONFIDENCE_RANK = {
        "UNAVAILABLE": 0,
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
    }

    @staticmethod
    def load_policy() -> _OptimizerV2Policy:
        try:
            with OPTIMIZER_POLICY_V2_PATH.open("r", encoding="utf-8") as file:
                policy = _OptimizerV2Policy.model_validate(
                    yaml.safe_load(file) or {}
                )
        except (OSError, ValidationError, yaml.YAMLError) as exc:
            raise OptimizerV2PolicyError("Optimizer V2 policy is invalid.") from exc

        minimum = policy.confidence.minimum_for_dynamic_adjustment
        if minimum not in OptimizerV2Service.CONFIDENCE_RANK:
            raise OptimizerV2PolicyError(
                "Optimizer V2 minimum confidence is invalid."
            )
        return policy

    @classmethod
    def _lowest_confidence(cls, values: list[Any]) -> str:
        normalized = [
            getattr(value, "value", str(value))
            for value in values
        ]
        if not normalized:
            return "UNAVAILABLE"
        return min(
            normalized,
            key=lambda value: cls.CONFIDENCE_RANK.get(value, -1),
        )

    @classmethod
    def _forecast_confidence(cls, forecast: Any, hours: int) -> str:
        if forecast is None or not forecast.available:
            return "UNAVAILABLE"
        points = forecast.forecast[:hours]
        if len(points) < hours:
            return "UNAVAILABLE"
        return cls._lowest_confidence([point.confidence for point in points])

    @staticmethod
    def _difference(left: float | None, right: float | None) -> float | None:
        if left is None or right is None:
            return None
        return left - right

    @classmethod
    def _evidence(
        cls,
        context: DecisionContextSchema,
        policy: _OptimizerV2Policy,
    ) -> OptimizerV2EvidenceSchema:
        energy = context.energy
        solar = context.solar_forecast
        load = context.load_forecast
        tariff = context.tariff

        solar_6h = solar.summary.next_6h_energy_kwh if solar else None
        load_6h = load.summary.next_6h_energy_kwh if load else None
        solar_24h = solar.summary.next_24h_energy_kwh if solar else None
        load_24h = load.summary.next_24h_energy_kwh if load else None
        net_6h = cls._difference(solar_6h, load_6h)
        net_24h = cls._difference(solar_24h, load_24h)

        primary_hours = policy.auto.horizons.primary_hours
        secondary_hours = policy.auto.horizons.secondary_hours
        solar_confidence = cls._forecast_confidence(
            solar,
            max(primary_hours, secondary_hours),
        )
        load_confidence = cls._forecast_confidence(
            load,
            max(primary_hours, secondary_hours),
        )
        decision_confidence = cls._lowest_confidence(
            [solar_confidence, load_confidence]
        )

        tariff_current = tariff.current if tariff and tariff.available else None
        tariff_source = tariff.source if tariff and tariff.available else None
        projected_grid_need = (
            max(0.0, load_24h - solar_24h)
            if load_24h is not None and solar_24h is not None
            else None
        )
        reference_cost = None
        if (
            projected_grid_need is not None
            and tariff_current is not None
            and tariff_source is not None
            and tariff_source.pricing_type == "reference_average"
            and tariff_source.realtime is False
        ):
            reference_cost = round(
                projected_grid_need * tariff_current.price_per_kwh,
                2,
            )

        weather_current = (
            context.weather.current
            if context.weather and context.weather.available
            else None
        )
        storage = energy.storage if energy else None
        return OptimizerV2EvidenceSchema(
            current_soc_percent=storage.soc_percent if storage else None,
            battery_capacity_kwh=storage.capacity_kwh if storage else None,
            solar_6h_kwh=solar_6h,
            load_6h_kwh=load_6h,
            net_energy_6h_kwh=net_6h,
            solar_24h_kwh=solar_24h,
            load_24h_kwh=load_24h,
            net_energy_24h_kwh=net_24h,
            solar_forecast_confidence=solar_confidence,
            load_forecast_confidence=load_confidence,
            decision_confidence=decision_confidence,
            weather_condition=weather_current.condition if weather_current else None,
            weather_cloud_cover_percent=(
                weather_current.cloud_cover_percent if weather_current else None
            ),
            tariff_price_per_kwh=(
                tariff_current.price_per_kwh if tariff_current else None
            ),
            tariff_pricing_type=(
                tariff_source.pricing_type if tariff_source else None
            ),
            tariff_realtime=(tariff_source.realtime if tariff_source else None),
            projected_grid_energy_need_kwh=projected_grid_need,
            estimated_reference_grid_cost_cny=reference_cost,
        )

    @staticmethod
    def _current_value(capability: DeviceCapabilitySchema | None) -> float | None:
        if capability is None or capability.name != "backup_reserve":
            return None
        try:
            return float(capability.value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _strategy_reason(
        mode: StrategyMode,
        target: float,
    ) -> tuple[str, str, str]:
        if mode == StrategyMode.BACKUP:
            return (
                "STRATEGY_BACKUP_BASELINE",
                f"BACKUP 模式保持 {target:g}% 最低备电 Reserve，优先保留停电保障能力。",
                "strategy.BACKUP.baseline",
            )
        return (
            "STRATEGY_SAVE_BASELINE",
            f"SAVE 模式保持用户设定的 {target:g}% Reserve 基线。",
            "strategy.SAVE.baseline",
        )

    def optimize(
        self,
        *,
        context: DecisionContextSchema,
        capability: DeviceCapabilitySchema | None,
    ) -> OptimizationDecisionV2Schema:
        policy = self.load_policy()
        evidence = self._evidence(context, policy)
        strategy = context.strategy
        mode = strategy.mode if strategy else StrategyMode.AUTO
        baseline = strategy.backup_reserve_target if strategy else None
        current = self._current_value(capability)
        device_id = (
            context.energy.source.device_id
            if context.energy and context.energy.source
            else None
        )

        if baseline is None:
            return OptimizationDecisionV2Schema(
                version=policy.version,
                action_required=False,
                device_id=device_id,
                current_value=current,
                strategy_mode=mode,
                decision_confidence=evidence.decision_confidence,
                reason_code="CONTEXT_UNAVAILABLE",
                reason="当前 Decision Context 缺少 Strategy，无法确定 Reserve 基线。",
                evidence=evidence,
                policy_rule="context.strategy.required",
            )

        if mode in {StrategyMode.BACKUP, StrategyMode.SAVE}:
            reason_code, reason, policy_rule = self._strategy_reason(mode, baseline)
            target = baseline
        else:
            target = baseline
            minimum_confidence = (
                policy.confidence.minimum_for_dynamic_adjustment
            )
            metrics_available = (
                evidence.net_energy_6h_kwh is not None
                and evidence.net_energy_24h_kwh is not None
            )
            if not metrics_available:
                reason_code = "CONTEXT_UNAVAILABLE"
                reason = (
                    f"预测上下文不完整，AUTO 模式保持 {baseline:g}% Reserve 基线，"
                    "不使用不完整预测进行动态调整。"
                )
                policy_rule = "auto.context_fallback"
            elif (
                self.CONFIDENCE_RANK[evidence.decision_confidence]
                < self.CONFIDENCE_RANK[minimum_confidence]
            ):
                reason_code = "FORECAST_CONFIDENCE_INSUFFICIENT"
                reason = (
                    f"Solar Forecast 置信度为 {evidence.solar_forecast_confidence}，"
                    f"Load Forecast 置信度为 {evidence.load_forecast_confidence}；"
                    f"低于动态调整要求 {minimum_confidence}，AUTO 模式保持 "
                    f"{baseline:g}% Reserve 基线。"
                )
                policy_rule = "auto.confidence_gate"
            else:
                thresholds = policy.auto.net_energy_thresholds_kwh
                targets = policy.auto.reserve_targets
                net_6h = evidence.net_energy_6h_kwh
                if net_6h >= thresholds.strong_surplus:
                    target = targets.strong_surplus
                    reason_code = "AUTO_FORECAST_STRONG_SURPLUS"
                    label = "净能源盈余"
                    policy_rule = "auto.net_6h.strong_surplus"
                elif (
                    thresholds.balanced_lower
                    <= net_6h
                    <= thresholds.balanced_upper
                ):
                    target = targets.balanced
                    reason_code = "AUTO_FORECAST_BALANCED"
                    label = "能源基本平衡"
                    policy_rule = "auto.net_6h.balanced"
                elif net_6h >= thresholds.moderate_deficit:
                    target = targets.moderate_deficit
                    reason_code = "AUTO_FORECAST_MODERATE_DEFICIT"
                    label = "中等净能源缺口"
                    policy_rule = "auto.net_6h.moderate_deficit"
                else:
                    target = targets.strong_deficit
                    reason_code = "AUTO_FORECAST_STRONG_DEFICIT"
                    label = "较强净能源缺口"
                    policy_rule = "auto.net_6h.strong_deficit"

                target = min(
                    policy.auto.maximum_reserve_percent,
                    max(policy.auto.minimum_reserve_percent, target),
                )
                reason = (
                    f"未来 6 小时预计光伏 {evidence.solar_6h_kwh:.2f} kWh，"
                    f"家庭负载 {evidence.load_6h_kwh:.2f} kWh，"
                    f"净能源 {evidence.net_energy_6h_kwh:.2f} kWh（{label}）。"
                    f"AUTO 模式将最低 Reserve 目标设为 {target:g}%。"
                    f"未来 24 小时净能源 {evidence.net_energy_24h_kwh:.2f} kWh "
                    "仅作为次级风险证据。"
                )

        if current is None or device_id is None:
            return OptimizationDecisionV2Schema(
                version=policy.version,
                action_required=False,
                device_id=device_id,
                current_value=current,
                target_value=target,
                strategy_mode=mode,
                decision_confidence=evidence.decision_confidence,
                reason_code="CONTEXT_UNAVAILABLE",
                reason="当前 backup_reserve capability 或设备上下文不可用。",
                evidence=evidence,
                policy_rule="capability.backup_reserve.required",
            )

        action_required = abs(current - target) > 0.01
        if not action_required:
            reason_code = "TARGET_ALREADY_SATISFIED"
            reason = f"当前 backup_reserve 已达到 {target:g}% 目标，无需创建 Proposal。"

        return OptimizationDecisionV2Schema(
            version=policy.version,
            action_required=action_required,
            device_id=device_id,
            current_value=current,
            target_value=target,
            strategy_mode=mode,
            decision_confidence=evidence.decision_confidence,
            reason_code=reason_code,
            reason=reason,
            evidence=evidence,
            policy_rule=policy_rule,
        )


optimizer_v2_service = OptimizerV2Service()
