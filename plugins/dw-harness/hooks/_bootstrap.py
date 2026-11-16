"""Shared bootstrap for Claude Code hook adapters.

Layout contract (both plugin and copy-template installs):
    <install_root>/hooks/<this script>.py
    <install_root>/dw_core/            <- vendored core, importable as a package
    <install_root>/dialects/*.json

Project root comes from CLAUDE_PROJECT_DIR when Claude Code provides it,
falling back to a walk-up search. Policy hooks fail closed: any internal
error becomes a deny with the reason attached, so a broken guard never
silently allows.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

INSTALL_ROOT = Path(__file__).resolve().parent.parent
for candidate in (INSTALL_ROOT, INSTALL_ROOT.parent):
    if (candidate / "dw_core").is_dir():
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
        break


def read_payload() -> dict:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"raw": raw}
    except json.JSONDecodeError:
        return {"raw": raw}


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    cur = Path(os.getcwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".claude" / "dw").is_dir() or (candidate / ".git").exists():
            return candidate
    return cur


def emit_pretool_decision(decision: str, reasons) -> None:
    """deny / ask / allow via the documented PreToolUse JSON contract."""
    import json as _json
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": "; ".join(str(r) for r in reasons)[:2000],
        }
    }
    print(_json.dumps(payload, ensure_ascii=False))


def emit_additional_context(event_name: str, text: str) -> None:
    import json as _json
    payload = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": text,
        }
    }
    print(_json.dumps(payload, ensure_ascii=False))


def selftest(name: str) -> int:
    import dw_core
    print(f"ok {name} dw_core={dw_core.__version__}")
    return 0
