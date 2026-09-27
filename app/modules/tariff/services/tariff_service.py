from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from app.modules.tariff.schemas.tariff import (
    TariffContextSchema,
    TariffCurrentSchema,
    TariffSourceSchema,
)


BASE_DIR = Path(__file__).resolve().parents[4]
TARIFF_POLICY_PATH = BASE_DIR / "config" / "tariff_policy.yaml"


class TariffPolicyError(RuntimeError):
    pass


class _TariffReferencePolicy(BaseModel):
    price_per_kwh: float = Field(gt=0)
    provider: str = Field(min_length=1)
    reference_date: str | None = None
    realtime: bool


class _TariffPolicy(BaseModel):
    country: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    pricing_type: str = Field(min_length=1)
    reference: _TariffReferencePolicy


class TariffService:
    @staticmethod
    def load_policy() -> _TariffPolicy:
        try:
            with TARIFF_POLICY_PATH.open("r", encoding="utf-8") as file:
                raw_policy = yaml.safe_load(file) or {}
            policy = _TariffPolicy.model_validate(raw_policy)
        except (OSError, ValidationError, yaml.YAMLError) as exc:
            raise TariffPolicyError("Tariff reference policy is invalid.") from exc

        if policy.unit != "kWh":
            raise TariffPolicyError("Tariff reference policy unit must be kWh.")
        if policy.reference.realtime:
            raise TariffPolicyError(
                "Reference-average tariff cannot be marked as realtime."
            )
        return policy

    def get_context(self) -> TariffContextSchema:
        policy = self.load_policy()
        reference = policy.reference
        return TariffContextSchema(
            available=True,
            current=TariffCurrentSchema(
                price_per_kwh=reference.price_per_kwh,
                currency=policy.currency,
                period=None,
            ),
            source=TariffSourceSchema(
                provider=reference.provider,
                pricing_type=policy.pricing_type,
                region=policy.country,
                reference_date=reference.reference_date,
                realtime=reference.realtime,
            ),
            observed_at=datetime.now(timezone.utc),
        )


tariff_service = TariffService()
