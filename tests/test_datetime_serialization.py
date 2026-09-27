from datetime import datetime, timedelta, timezone

from app.core.datetime_serialization import serialize_utc_datetime
from app.modules.proposal.models.proposal import ProposalStatus
from app.modules.proposal.schemas.proposal import ProposalResponseSchema
from app.modules.strategy.models.strategy import StrategyMode


def test_naive_database_datetime_is_serialized_as_explicit_utc() -> None:
    value = serialize_utc_datetime(datetime(2026, 9, 26, 18, 26, 21))

    assert value == "2026-09-26T18:26:21Z"


def test_aware_datetime_is_normalized_to_utc() -> None:
    china_time = datetime(
        2026, 9, 27, 2, 26, 21, tzinfo=timezone(timedelta(hours=8))
    )

    assert serialize_utc_datetime(china_time) == "2026-09-26T18:26:21Z"


def test_proposal_api_schema_emits_timezone_marker() -> None:
    schema = ProposalResponseSchema(
        id=42,
        device_id=1,
        strategy_mode=StrategyMode.AUTO,
        capability="backup_reserve",
        current_value=80,
        target_value=30,
        reason_code="TEST",
        reason="test",
        status=ProposalStatus.SUCCEEDED,
        created_at=datetime(2026, 9, 26, 18, 25),
        updated_at=datetime(2026, 9, 26, 18, 26),
    )

    payload = schema.model_dump(mode="json")

    assert payload["created_at"] == "2026-09-26T18:25:00Z"
    assert payload["updated_at"] == "2026-09-26T18:26:00Z"
