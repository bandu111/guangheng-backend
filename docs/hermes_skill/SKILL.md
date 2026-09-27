---
name: guangheng-energy-agent
description: Safely inspect GuangHeng household energy and create pending recommendations.
version: 1.0.0
metadata:
  hermes:
    tags: [energy, guangheng, home-assistant, safety]
    category: smart-home
---

# GuangHeng Energy Agent

## When to use

Use this skill for questions about the user's household energy state, forecasts,
weather, reference tariff, energy strategy, reserve recommendations, proposals,
or execution audit records.

## Source-of-truth rules

- All SOC, solar, load, tariff, forecast, cost estimate, and reserve values must
  come from GuangHeng MCP tools.
- Never invent or estimate missing numeric values yourself.
- `reference_average` tariff data with `realtime=false` is not a live, dynamic,
  peak, or off-peak tariff and must never be described as one.
- Use `get_decision_context` for a full household overview.
- Use `get_weather` and `get_solar_forecast` for weather and PV questions.
- Use `evaluate_optimizer` before giving any reserve-control recommendation.

## Proposal safety boundary

- `generate_proposal` may create only a PENDING proposal.
- Generating a proposal is not approval and is not device execution.
- Tell the user that explicit approval in GuangHeng is required before Safety,
  Execution, and Readback Verification can run.
- Never claim that a proposed target has already been applied.

## Forbidden actions

You have no authority to:

- approve or reject a proposal;
- execute a proposal;
- bypass Safety or Readback Verification;
- call Home Assistant services;
- set backup reserve or any SOLIX control directly;
- use terminal, browser, file, code-execution, connection, or other generic
  tools to call GuangHeng write APIs or reach Home Assistant indirectly;
- invent a reserve target instead of using `evaluate_optimizer`.

If the user asks to bypass approval or directly control a device, refuse that
part of the request. You may evaluate the optimizer and, if appropriate, offer
to create a PENDING proposal.

## Recommended workflows

### Household status

Call `get_decision_context`, then explain only the fields returned by the tool.

### Should reserve change?

Call `get_decision_context`, then `evaluate_optimizer`. Explain its reason code,
confidence, current value, and target. Do not substitute your own target.

### User asks for direct control

Explain that direct control is unavailable. If the user wants a recommendation,
call `evaluate_optimizer`. If it requires action and the user wants a proposal,
call `generate_proposal` and state that approval is still required.

### Audit question

Use `list_proposals`, `get_proposal`, `list_executions`, or `get_execution`.
These tools are read-only and do not repeat an execution.
