import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.modules.hermes.models.agent_conversation import (
    AgentMessage,
    AgentSession,
    AgentToolCall,
)
from app.modules.hermes.repositories.agent_repository import agent_repository
from app.modules.hermes.schemas.hermes import (
    AgentDecisionSchema,
    AgentErrorSchema,
    AgentIntent,
    AgentMessageListSchema,
    AgentMessageSchema,
    AgentProposalSchema,
    AgentResponseStatus,
    AgentSessionCreateSchema,
    AgentSessionDetailSchema,
    AgentToolTraceSchema,
    HermesChatResponseSchema,
)
from app.modules.hermes.services.hermes_client import (
    HermesToolEvent,
    HermesUnavailableError,
    hermes_client,
)


DISPLAY_NAMES = {
    "get_energy_state": "读取能源状态",
    "get_energy_balance": "读取能源平衡",
    "get_weather": "检查天气",
    "get_solar_forecast": "读取光伏预测",
    "get_load_forecast": "读取负载预测",
    "get_tariff": "读取参考电价",
    "get_strategy": "读取当前策略",
    "get_decision_context": "读取决策上下文",
    "evaluate_optimizer": "运行能源优化器",
    "generate_proposal": "创建待审批方案",
    "get_proposal": "读取方案",
    "list_proposals": "读取方案记录",
    "get_execution": "读取执行记录",
    "list_executions": "读取执行记录",
}

SECRET_MARKERS = (
    "authorization",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
)


class AgentSessionNotFoundError(LookupError):
    pass


class AgentService:
    def create_session(self, db: Session) -> AgentSessionCreateSchema:
        row = agent_repository.create_session(
            db,
            AgentSession(id=str(uuid4()), status="active"),
        )
        return AgentSessionCreateSchema(
            session_id=row.id,
            created_at=row.created_at,
        )

    def get_session(self, db: Session, session_id: str) -> AgentSessionDetailSchema:
        row = self._require_session(db, session_id)
        return AgentSessionDetailSchema(
            session_id=row.id,
            status=row.status,
            message_count=agent_repository.count_messages(db, row.id),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def get_messages(self, db: Session, session_id: str) -> AgentMessageListSchema:
        self._require_session(db, session_id)
        messages = [self._message_schema(db, item) for item in agent_repository.list_messages(db, session_id)]
        return AgentMessageListSchema(
            session_id=session_id,
            count=len(messages),
            messages=messages,
        )

    async def chat(
        self,
        db: Session,
        message: str,
        session_id: str | None = None,
    ) -> HermesChatResponseSchema:
        if session_id is None:
            session_id = self.create_session(db).session_id
        session = self._require_session(db, session_id)
        user_message = agent_repository.create_message(
            db,
            AgentMessage(
                id=str(uuid4()),
                session_id=session.id,
                role="user",
                content=message,
                status=AgentResponseStatus.COMPLETED.value,
            ),
        )

        try:
            if not session.hermes_session_id:
                # Official Hermes requires globally unique session titles.
                # Use the local audit id instead of the user text so repeated
                # questions can always start independent conversations.
                session.hermes_session_id = await hermes_client.create_session(
                    f"GuangHeng {session.id}"
                )
                agent_repository.save_session(db, session)
            turn = await hermes_client.run_session_turn(
                session.hermes_session_id,
                message,
            )
        except HermesUnavailableError as exc:
            return self._persist_failed_response(
                db,
                session.id,
                exc.error_code,
                self._public_error_message(exc.error_code),
                created_after=user_message.created_at,
            )

        parsed_events = [self._parse_event(item) for item in turn.tool_events if self._tool_name(item.tool_name) in DISPLAY_NAMES]
        successful = [item for item in parsed_events if item[1] is not None and bool(item[1].get("success"))]
        failed = [item for item in parsed_events if item not in successful]

        decision = self._map_decision(successful)
        proposal, invalid_proposal = self._map_proposal(successful)
        if invalid_proposal:
            invalid_event, invalid_result = invalid_proposal
            parsed_events = [
                (event, invalid_result if event is invalid_event else result)
                for event, result in parsed_events
            ]
            successful = [
                item for item in successful if item[0] is not invalid_event
            ]
            failed.append(invalid_proposal)
            proposal = None
        sources = self._map_sources(successful)
        intent = self._map_intent(parsed_events)
        status = self._response_status(turn.status, parsed_events, successful, failed)
        error = self._map_error(turn.error_code, turn.error_message, failed, status)
        answer = turn.answer if turn.answer and turn.answer.strip() else None

        assistant = AgentMessage(
            id=str(uuid4()),
            session_id=session.id,
            role="assistant",
            content=answer or "",
            intent=intent.value,
            status=status.value,
            decision=self._json_model(decision),
            proposal=self._json_model(proposal),
            sources=sources,
            error=self._json_model(error),
            created_at=max(
                datetime.utcnow(), user_message.created_at + timedelta(microseconds=1)
            ),
        )
        agent_repository.create_message(db, assistant)
        tool_rows = self._persist_tool_calls(db, session.id, assistant.id, parsed_events)
        session.updated_at = datetime.utcnow()
        agent_repository.save_session(db, session)
        tools = [self._tool_trace(row) for row in tool_rows]
        return self._response(
            session_id=session.id,
            message_id=assistant.id,
            answer=answer,
            intent=intent,
            status=status,
            tools=tools,
            decision=decision,
            proposal=proposal,
            sources=sources,
            error=error,
        )

    def _persist_failed_response(
        self,
        db: Session,
        session_id: str,
        error_code: str,
        message: str,
        created_after: datetime | None = None,
    ) -> HermesChatResponseSchema:
        error = AgentErrorSchema(
            code=error_code,
            message=message,
            retryable=True,
        )
        assistant = agent_repository.create_message(
            db,
            AgentMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="assistant",
                content="",
                intent=AgentIntent.GENERAL.value,
                status=AgentResponseStatus.FAILED.value,
                sources={},
                error=error.model_dump(mode="json"),
                created_at=(
                    max(
                        datetime.utcnow(),
                        created_after + timedelta(microseconds=1),
                    )
                    if created_after is not None
                    else datetime.utcnow()
                ),
            ),
        )
        return self._response(
            session_id=session_id,
            message_id=assistant.id,
            answer=None,
            intent=AgentIntent.GENERAL,
            status=AgentResponseStatus.FAILED,
            tools=[],
            decision=None,
            proposal=None,
            sources={},
            error=error,
        )

    def _persist_tool_calls(
        self,
        db: Session,
        session_id: str,
        message_id: str,
        events: list[tuple[HermesToolEvent, dict[str, Any] | None]],
    ) -> list[AgentToolCall]:
        rows: list[AgentToolCall] = []
        for sequence, (event, result) in enumerate(events, start=1):
            name = self._tool_name(event.tool_name)
            completed_at = event.completed_at or datetime.now(timezone.utc)
            success = bool(result and result.get("success")) and not event.failed
            error_code = None
            if result and not success:
                error_code = result.get("error_code") or "TOOL_FAILED"
            elif not success:
                error_code = self._event_failure_code(event)
            rows.append(
                AgentToolCall(
                    id=str(uuid4()),
                    session_id=session_id,
                    message_id=message_id,
                    sequence=sequence,
                    tool_name=name,
                    success=success,
                    started_at=self._db_time(event.started_at),
                    completed_at=self._db_time(completed_at),
                    duration_ms=max(0, event.duration_ms),
                    error_code=error_code,
                    input_summary=self._sanitize(event.arguments),
                    output_summary=self._output_summary(name, result),
                )
            )
        return agent_repository.create_tool_calls(db, rows)

    @staticmethod
    def _parse_event(event: HermesToolEvent) -> tuple[HermesToolEvent, dict[str, Any] | None]:
        content = event.result_content
        if not isinstance(content, str) or not content.strip():
            return event, None
        decoder = json.JSONDecoder()
        candidates: list[Any] = []
        try:
            candidates.append(json.loads(content))
        except json.JSONDecodeError:
            for index, char in enumerate(content):
                if char != "{":
                    continue
                try:
                    value, _ = decoder.raw_decode(content[index:])
                    candidates.append(value)
                except json.JSONDecodeError:
                    continue
        for candidate in candidates:
            result = AgentService._unwrap_result(candidate)
            if isinstance(result, dict) and "success" in result and "tool" in result:
                return event, result
        return event, None

    @staticmethod
    def _unwrap_result(value: Any) -> Any:
        for _ in range(4):
            if isinstance(value, dict) and "success" in value and "tool" in value:
                return value
            if isinstance(value, dict) and "result" in value:
                value = value["result"]
                continue
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                    continue
                except json.JSONDecodeError:
                    return None
            if isinstance(value, dict) and isinstance(value.get("content"), list):
                texts = [item.get("text") for item in value["content"] if isinstance(item, dict) and isinstance(item.get("text"), str)]
                value = texts[0] if texts else None
                continue
            return None
        return value

    @staticmethod
    def _map_decision(
        events: list[tuple[HermesToolEvent, dict[str, Any]]],
    ) -> AgentDecisionSchema | None:
        for event, result in reversed(events):
            if AgentService._tool_name(event.tool_name) != "evaluate_optimizer":
                continue
            data = result.get("data")
            if not isinstance(data, dict):
                return None
            required = ("version", "strategy_mode", "capability", "action_required", "reason_code", "decision_confidence")
            if any(key not in data for key in required):
                return None
            return AgentDecisionSchema(
                optimizer_version=str(data["version"]),
                strategy=str(data["strategy_mode"]),
                capability=str(data["capability"]),
                current_value=data.get("current_value"),
                target_value=data.get("target_value"),
                action_required=bool(data["action_required"]),
                reason_code=str(data["reason_code"]),
                confidence=str(data["decision_confidence"]),
            )
        return None

    @staticmethod
    def _map_proposal(
        events: list[tuple[HermesToolEvent, dict[str, Any]]],
    ) -> tuple[AgentProposalSchema | None, tuple[HermesToolEvent, dict[str, Any]] | None]:
        for event, result in reversed(events):
            if AgentService._tool_name(event.tool_name) != "generate_proposal":
                continue
            data = result.get("data")
            proposal = data.get("proposal") if isinstance(data, dict) else None
            if proposal is None:
                return None, None
            if not isinstance(proposal, dict) or str(proposal.get("status")) != "PENDING":
                invalid = dict(result)
                invalid.update({"success": False, "error_code": "PROPOSAL_STATE_INVALID"})
                return None, (event, invalid)
            try:
                return AgentProposalSchema(
                    id=int(proposal["id"]),
                    status="PENDING",
                    capability=str(proposal["capability"]),
                    current_value=float(proposal["current_value"]),
                    target_value=float(proposal["target_value"]),
                    created_at=proposal["created_at"],
                ), None
            except (KeyError, TypeError, ValueError):
                return None, None
        return None, None

    @staticmethod
    def _map_sources(
        events: list[tuple[HermesToolEvent, dict[str, Any]]],
    ) -> dict[str, Any]:
        sources: dict[str, Any] = {}
        for event, result in events:
            name = AgentService._tool_name(event.tool_name)
            data = result.get("data")
            observed_at = result.get("observed_at")
            if not isinstance(data, dict):
                continue
            if name == "get_decision_context":
                AgentService._sources_from_context(sources, data)
            elif name in {"get_energy_state", "get_energy_balance"}:
                source = data.get("source") if isinstance(data.get("source"), dict) else {}
                sources["energy"] = {
                    "provider": "home_assistant",
                    "source_mode": source.get("source_mode"),
                    "observed_at": data.get("last_updated") or observed_at,
                }
            elif name == "get_weather":
                sources["weather"] = {"provider": data.get("provider"), "observed_at": data.get("observed_at") or observed_at}
            elif name == "get_solar_forecast":
                sources["solar_forecast"] = {"algorithm": data.get("method"), "confidence": AgentService._forecast_confidence(data), "observed_at": data.get("observed_at") or observed_at}
            elif name == "get_load_forecast":
                sources["load_forecast"] = {"algorithm": data.get("method"), "confidence": AgentService._forecast_confidence(data), "observed_at": data.get("observed_at") or observed_at}
            elif name == "get_tariff":
                source = data.get("source") if isinstance(data.get("source"), dict) else {}
                sources["tariff"] = {
                    "provider": source.get("provider"),
                    "pricing_type": source.get("pricing_type"),
                    "realtime": source.get("realtime"),
                    "observed_at": data.get("observed_at") or observed_at,
                }
        return sources

    @staticmethod
    def _sources_from_context(sources: dict[str, Any], context: dict[str, Any]) -> None:
        energy = context.get("energy")
        if isinstance(energy, dict):
            source = energy.get("source") if isinstance(energy.get("source"), dict) else {}
            sources["energy"] = {"provider": "home_assistant", "source_mode": source.get("source_mode"), "observed_at": energy.get("last_updated") or context.get("observed_at")}
        weather = context.get("weather")
        if isinstance(weather, dict):
            sources["weather"] = {"provider": weather.get("provider"), "observed_at": weather.get("observed_at")}
        for key in ("solar_forecast", "load_forecast"):
            forecast = context.get(key)
            if isinstance(forecast, dict):
                sources[key] = {"algorithm": forecast.get("method"), "confidence": AgentService._forecast_confidence(forecast), "observed_at": forecast.get("observed_at")}
        tariff = context.get("tariff")
        if isinstance(tariff, dict):
            source = tariff.get("source") if isinstance(tariff.get("source"), dict) else {}
            sources["tariff"] = {"provider": source.get("provider"), "pricing_type": source.get("pricing_type"), "realtime": source.get("realtime"), "observed_at": tariff.get("observed_at")}

    @staticmethod
    def _forecast_confidence(data: dict[str, Any]) -> str | None:
        values = [str(item.get("confidence")) for item in data.get("forecast", []) if isinstance(item, dict) and item.get("confidence")]
        if not values:
            return None
        rank = {"UNAVAILABLE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
        return min(values, key=lambda item: rank.get(item, -1))

    @staticmethod
    def _map_intent(events: list[tuple[HermesToolEvent, dict[str, Any] | None]]) -> AgentIntent:
        names = {AgentService._tool_name(event.tool_name) for event, _ in events}
        if "generate_proposal" in names:
            return AgentIntent.PROPOSAL_REQUEST
        if "evaluate_optimizer" in names:
            return AgentIntent.ENERGY_DECISION
        if names & {"get_proposal", "list_proposals", "get_execution", "list_executions"}:
            return AgentIntent.AUDIT_QUERY
        if "get_weather" in names:
            return AgentIntent.WEATHER_FORECAST
        if "get_solar_forecast" in names:
            return AgentIntent.SOLAR_FORECAST
        if names & {"get_energy_state", "get_energy_balance", "get_decision_context"}:
            return AgentIntent.ENERGY_STATUS
        return AgentIntent.GENERAL

    @staticmethod
    def _response_status(turn_status: str, events, successful, failed) -> AgentResponseStatus:
        if failed and successful:
            return AgentResponseStatus.PARTIAL
        if failed and not successful:
            return AgentResponseStatus.FAILED
        if turn_status == "partial":
            return AgentResponseStatus.PARTIAL
        if turn_status == "failed":
            return AgentResponseStatus.FAILED
        return AgentResponseStatus.COMPLETED

    @staticmethod
    def _map_error(turn_code: str | None, turn_message: str | None, failed, status: AgentResponseStatus) -> AgentErrorSchema | None:
        if status == AgentResponseStatus.COMPLETED:
            return None
        if failed:
            event, result = failed[0]
            underlying = result.get("error_code") if isinstance(result, dict) else AgentService._event_failure_code(event)
            code = "MCP_UNAVAILABLE" if underlying == "MCP_UNAVAILABLE" else "TOOL_FAILED"
            return AgentErrorSchema(code=code, message="One or more agent tools could not provide verified data.", retryable=True)
        code = turn_code or "UPSTREAM_PROVIDER_ERROR"
        return AgentErrorSchema(code=code, message=turn_message or AgentService._public_error_message(code), retryable=True)

    @staticmethod
    def _event_failure_code(event: HermesToolEvent) -> str:
        text = (event.result_content or "").lower()
        if any(marker in text for marker in ("mcp", "channel closed", "disconnected", "connection")):
            return "MCP_UNAVAILABLE"
        return "TOOL_FAILED"

    @staticmethod
    def _public_error_message(code: str) -> str:
        return {
            "AGENT_TIMEOUT": "The energy agent timed out before completing the request.",
            "UPSTREAM_PROVIDER_ERROR": "The model provider is temporarily unavailable.",
            "MCP_UNAVAILABLE": "The GuangHeng tool service is unavailable.",
            "TOOL_FAILED": "A required energy tool could not provide verified data.",
        }.get(code, "The Hermes agent service is unavailable.")

    @staticmethod
    def _sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): "[REDACTED]" if any(marker in str(key).lower() for marker in SECRET_MARKERS) else AgentService._sanitize(item)
                for key, item in list(value.items())[:20]
            }
        if isinstance(value, list):
            return [AgentService._sanitize(item) for item in value[:20]]
        if isinstance(value, str):
            return value[:200]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return str(value)[:200]

    @staticmethod
    def _output_summary(name: str, result: dict[str, Any] | None) -> dict[str, Any]:
        if not result:
            return {"success": False}
        summary: dict[str, Any] = {
            "success": bool(result.get("success")),
            "error_code": result.get("error_code"),
            "observed_at": result.get("observed_at"),
        }
        data = result.get("data")
        if not isinstance(data, dict):
            return summary
        if name == "evaluate_optimizer":
            for key in ("version", "strategy_mode", "capability", "current_value", "target_value", "action_required", "reason_code", "decision_confidence"):
                summary[key] = data.get(key)
        elif name == "generate_proposal":
            action_set = data.get("action_set")
            if isinstance(action_set, dict):
                summary["action_set"] = {
                    key: action_set.get(key)
                    for key in (
                        "id",
                        "status",
                        "title",
                        "expected_grid_delta_w",
                        "created_at",
                    )
                }
                summary["action_count"] = len(action_set.get("items") or [])
                return AgentService._sanitize(summary)
            proposal = data.get("proposal")
            if isinstance(proposal, dict):
                summary["proposal"] = {key: proposal.get(key) for key in ("id", "status", "capability", "current_value", "target_value", "created_at")}
            else:
                summary["created"] = bool(data.get("created"))
        else:
            summary["available"] = data.get("available")
            summary["data_fields"] = sorted(str(key) for key in data.keys())[:20]
        return AgentService._sanitize(summary)

    @staticmethod
    def _tool_name(value: str) -> str:
        return value.removeprefix("mcp__guangheng__")

    @staticmethod
    def _db_time(value: datetime) -> datetime:
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value

    @staticmethod
    def _json_model(value):
        return value.model_dump(mode="json") if value is not None else None

    @staticmethod
    def _tool_trace(row: AgentToolCall) -> AgentToolTraceSchema:
        return AgentToolTraceSchema(
            tool_name=row.tool_name,
            display_name=DISPLAY_NAMES.get(row.tool_name, row.tool_name),
            success=row.success,
            started_at=row.started_at,
            completed_at=row.completed_at,
            duration_ms=row.duration_ms,
            error_code=row.error_code,
        )

    def _message_schema(self, db: Session, row: AgentMessage) -> AgentMessageSchema:
        return AgentMessageSchema(
            message_id=row.id,
            role=row.role,
            content=row.content,
            intent=row.intent,
            status=row.status,
            tools=[self._tool_trace(item) for item in agent_repository.list_tool_calls(db, row.id)],
            decision=row.decision,
            proposal=row.proposal,
            sources=row.sources or {},
            error=row.error,
            created_at=row.created_at,
        )

    @staticmethod
    def _response(**kwargs) -> HermesChatResponseSchema:
        error = kwargs["error"]
        answer = kwargs["answer"]
        return HermesChatResponseSchema(
            **kwargs,
            available=kwargs["status"] != AgentResponseStatus.FAILED,
            message=answer,
            error_code=error.code if error else None,
        )

    @staticmethod
    def _require_session(db: Session, session_id: str) -> AgentSession:
        row = agent_repository.get_session(db, session_id)
        if row is None:
            raise AgentSessionNotFoundError(session_id)
        return row


agent_service = AgentService()
