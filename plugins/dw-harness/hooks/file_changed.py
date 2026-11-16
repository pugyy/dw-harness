#!/usr/bin/env python3
"""FileChanged adapter: optional out-of-band SQL change feedback."""
from __future__ import annotations

import sys

from _bootstrap import emit_additional_context, project_root, read_payload, selftest


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest("file_changed")
    payload = read_payload()
    file_path = str(payload.get("file_path") or (payload.get("tool_input") or {}).get("file_path") or "")
    if not file_path.lower().endswith(".sql"):
        return 0
    try:
        from dw_core.config import HarnessConfig
        from dw_core.rules import lint_sql
        config = HarnessConfig.load(root=project_root())
        with open(file_path, encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
        result = lint_sql(text, config.resolve_dialect(file_path), config)
        if result.issues:
            lines = [f"[dw-harness] out-of-band change checked: {file_path}"]
            for issue in result.issues[:10]:
                lines.append(f"  [{issue.severity}] line {issue.line} {issue.rule}: {issue.message}")
            emit_additional_context("FileChanged", "\n".join(lines))
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
