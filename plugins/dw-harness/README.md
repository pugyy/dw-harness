# dw-harness plugin

Install-time options (userConfig):
- `python`: single executable path used by hook scripts (default `python`;
  on Windows prefer an absolute python.exe path — the exec form takes ONE
  command plus fixed args)
- `dialect`: default SQL dialect (odps / hive / spark / starrocks)

Hooks: PreToolUse guards (fail-closed: onFailure block + in-script deny
fallback), PostToolUse SQL write-after feedback, SessionStart state card,
PostCompact local capture, SessionEnd handoff. Out-of-band SQL changes are
covered by `dw lint --changed` in CI instead of a file watcher.
Skills: the 8-step workflow plus bootstrap / contract / check / next / review
/ backfill and an auto-loaded SQL reference. Agents: dw-explorer,
sql-validator, data-quality-checker, data-comparator (model: inherit; plugin
agents ignore permissionMode by design).

The bundled stdio MCP server (mcp/server.py) is deliberately NOT registered:
dw-harness MCP stays off until you opt in (see docs/mcp.md; template installs
use `dw init --mcp`).

Project-side files (AGENTS.md, rules, harness.json, contracts) are generated
by the `dw-bootstrap` skill / `dw init` — they are intentionally NOT shipped
by the plugin. Requires Claude Code >= 2.1.295 (userConfig options + hook
onFailure).
