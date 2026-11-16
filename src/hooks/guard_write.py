#!/usr/bin/env python3
"""PreToolUse adapter: PII / protected-object guard for Write and Edit."""
from __future__ import annotations

import sys

from _bootstrap import (emit_additional_context, emit_pretool_decision,
                        project_root, read_payload, selftest)


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest("guard_write")
    payload = read_payload()
    tool = str(payload.get("tool_name") or "")
    if tool and tool not in ("Write", "Edit"):
        return 0
    tool_input = payload.get("tool_input") or {}
    file_path = str(tool_input.get("file_path") or "")
    content = str(tool_input.get("content") or tool_input.get("new_string") or "")
    if not file_path:
        return 0
    try:
        from dw_core.config import HarnessConfig
        from dw_core.guard import GuardEngine
        config = HarnessConfig.load(root=project_root())
        engine = GuardEngine(config)
        decision = engine.evaluate_write(file_path, content)
        engine.log("PreToolUse:Write", {"file_path": file_path}, decision, file_path)
        if decision.decision == "deny":
            emit_pretool_decision("deny", decision.reasons or ["write denied by policy"])
            return 0
        if decision.reasons:
            emit_additional_context("PreToolUse",
                                    "[dw-harness] " + "; ".join(decision.reasons))
        return 0
    except Exception as exc:  # fail closed for policy hooks
        emit_pretool_decision("deny", [f"dw-harness write guard error (fail-closed): "
                                      f"{type(exc).__name__}: {exc}"])
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
