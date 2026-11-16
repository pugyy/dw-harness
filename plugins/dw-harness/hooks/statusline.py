#!/usr/bin/env python3
"""Claude Code statusLine script: dw · table V1 · Step 3/8 · dialect."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _bootstrap import INSTALL_ROOT, project_root, selftest


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest("statusline")
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}
    try:
        from dw_core.state import infer_step, load_state
        root = project_root()
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
            parts.append(f"{state['table']}")
        if state.get("version"):
            parts.append(f"{state['version']}")
        step = state.get("step") or (f"{nxt.get('step')}/8" if nxt.get("step") else "")
        if step:
            parts.append(f"Step {step}")
        if dialect:
            parts.append(dialect)
        model = (payload.get("model") or {}).get("display_name", "")
        line = " · ".join(parts)
        print(json.dumps({"line": line + (f" | {model}" if model else ""),
                          "cache_control": {"type": "ephemeral"}},
                         ensure_ascii=False))
        return 0
    except Exception:
        print(json.dumps({"line": "dw"}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
