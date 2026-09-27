import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.core.database import Base
from app.core.database import get_db
from app.main import app
from app.modules.hermes.models.agent_conversation import AgentMessage, AgentToolCall
from app.modules.hermes.services import agent_service as agent_service_module
from app.modules.hermes.services.agent_service import AgentService
from app.modules.hermes.services.hermes_client import (
    GUANGHENG_HERMES_SYSTEM_INSTRUCTION,
    HermesToolEvent,
    HermesTurnResult,
    HermesUnavailableError,
)


def _db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _result(tool: str, data=None, *, success=True, error_code=None) -> str:
    return json.dumps(
        {
            "success": success,
            "tool": tool,
            "data": data,
            "error_code": error_code,
            "message": None,
            "observed_at": "2026-09-19T08:00:00Z",
        }
    )


def _event(tool: str, result: str, *, failed=False, arguments=None) -> HermesToolEvent:
    started = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc)
    return HermesToolEvent(
        message_id=f"tool-{tool}",
        tool_name=f"mcp__guangheng__{tool}",
        arguments=arguments or {},
        started_at=started,
        completed_at=started,
        duration_ms=12,
        failed=failed,
        result_content=result,
    )


class FakeHermesClient:
    def __init__(self, turns):
        self.turns = list(turns)
        self.created = 0
        self.session_ids = []

    async def create_session(self, title):
        self.created += 1
        return "official-hermes-session"

    async def run_session_turn(self, session_id, message):
        self.session_ids.append(session_id)
        return self.turns.pop(0)


def _chat(monkeypatch, db, turns, message="状态", session_id=None):
    fake = FakeHermesClient(turns)
    monkeypatch.setattr(agent_service_module, "hermes_client", fake)
    response = asyncio.run(AgentService().chat(db, message, session_id))
    return response, fake


def test_session_creation_and_lookup():
    db = _db()
    service = AgentService()
    created = service.create_session(db)
    detail = service.get_session(db, created.session_id)
    assert detail.session_id == created.session_id
    assert detail.status == "active"
    assert detail.message_count == 0


def test_session_http_api_create_read_and_list_messages():
    db = _db()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            created = client.post("/api/v1/hermes/sessions")
            assert created.status_code == 200
            session_id = created.json()["session_id"]

            detail = client.get(f"/api/v1/hermes/sessions/{session_id}")
            messages = client.get(f"/api/v1/hermes/sessions/{session_id}/messages")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert detail.status_code == 200
    assert detail.json()["session_id"] == session_id
    assert detail.json()["message_count"] == 0
    assert messages.status_code == 200
    assert messages.json() == {
        "session_id": session_id,
        "count": 0,
        "messages": [],
    }


def test_chat_auto_creates_session_and_persists_two_roles(monkeypatch):
    db = _db()
    turn = HermesTurnResult(answer="当前状态正常。", status="completed")
    response, fake = _chat(monkeypatch, db, [turn])
    messages = AgentService().get_messages(db, response.session_id)
    assert fake.created == 1
    assert [item.role for item in messages.messages] == ["user", "assistant"]
    assert messages.messages[1].content == "当前状态正常。"
    assert messages.messages[1].decision is None
    assert messages.messages[1].proposal is None


def test_existing_session_keeps_official_hermes_conversation(monkeypatch):
    db = _db()
    service = AgentService()
    session_id = service.create_session(db).session_id
    fake = FakeHermesClient(
        [
            HermesTurnResult(answer="第一轮", status="completed"),
            HermesTurnResult(answer="第二轮", status="completed"),
        ]
    )
    monkeypatch.setattr(agent_service_module, "hermes_client", fake)
    asyncio.run(service.chat(db, "状态", session_id))
    asyncio.run(service.chat(db, "需要调整吗", session_id))
    assert fake.created == 1
    assert fake.session_ids == ["official-hermes-session", "official-hermes-session"]
    assert service.get_session(db, session_id).message_count == 4


def test_tool_trace_and_optimizer_decision_come_from_tool_result(monkeypatch):
    db = _db()
    decision = {
        "version": "2.0",
        "strategy_mode": "BACKUP",
        "capability": "backup_reserve",
        "current_value": 80.0,
        "target_value": 80.0,
        "action_required": False,
        "reason_code": "TARGET_ALREADY_SATISFIED",
        "decision_confidence": "HIGH",
    }
    event = _event(
        "evaluate_optimizer",
        _result("evaluate_optimizer", decision),
        arguments={"api_key": "must-not-be-stored", "scope": "current"},
    )
    response, _ = _chat(
        monkeypatch,
        db,
        [HermesTurnResult(answer="自然语言里写 20% 也不能覆盖工具。", status="completed", tool_events=[event])],
    )
    assert response.intent == "energy_decision"
    assert response.decision.target_value == 80.0
    assert response.decision.reason_code == "TARGET_ALREADY_SATISFIED"
    assert response.tools[0].display_name == "运行能源优化器"
    row = db.scalar(select(AgentToolCall))
    assert row.input_summary["api_key"] == "[REDACTED]"
    assert "must-not-be-stored" not in json.dumps(row.input_summary)


def test_pending_proposal_is_mapped_without_approval_or_execution(monkeypatch):
    db = _db()
    proposal = {
        "id": 42,
        "status": "PENDING",
        "capability": "backup_reserve",
        "current_value": 25.0,
        "target_value": 80.0,
        "created_at": "2026-09-19T08:00:00Z",
    }
    event = _event(
        "generate_proposal",
        _result("generate_proposal", {"created": True, "proposal": proposal}),
    )
    response, _ = _chat(
        monkeypatch,
        db,
        [HermesTurnResult(answer="已创建待审批方案。", status="completed", tool_events=[event])],
    )
    assert response.proposal.id == 42
    assert response.proposal.status == "PENDING"
    assert response.status == "completed"


def test_non_pending_proposal_is_rejected(monkeypatch):
    db = _db()
    proposal = {
        "id": 42,
        "status": "APPROVED",
        "capability": "backup_reserve",
        "current_value": 25.0,
        "target_value": 80.0,
        "created_at": "2026-09-19T08:00:00Z",
    }
    event = _event("generate_proposal", _result("generate_proposal", {"proposal": proposal}))
    response, _ = _chat(
        monkeypatch,
        db,
        [HermesTurnResult(answer="方案", status="completed", tool_events=[event])],
    )
    assert response.proposal is None
    assert response.status == "failed"
    assert response.error.code == "TOOL_FAILED"
    assert response.tools[0].success is False
    assert response.tools[0].error_code == "PROPOSAL_STATE_INVALID"


def test_provenance_is_mapped_from_tools(monkeypatch):
    db = _db()
    energy = {
        "available": True,
        "source": {"source_mode": "simulator"},
        "last_updated": "2026-09-19T08:00:00Z",
    }
    weather = {
        "available": True,
        "provider": "open_meteo",
        "observed_at": "2026-09-19T08:01:00Z",
    }
    events = [
        _event("get_energy_state", _result("get_energy_state", energy)),
        _event("get_weather", _result("get_weather", weather)),
    ]
    response, _ = _chat(
        monkeypatch,
        db,
        [HermesTurnResult(answer="状态和天气", status="completed", tool_events=events)],
    )
    assert response.sources["energy"]["provider"] == "home_assistant"
    assert response.sources["energy"]["source_mode"] == "simulator"
    assert response.sources["weather"]["provider"] == "open_meteo"


def test_mcp_unavailable_fails_without_invented_business_data(monkeypatch):
    db = _db()
    event = _event(
        "get_energy_state",
        "MCP channel closed while reading tool result",
        failed=True,
    )
    response, _ = _chat(
        monkeypatch,
        db,
        [HermesTurnResult(answer=None, status="failed", tool_events=[event])],
    )
    assert response.status == "failed"
    assert response.error.code == "MCP_UNAVAILABLE"
    assert response.answer is None
    assert response.decision is None
    assert response.proposal is None


def test_partial_tool_failure_keeps_only_verified_structured_data(monkeypatch):
    db = _db()
    events = [
        _event(
            "get_weather",
            _result("get_weather", {"available": True, "provider": "open_meteo"}),
        ),
        _event(
            "get_solar_forecast",
            _result(
                "get_solar_forecast",
                None,
                success=False,
                error_code="SOLAR_FORECAST_UNAVAILABLE",
            ),
            failed=True,
        ),
    ]
    response, _ = _chat(
        monkeypatch,
        db,
        [HermesTurnResult(answer="天气可用，光伏预测不可用。", status="completed", tool_events=events)],
    )
    assert response.status == "partial"
    assert response.sources["weather"]["provider"] == "open_meteo"
    assert "solar_forecast" not in response.sources
    assert response.error.code == "TOOL_FAILED"


def test_unavailable_and_private_reasoning_are_not_persisted(monkeypatch):
    db = _db()
    service = AgentService()

    class Unavailable:
        async def create_session(self, title):
            raise HermesUnavailableError("secret upstream detail", "HERMES_UNAVAILABLE")

    monkeypatch.setattr(agent_service_module, "hermes_client", Unavailable())
    response = asyncio.run(service.chat(db, "状态"))
    assert response.status == "failed"
    assert response.error.code == "HERMES_UNAVAILABLE"
    stored = "\n".join(db.scalars(select(AgentMessage.content)).all())
    assert "secret upstream detail" not in stored
    assert GUANGHENG_HERMES_SYSTEM_INSTRUCTION not in stored
    assert "reasoning" not in stored.lower()
