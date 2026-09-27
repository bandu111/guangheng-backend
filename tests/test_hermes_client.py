import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.modules.hermes.services import agent_service as agent_service_module
from app.modules.hermes.services.hermes_client import (
    GUANGHENG_HERMES_SYSTEM_INSTRUCTION,
    HermesClient,
    HermesUnavailableError,
)


def test_hermes_client_calls_official_gateway_without_exposing_key():
    local_gateway_key = "local-gateway-test-key"
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "安全答复"}}
                ]
            },
        )

    client = HermesClient(
        base_url="http://127.0.0.1:8642",
        api_key=local_gateway_key,
        model="hermes-agent",
        transport=httpx.MockTransport(handler),
    )

    answer = asyncio.run(client.chat("读取当前能源情况"))

    assert answer == "安全答复"
    assert captured["url"] == "http://127.0.0.1:8642/v1/chat/completions"
    assert captured["authorization"] == f"Bearer {local_gateway_key}"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "hermes-agent"
    assert body["messages"][0]["content"] == GUANGHENG_HERMES_SYSTEM_INSTRUCTION
    assert body["messages"][1]["content"] == "读取当前能源情况"


def test_hermes_unavailable_error_is_structured_and_does_not_leak_key():
    local_gateway_key = "private-local-gateway-key"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream unavailable")

    client = HermesClient(
        base_url="http://127.0.0.1:8642",
        api_key=local_gateway_key,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(HermesUnavailableError) as error:
        asyncio.run(client.chat("状态"))

    assert local_gateway_key not in str(error.value)
    assert "unavailable" in str(error.value).lower()


def test_invalid_gateway_payload_does_not_expose_response_details():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "sensitive-response"})

    client = HermesClient(
        base_url="http://127.0.0.1:8642",
        api_key="another-local-key",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(HermesUnavailableError) as error:
        asyncio.run(client.chat("状态"))

    assert "sensitive-response" not in str(error.value)


def test_session_stream_correlates_parallel_tools_by_name_not_parent_message_id():
    sse = "\n".join(
        [
            'event: tool.started',
            'data: {"message_id":"42","tool_name":"mcp__guangheng__get_energy_state","args":{},"ts":"2026-09-19T08:00:00Z"}',
            '',
            'event: tool.started',
            'data: {"message_id":"42","tool_name":"mcp__guangheng__get_energy_balance","args":{},"ts":"2026-09-19T08:00:00Z"}',
            '',
            'event: tool.completed',
            'data: {"message_id":"42","tool_name":"mcp__guangheng__get_energy_state","error":false,"ts":"2026-09-19T08:00:01Z"}',
            '',
            'event: tool.completed',
            'data: {"message_id":"42","tool_name":"mcp__guangheng__get_energy_balance","error":false,"ts":"2026-09-19T08:00:02Z"}',
            '',
            'event: assistant.completed',
            'data: {"content":"完成","completed":true,"partial":false}',
            '',
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, text=sse)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 100,
                        "role": "tool",
                        "tool_name": "mcp__guangheng__get_energy_state",
                        "content": '{"result":"{\\"success\\":true,\\"tool\\":\\"get_energy_state\\"}"}',
                    },
                    {
                        "id": 101,
                        "role": "tool",
                        "tool_name": "mcp__guangheng__get_energy_balance",
                        "content": '{"result":"{\\"success\\":true,\\"tool\\":\\"get_energy_balance\\"}"}',
                    },
                ]
            },
        )

    client = HermesClient(
        base_url="http://127.0.0.1:8642",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(client.run_session_turn("session-1", "状态"))

    assert result.status == "completed"
    assert [item.tool_name for item in result.tool_events] == [
        "mcp__guangheng__get_energy_state",
        "mcp__guangheng__get_energy_balance",
    ]
    assert all(item.result_content for item in result.tool_events)


def test_chat_api_returns_structured_error_when_hermes_is_unavailable(monkeypatch):
    async def unavailable(message: str) -> str:
        raise HermesUnavailableError("gateway unavailable")

    monkeypatch.setattr(
        agent_service_module.hermes_client,
        "create_session",
        unavailable,
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/hermes/chat",
                json={"message": "读取当前能源情况"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["answer"] is None
    assert body["message"] is None
    assert body["status"] == "failed"
    assert body["error_code"] == "HERMES_UNAVAILABLE"
    assert body["error"]["code"] == "HERMES_UNAVAILABLE"
    assert body["session_id"]
    assert body["message_id"]
