#!/usr/bin/env python3
"""PreToolUse adapter: guard database commands on Bash and PowerShell."""
from __future__ import annotations

import sys
from pathlib import Path

from _bootstrap import emit_pretool_decision, project_root, read_payload, selftest


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest("guard_shell")
    payload = read_payload()
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    command = str(tool_input.get("command") or payload.get("raw") or "")
    if tool and tool not in ("Bash", "PowerShell"):
        return 0
    if not command.strip():
        return 0
    try:
        from dw_core.config import HarnessConfig
        from dw_core.guard import GuardEngine
        config = HarnessConfig.load(root=project_root())
        engine = GuardEngine(config)
        cwd = Path(payload["cwd"]) if payload.get("cwd") else Path.cwd()
        decision = engine.evaluate_command(command, cwd=cwd)
        if decision.decision == "deny":
            emit_pretool_decision("deny", decision.reasons or ["denied by dw-harness policy"])
            return 0
        if decision.decision == "ask":
            emit_pretool_decision("ask", decision.reasons or ["needs explicit confirmation"])
            return 0
        return 0
    except Exception as exc:  # fail closed for policy hooks
        emit_pretool_decision("deny", [f"dw-harness guard error (fail-closed): "
                                      f"{type(exc).__name__}: {exc}"])
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
