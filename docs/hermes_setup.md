# GuangHeng Hermes Phase 1 Setup

GuangHeng integrates with the official
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) as an
independent runtime. No Hermes source code is copied into GuangHeng.

## Security boundary

The DeepSeek provider secret belongs only to Hermes. Hermes stores provider
secrets in `~/.hermes/.env`; do not put that key in GuangHeng, Flutter, Git,
YAML, logs, prompts, or chat messages.

GuangHeng's `HERMES_API_KEY` is a separate local Gateway access key. It is not a
DeepSeek key.

## 1. Install WSL2

In an Administrator PowerShell:

```powershell
wsl --install
wsl --set-default-version 2
wsl --list --verbose
```

Restart Windows if prompted. Ubuntu LTS is the recommended distribution.

For localhost access between WSL2 and Windows on supported Windows 11 builds,
enable mirrored networking in `%UserProfile%\.wslconfig` and then run
`wsl --shutdown`:

```ini
[wsl2]
networkingMode=mirrored
```

## 2. Install official Hermes Agent in WSL2

Open Ubuntu/WSL2:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc
hermes setup
```

This uses the official installer documented by Nous Research.

## 3. Configure DeepSeek inside Hermes

Run:

```bash
hermes model
```

Choose the built-in DeepSeek provider and enter the new key only into the
interactive Hermes prompt. Hermes stores it in `~/.hermes/.env`. Do not paste it
into Codex or any GuangHeng file.

The current official provider profile uses the DeepSeek API base
`https://api.deepseek.com/v1` and supports `deepseek-v4-flash` and
`deepseek-v4-pro`. Prefer the flash model for initial integration and select the
stronger model only when needed. Model selection remains Hermes configuration,
not GuangHeng business code.

The resulting secret file contains the provider variable below with its value
entered locally:

```dotenv
DEEPSEEK_API_KEY=
```

The line above is intentionally only a placeholder in this document.

## 4. Start the GuangHeng MCP server

In Windows PowerShell from the backend project:

```powershell
.\.venv\Scripts\python.exe -m app.modules.hermes.mcp.server --host 127.0.0.1 --port 8001
```

The MCP endpoint is Streamable HTTP:

```text
http://127.0.0.1:8001/mcp
```

It intentionally does not use the legacy SSE transport.

## 5. Connect Hermes to the MCP server

Merge the `mcp_servers` block from `config/hermes_mcp.example.yaml` into
`~/.hermes/config.yaml`. The configuration uses an explicit allow-list,
disables resources/prompts, disables parallel tool calls, and marks the server
`untrusted` so Hermes treats the proposal-generating tool as write-capable.

For the dedicated GuangHeng profile, also merge the example's
`agent.disabled_toolsets` block. It disables Hermes' built-in Home Assistant,
terminal, code execution, file, browser, computer-control, connection,
delegation, and scheduled-job paths. Do not set `HASS_TOKEN` in this Hermes
profile. This ensures the allow-listed GuangHeng MCP server is the only energy
integration path, rather than relying on prompt instructions as the security
boundary. Keep this profile dedicated to GuangHeng.

Verify from WSL2 that the Windows-hosted MCP port is reachable. With mirrored
networking, use `127.0.0.1`. If your organization does not allow mirrored
networking, run both GuangHeng and Hermes inside the same WSL2 environment
rather than exposing an unauthenticated MCP port to the LAN.

After changing MCP configuration, restart Hermes or run `/reload-mcp` in an
active Hermes session.

## 6. Install the GuangHeng skill

Copy the supplied skill into the Hermes skills directory:

```bash
mkdir -p ~/.hermes/skills/smart-home/guangheng-energy-agent
cp /mnt/e/PythonProject/guangheng_server/docs/hermes_skill/SKILL.md \
  ~/.hermes/skills/smart-home/guangheng-energy-agent/SKILL.md
```

Start a new Hermes session after installing the skill.

## 7. Enable and start the Hermes API server

Enable the API server in Hermes' local `~/.hermes/.env` and set a new local
Gateway key. Enter the value only on your machine; do not commit it:

```dotenv
API_SERVER_ENABLED=true
API_SERVER_KEY=
```

The key line above is intentionally a placeholder. After saving the real local
Gateway key in that file, start Hermes in the WSL foreground as recommended by
the official CLI documentation:

```bash
hermes gateway run
```

The Gateway should listen on:

```text
http://127.0.0.1:8642
```

Verify:

```bash
curl http://127.0.0.1:8642/health
curl -H "Authorization: Bearer $HERMES_API_KEY" \
  http://127.0.0.1:8642/v1/models
```

## 8. Configure GuangHeng locally

Manually add these values to the local GuangHeng `.env`. The local Gateway key
must match `API_SERVER_KEY` in Hermes:

```dotenv
HERMES_BASE_URL=http://127.0.0.1:8642
HERMES_API_KEY=
HERMES_MODEL=hermes-agent
HERMES_TIMEOUT_SECONDS=120
```

Do not place the DeepSeek provider key here.

## 9. Start GuangHeng and test

Start FastAPI, then call:

```text
POST http://127.0.0.1:8000/api/v1/hermes/chat
```

Example body:

```json
{"message": "我现在家的能源情况怎么样？"}
```

Confirm all reported SOC, solar, and load values match
`GET /api/v1/energy/state`.

For reserve advice, confirm Hermes calls `evaluate_optimizer`. For a request to
bypass approval, confirm Hermes refuses direct control. No Phase 1 MCP tool can
approve, execute, or call Home Assistant write services.

## Phase 2B: Windows Native sessions and structured responses

The validated Phase 2 runtime runs Official Hermes 0.21.3 natively on Windows.
GuangHeng uses the loopback-only endpoints below; none of them should be
published to the LAN or Internet:

```text
GuangHeng API: http://127.0.0.1:8000
GuangHeng MCP: http://127.0.0.1:8001/mcp
Hermes Gateway: http://127.0.0.1:8642
```

Conversation APIs:

```text
POST /api/v1/hermes/sessions
GET  /api/v1/hermes/sessions/{session_id}
GET  /api/v1/hermes/sessions/{session_id}/messages
POST /api/v1/hermes/chat
```

`POST /api/v1/hermes/chat` accepts an optional `session_id`. If omitted,
GuangHeng creates both the local audit session and the corresponding Official
Hermes session. Subsequent turns reuse the stored Hermes session ID. Only user
messages, final assistant answers, sanitized tool summaries, structured tool
results, and timestamps are persisted. System instructions, provider secrets,
authorization headers, raw tracebacks, and model reasoning are not persisted.

Decision, proposal, and provenance fields are mapped only from MCP Tool Result
payloads. They are never extracted from the assistant's natural-language
answer. A proposal returned to Hermes must remain `PENDING`; Hermes has no
approval, execution, or Home Assistant write tool.

### Hermes 0.21.3 MCP compatibility notes

The Windows-native unattended API mode currently uses `trust: full` for the
GuangHeng MCP registration. This is a runtime compatibility workaround for an
Official Hermes 0.21.3 issue that rejects `untrusted` tools even when they carry
`readOnlyHint`. It is not a business authorization mechanism. The fixed
GuangHeng allow-list remains the security boundary and must stay at exactly the
existing 14 tools. It contains no approval, execution, or Home Assistant write
tool.

Official Hermes 0.21.3 also does not reliably re-register Streamable HTTP MCP
tools after the MCP process is interrupted. If the MCP endpoint is healthy but
Hermes reports missing or disconnected tools, restart the Hermes Gateway and
repeat tool discovery. GuangHeng deliberately does not kill or restart Hermes
automatically.
