import asyncio

from pydantic import BaseModel

from app.modules.hermes.mcp.server import ALLOWED_TOOL_FUNCTIONS, mcp_server
from app.modules.hermes.mcp.tools import context, energy, optimizer, proposal
from app.modules.proposal.models.proposal import ProposalStatus


EXPECTED_TOOLS = {
    "get_energy_state",
    "get_energy_balance",
    "get_weather",
    "get_solar_forecast",
    "get_load_forecast",
    "get_tariff",
    "get_strategy",
    "get_decision_context",
    "evaluate_optimizer",
    "generate_proposal",
    "get_proposal",
    "list_proposals",
    "get_execution",
    "list_executions",
}

FORBIDDEN_TOOLS = {
    "approve_proposal",
    "reject_proposal",
    "execute_proposal",
    "call_home_assistant_service",
    "set_backup_reserve",
    "set_charging_limit",
    "set_discharge_limit",
    "set_power_control",
}


class AvailableResult(BaseModel):
    available: bool = True
    marker: str
    error_code: str | None = None


class OptimizerResult(BaseModel):
    optimizer_version: str = "v2"


class PendingProposal(BaseModel):
    status: ProposalStatus = ProposalStatus.PENDING


class ProposalGenerationResult(BaseModel):
    created: bool
    proposal: PendingProposal | None = None


def test_tool_registry_contains_only_explicit_allow_list():
    registered = {tool.name for tool in asyncio.run(mcp_server.list_tools())}

    assert registered == EXPECTED_TOOLS
    assert set(ALLOWED_TOOL_FUNCTIONS) == EXPECTED_TOOLS
    assert registered.isdisjoint(FORBIDDEN_TOOLS)


def test_energy_tool_calls_existing_energy_service(monkeypatch):
    calls = 0

    async def fake_get_energy_state(*, db):
        nonlocal calls
        calls += 1
        return AvailableResult(marker="energy-service")

    monkeypatch.setattr(
        energy.energy_state_service,
        "get_energy_state",
        fake_get_energy_state,
    )

    result = asyncio.run(energy.get_energy_state())

    assert calls == 1
    assert result.success is True
    assert result.data["marker"] == "energy-service"


def test_forecast_tool_calls_existing_solar_forecast_service(monkeypatch):
    calls = 0

    async def fake_get_forecast(*, db):
        nonlocal calls
        calls += 1
        return AvailableResult(marker="solar-forecast-service")

    monkeypatch.setattr(
        context.solar_forecast_service,
        "get_forecast",
        fake_get_forecast,
    )

    result = asyncio.run(context.get_solar_forecast())

    assert calls == 1
    assert result.success is True
    assert result.data["marker"] == "solar-forecast-service"


def test_optimizer_tool_calls_optimizer_v2_service(monkeypatch):
    calls = 0

    async def fake_evaluate(*, db):
        nonlocal calls
        calls += 1
        return OptimizerResult()

    monkeypatch.setattr(
        optimizer.optimizer_evaluation_service,
        "evaluate",
        fake_evaluate,
    )

    result = asyncio.run(optimizer.evaluate_optimizer())

    assert calls == 1
    assert result.success is True
    assert result.data["optimizer_version"] == "v2"


def test_generate_proposal_returns_pending_only(monkeypatch):
    async def fake_generate(*, db):
        return ProposalGenerationResult(
            created=True,
            proposal=PendingProposal(),
        )

    monkeypatch.setattr(proposal.proposal_service, "generate", fake_generate)

    result = asyncio.run(proposal.generate_proposal())

    assert result.success is True
    assert result.data["created"] is True
    assert result.data["proposal"]["status"] == ProposalStatus.PENDING.value


def test_action_not_required_does_not_create_proposal(monkeypatch):
    async def fake_generate(*, db):
        return ProposalGenerationResult(created=False, proposal=None)

    monkeypatch.setattr(proposal.proposal_service, "generate", fake_generate)

    result = asyncio.run(proposal.generate_proposal())

    assert result.success is True
    assert result.data == {"created": False, "proposal": None}


def test_tool_exception_returns_sanitized_structured_error(monkeypatch):
    async def fake_get_energy_state(*, db):
        raise RuntimeError("internal sensitive-token-value and traceback")

    monkeypatch.setattr(
        energy.energy_state_service,
        "get_energy_state",
        fake_get_energy_state,
    )

    result = asyncio.run(energy.get_energy_state())

    assert result.success is False
    assert result.tool == "get_energy_state"
    assert result.error_code == "ENERGY_STATE_UNAVAILABLE"
    assert result.data is None
    assert "sensitive-token-value" not in (result.message or "")

