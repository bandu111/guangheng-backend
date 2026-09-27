import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings


GUANGHENG_HERMES_SYSTEM_INSTRUCTION = """
You are GuangHeng Energy Agent. All SOC, solar, load, tariff, forecast, and
reserve values must come from GuangHeng MCP tools. Never invent numeric energy
data. Use evaluate_optimizer before giving reserve-control advice. You may use
generate_proposal only to create a PENDING proposal. A proposal is not an
execution: tell the user it still requires explicit user approval, Safety,
Execution, and Readback Verification. You have no authority to approve or
reject proposals, bypass Safety, call Home Assistant services, or directly
control Anker SOLIX. Refuse any request to bypass approval.
Never use general-purpose tools to reach GuangHeng write APIs or Home Assistant
indirectly.
""".strip()


class HermesUnavailableError(RuntimeError):
    def __init__(self, message: str, error_code: str = "HERMES_UNAVAILABLE"):
        super().__init__(message)
        self.error_code = error_code


@dataclass
class HermesToolEvent:
    message_id: str
    tool_name: str
    arguments: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int = 0
    failed: bool = False
    result_content: str | None = None


@dataclass
class HermesTurnResult:
    answer: str | None
    status: str
    tool_events: list[HermesToolEvent] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class HermesClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.hermes_base_url).rstrip("/")
        self.api_key = (
            settings.hermes_api_key if api_key is None else api_key
        )
        self.model = model or settings.hermes_model
        self.timeout = timeout or settings.hermes_timeout_seconds
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
            # The Hermes Gateway is a loopback service. On Windows, httpx can
            # inherit an OS proxy that intercepts localhost with a synthetic
            # 502, so this hop must never use the ambient proxy configuration.
            trust_env=False,
        )

    async def chat(self, message: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": GUANGHENG_HERMES_SYSTEM_INSTRUCTION,
                },
                {"role": "user", "content": message},
            ],
            "stream": False,
        }
        try:
            async with self._client() as client:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Hermes returned no assistant message.")
            return content
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise self._unavailable_error(exc) from exc

    async def create_session(self, title: str) -> str:
        try:
            async with self._client() as client:
                response = await client.post(
                    f"{self.base_url}/api/sessions",
                    headers=self._headers(),
                    json={"title": title[:120], "source": "api_server"},
                )
                response.raise_for_status()
                body = response.json()
            session_id = body["session"]["id"]
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("Hermes session id is missing.")
            return session_id
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise self._unavailable_error(exc) from exc

    async def run_session_turn(
        self,
        hermes_session_id: str,
        message: str,
    ) -> HermesTurnResult:
        events: dict[str, HermesToolEvent] = {}
        order: list[str] = []
        answer: str | None = None
        status = "failed"
        error_code: str | None = None
        error_message: str | None = None
        try:
            async with self._client() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/sessions/{hermes_session_id}/chat/stream",
                    headers=self._headers(),
                    json={
                        "input": message,
                        "instructions": GUANGHENG_HERMES_SYSTEM_INSTRUCTION,
                    },
                ) as response:
                    response.raise_for_status()
                    event_name = "message"
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            event_name = line.split(":", 1)[1].strip()
                            continue
                        if not line.startswith("data:"):
                            continue
                        try:
                            data = json.loads(line.split(":", 1)[1].strip())
                        except (json.JSONDecodeError, TypeError):
                            continue
                        if event_name == "tool.started":
                            self._record_tool_started(events, order, data)
                        elif event_name == "tool.completed":
                            self._record_tool_completed(events, order, data)
                        elif event_name == "assistant.completed":
                            answer = data.get("content")
                            if data.get("partial"):
                                status = "partial"
                            elif data.get("completed"):
                                status = "completed"
                        elif event_name in {"run.failed", "run.interrupted"}:
                            status = "failed"
                            error_code = "UPSTREAM_PROVIDER_ERROR"
                            error_message = "Hermes could not complete the agent turn."

                history_response = await client.get(
                    f"{self.base_url}/api/sessions/{hermes_session_id}/messages",
                    headers=self._headers(),
                )
                history_response.raise_for_status()
                history = history_response.json().get("data", [])
            # Hermes 0.21.3 emits the parent assistant message id for every
            # tool in one parallel tool-call batch. The persisted tool rows
            # receive different database ids, so correlate by tool name and
            # chronological occurrence rather than by message id.
            tool_messages: dict[str, list[dict[str, Any]]] = {}
            for history_item in history:
                if history_item.get("role") != "tool":
                    continue
                name = history_item.get("tool_name")
                if isinstance(name, str):
                    tool_messages.setdefault(name, []).append(history_item)
            for item in (events[key] for key in order):
                candidates = tool_messages.get(item.tool_name, [])
                if candidates:
                    message_row = candidates.pop(0)
                    item.result_content = message_row.get("content")
            if status == "failed" and answer:
                status = "partial"
            return HermesTurnResult(
                answer=answer,
                status=status,
                tool_events=[events[key] for key in order],
                error_code=error_code,
                error_message=error_message,
            )
        except httpx.TimeoutException as exc:
            raise HermesUnavailableError(
                "Official Hermes Agent timed out.", "AGENT_TIMEOUT"
            ) from exc
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise self._unavailable_error(exc) from exc

    @staticmethod
    def _record_tool_started(
        events: dict[str, HermesToolEvent], order: list[str], data: dict
    ) -> None:
        message_id = str(data.get("message_id") or "")
        if not message_id:
            return
        timestamp = HermesClient._parse_time(data.get("ts"))
        tool_name = str(data.get("tool_name") or "unknown")
        event_key = f"{message_id}:{tool_name}:{len(order)}"
        events[event_key] = HermesToolEvent(
            message_id=message_id,
            tool_name=tool_name,
            arguments=data.get("args") if isinstance(data.get("args"), dict) else {},
            started_at=timestamp,
        )
        order.append(event_key)

    @staticmethod
    def _record_tool_completed(
        events: dict[str, HermesToolEvent], order: list[str], data: dict
    ) -> None:
        message_id = str(data.get("message_id") or "")
        if not message_id:
            return
        completed_at = HermesClient._parse_time(data.get("ts"))
        tool_name = str(data.get("tool_name") or "unknown")
        event_key = next(
            (
                key
                for key in reversed(order)
                if events[key].message_id == message_id
                and events[key].tool_name == tool_name
                and events[key].completed_at is None
            ),
            None,
        )
        item = events.get(event_key) if event_key is not None else None
        if item is None:
            event_key = f"{message_id}:{tool_name}:{len(order)}"
            item = HermesToolEvent(
                message_id=message_id,
                tool_name=tool_name,
                arguments=data.get("args")
                if isinstance(data.get("args"), dict)
                else {},
                started_at=completed_at,
            )
            events[event_key] = item
            order.append(event_key)
        item.completed_at = completed_at
        item.duration_ms = max(
            0, int((completed_at - item.started_at).total_seconds() * 1000)
        )
        item.failed = bool(data.get("error"))

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    @staticmethod
    def _unavailable_error(exc: Exception) -> HermesUnavailableError:
        if isinstance(exc, httpx.TimeoutException):
            return HermesUnavailableError(
                "Official Hermes Agent timed out.", "AGENT_TIMEOUT"
            )
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in {502, 503, 504}:
                return HermesUnavailableError(
                    "Hermes upstream provider is unavailable.",
                    "UPSTREAM_PROVIDER_ERROR",
                )
        return HermesUnavailableError(
            "Official Hermes Agent API is unavailable or returned an invalid response.",
            "HERMES_UNAVAILABLE",
        )


hermes_client = HermesClient()
