# GuangHeng Phase 2C Autonomous Decision Loop

## Safety boundary

Autonomous Decision is not Autonomous Execution.

The Phase 2C loop may observe runtime data, assemble Decision Context, run
Optimizer V2, create a `PENDING` Proposal, and create a structured Notification
Event. It never approves a Proposal, invokes Execution, writes Home Assistant,
or bypasses Safety and Readback Verification.

Optimizer V2 remains the only source of energy targets and
`action_required`. Hermes and DeepSeek are not dependencies of the loop and are
never called by the scheduler. Hermes remains available only for user-initiated
explanations.

## Run flow

```text
Manual API / Scheduler tick
  -> DecisionContextService
  -> OptimizerEvaluationService
  -> OptimizationDecisionV2
  -> AutonomousDecisionRun audit record
  -> deterministic Proposal checks
  -> PENDING Proposal when required
  -> structured Notification Event
  -> wait for explicit user approval through the existing Proposal API
```

If no action is required, the run ends with `NO_ACTION_REQUIRED`. It creates no
Proposal and no `ACTION_REQUIRED` notification. If Decision Context, critical
optimizer evidence, or Optimizer evaluation is unavailable, the run fails and
does not create a Proposal.

## Scheduler

The scheduler uses the FastAPI lifespan and one `asyncio` background task. Its
production policy is stored in `config/autonomy_policy.yaml`:

```yaml
scheduler:
  enabled: false
  interval_seconds: 300
  initial_delay_seconds: 30
```

It is disabled by default, and startup never runs an immediate decision. When
enabled, the initial delay elapses before the first run. Shutdown stops future
ticks and allows an in-progress run to finish so an audit row is not left in
`RUNNING` state.

An in-process `asyncio.Lock` prevents overlapping runs. A concurrent trigger is
recorded as `SKIPPED / RUN_ALREADY_IN_PROGRESS`. This is an MVP guarantee for a
single FastAPI process only. Multiple workers require a distributed lease or
database lock before the scheduler can be enabled safely.

## Proposal deduplication

For the same device and capability:

- An existing `PENDING` Proposal with the same target is reused. The result is
  `EXISTING_PENDING_PROPOSAL_REUSED`.
- An existing `PENDING` Proposal with a different target blocks creation. The
  result is `PENDING_PROPOSAL_CONFLICT`, and one `SYSTEM_WARNING` asks the user
  to resolve the existing Proposal.
- A matching `REJECTED` Proposal inside the configured 60-minute cooldown
  suppresses recreation. The result is `REJECTED_PROPOSAL_COOLDOWN`, with no
  new notification.
- A changed target or expired cooldown permits a new evaluation to create one
  `PENDING` Proposal.

Autonomy never deletes, rejects, approves, supersedes, or expires an existing
Proposal. Proposal expiration and supersede semantics are future enhancements.

## Notification deduplication

Notifications contain a structured payload with strategy, capability, current
and target values, reason code, confidence, and Proposal ID. UI clients must
read these fields and must not parse values from notification text.

`ACTION_REQUIRED` uses `proposal:{proposal_id}` as its dedupe key. An existing
unread event is reused. Proposal conflict and system warning events also use
deterministic keys and reuse unread events. No notification is generated every
five minutes for a no-action decision.

Marking a notification as read only performs `UNREAD -> READ`. It does not
approve a Proposal or execute a device operation.

## APIs

```text
GET   /api/v1/autonomy/status
POST  /api/v1/autonomy/run
GET   /api/v1/autonomy/decisions
GET   /api/v1/autonomy/decisions/{run_id}
GET   /api/v1/notifications
PATCH /api/v1/notifications/{event_id}/read
```

The status contract exposes scheduler configuration, current running state,
latest decision, pending Proposal summary, unread notification count, and the
UI-facing state `MONITORING`, `ACTION_REQUIRED`, `DEGRADED`, or `DISABLED`.

## Stored data

`autonomous_decision_runs` stores bounded decision audit fields only.
`notification_events` stores notification metadata and its structured payload.
Neither table stores raw Home Assistant responses, raw weather history, Hermes
prompts, model reasoning, authorization headers, or secrets.

## Known runtime limitations

- The current source is an Anker SOLIX simulator.
- Some Home Assistant entity timestamps can be older than the current Control
  Plane observation.
- Simulator solar power can disagree with nighttime weather radiation.
- The loop does not repair, replace, or invent those values. It records or
  fails based on existing Domain Services and Optimizer V2.
- Savings, carbon, resilience, Proposal expiration, and supersede reporting are
  outside Phase 2C.
