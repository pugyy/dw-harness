# dw-harness plugin

Install-time options (userConfig):
- `python`: interpreter used by hook scripts (default `python`; use `py -3`
  or an absolute path on Windows as needed)
- `dialect`: default SQL dialect (odps / hive / spark / starrocks)

Hooks: PreToolUse guards (fail-closed), PostToolUse SQL write-after feedback,
SessionStart state card, PostCompact local capture, FileChanged out-of-band
check, SessionEnd handoff. Skills: the 8-step workflow plus bootstrap /
contract / check / next / review / backfill and an auto-loaded SQL reference.
Agents: dw-explorer, sql-validator, data-quality-checker, data-comparator
(model: inherit; plugin agents ignore permissionMode by design).

Project-side files (AGENTS.md, rules, harness.json, contracts) are generated
by the `dw-bootstrap` skill / `dw init` — they are intentionally NOT shipped
by the plugin. Requires Claude Code >= 2.1.271 (userConfig options).
