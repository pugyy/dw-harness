#!/usr/bin/env python3
"""SessionEnd adapter: short handoff note for the next session."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from _bootstrap import project_root, read_payload, selftest


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest("handoff")
    read_payload()
    try:
        from dw_core.state import infer_step, load_state
        root = project_root()
        state = load_state(root)
        progress = infer_step(root)
        nxt = progress.get("next") or {"step": "-", "name": "all deliverables present"}
        lines = [
            f"# dw-harness handoff — {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            "",
            f"- table: {state.get('table', '-')}",
            f"- version: {state.get('version', '-')}",
            f"- next: Step {nxt['step']}/8 {nxt['name']}",
        ]
        constraints = state.get("constraints") or []
        for c in constraints[:5]:
            lines.append(f"- constraint: {c}")
        dw_dir = root / ".claude" / "dw"
        dw_dir.mkdir(parents=True, exist_ok=True)
        (dw_dir / "handoff.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
