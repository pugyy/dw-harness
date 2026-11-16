#!/usr/bin/env python3
"""Claude Code statusLine script: prints one plain-text line.

statusLine contract: the session payload arrives on stdin; whatever the
script prints to stdout becomes the status bar verbatim (no JSON wrapping).
"""
from __future__ import annotations

import json
import sys

from _bootstrap import project_root, selftest


def build_line(root) -> str:
    from dw_core.state import infer_step, load_state
    state = load_state(root)
    config_path = root / ".claude" / "dw" / "harness.json"
    dialect = ""
    if config_path.is_file():
        try:
            dialect = json.loads(config_path.read_text(encoding="utf-8-sig")) \
                .get("dialect", {}).get("default", "")
        except json.JSONDecodeError:
            pass
    progress = infer_step(root)
    nxt = progress.get("next") or {}
    parts = ["dw"]
    if state.get("table"):
        parts.append(str(state["table"]))
    if state.get("version"):
        parts.append(str(state["version"]))
    step = state.get("step") or (f"{nxt.get('step')}/8" if nxt.get("step") else "")
    if step:
        parts.append(f"Step {step}")
    if dialect:
        parts.append(dialect)
    return " · ".join(parts)


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest("statusline")
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except json.JSONDecodeError:
        payload = {}
    try:
        line = build_line(project_root())
    except Exception:
        line = "dw"
    model = (payload.get("model") or {}).get("display_name", "")
    print(line + (f" | {model}" if model else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
