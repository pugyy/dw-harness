#!/usr/bin/env python3
"""PostToolUse adapter: write-after feedback for SQL files (Write/Edit)."""
from __future__ import annotations

import sys

from _bootstrap import emit_additional_context, project_root, read_payload, selftest


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest("validate_post")
    payload = read_payload()
    tool_input = payload.get("tool_input") or {}
    file_path = str(tool_input.get("file_path") or "")
    if not file_path.lower().endswith(".sql"):
        return 0
    try:
        from dw_core.config import HarnessConfig
        from dw_core.rules import lint_sql
        config = HarnessConfig.load(root=project_root())
        with open(file_path, encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
        dialect = config.resolve_dialect(file_path)
        result = lint_sql(text, dialect, config)
        if result.errors:
            print(f"[dw-harness] SQL check failed (dialect={dialect}): {file_path}",
                  file=sys.stderr)
            for issue in result.errors:
                print(f"  [ERROR] line {issue.line} {issue.rule}: {issue.message}",
                      file=sys.stderr)
            return 2  # write-after feedback: file is on disk; fix and rewrite
        if result.warns:
            lines = [f"[dw-harness] SQL warnings (dialect={dialect}): {file_path}"]
            for issue in result.warns[:10]:
                lines.append(f"  [WARN] line {issue.line} {issue.rule}: {issue.message}")
            emit_additional_context("PostToolUse", "\n".join(lines))
        return 0
    except OSError as exc:
        print(f"[dw-harness] cannot read {file_path}: {exc}", file=sys.stderr)
        return 0
    except Exception as exc:  # non-blocking: report only
        print(f"[dw-harness] lint error (non-blocking, run `dw doctor`): "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
