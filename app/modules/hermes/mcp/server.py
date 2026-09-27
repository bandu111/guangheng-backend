import argparse
from collections.abc import Callable
from typing import Any

from mcp import types
from mcp.server import MCPServer

from app.modules.hermes.mcp.tools.audit import get_execution, list_executions
from app.modules.hermes.mcp.tools.context import (
    get_decision_context,
    get_load_forecast,
    get_solar_forecast,
    get_strategy,
    get_tariff,
    get_weather,
)
from app.modules.hermes.mcp.tools.energy import (
    get_energy_balance,
    get_energy_state,
)
from app.modules.hermes.mcp.tools.optimizer import evaluate_optimizer
from app.modules.hermes.mcp.tools.proposal import (
    generate_proposal,
    get_proposal,
    list_proposals,
)


GUANGHENG_AGENT_INSTRUCTIONS = """
You are the GuangHeng Energy Agent. Use GuangHeng tools for every numeric claim
about SOC, solar, load, tariff, forecasts, and reserve targets. Never invent
energy values. For control advice, call evaluate_optimizer first. You may call
generate_proposal when a pending recommendation is appropriate, but creating a
proposal does not execute it. When get_decision_context returns a Household
Energy Graph opportunity with multiple coordinated actions, pass that exact
opportunity code to generate_proposal so it creates one PENDING Action Set.
Explicitly tell the user that a proposal or Action Set requires
user approval before Safety, Execution, and Readback Verification. You cannot
approve or reject proposals, bypass Safety, call Home Assistant services, or
directly control Anker SOLIX devices. Refuse requests to bypass user approval.
Never use general-purpose tools to reach GuangHeng write APIs or Home Assistant
indirectly.
""".strip()


ALLOWED_TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "get_energy_state": get_energy_state,
    "get_energy_balance": get_energy_balance,
    "get_weather": get_weather,
    "get_solar_forecast": get_solar_forecast,
    "get_load_forecast": get_load_forecast,
    "get_tariff": get_tariff,
    "get_strategy": get_strategy,
    "get_decision_context": get_decision_context,
    "evaluate_optimizer": evaluate_optimizer,
    "generate_proposal": generate_proposal,
    "get_proposal": get_proposal,
    "list_proposals": list_proposals,
    "get_execution": get_execution,
    "list_executions": list_executions,
}

READ_ONLY_TOOLS = frozenset(ALLOWED_TOOL_FUNCTIONS) - {"generate_proposal"}


def create_mcp_server() -> MCPServer:
    server = MCPServer(
        name="guangheng-energy-tools",
        title="GuangHeng Energy Tools",
        description="Minimal-permission energy context and proposal tools.",
        instructions=GUANGHENG_AGENT_INSTRUCTIONS,
        version="1.0.0",
    )
    for name, function in ALLOWED_TOOL_FUNCTIONS.items():
        read_only = name in READ_ONLY_TOOLS
        server.add_tool(
            function,
            name=name,
            annotations=types.ToolAnnotations(
                readOnlyHint=read_only,
                destructiveHint=False,
                idempotentHint=read_only,
                openWorldHint=False,
            ),
            structured_output=True,
        )
    return server


mcp_server = create_mcp_server()


def main() -> None:
    parser = argparse.ArgumentParser(description="GuangHeng MCP Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    mcp_server.run(
        transport="streamable-http",
        host=args.host,
        port=args.port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
