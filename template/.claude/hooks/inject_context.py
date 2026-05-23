#!/usr/bin/env python3
"""Re-inject data warehouse context after Claude Code compacts a conversation."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def emit_additional_context(content: str) -> None:
    if not content.strip():
        return
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostCompact",
            "additionalContext": content,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    context_dir = project_dir / ".claude" / "context"
    context_dir.mkdir(parents=True, exist_ok=True)

    compact_summary = payload.get("compact_summary")
    if compact_summary:
        target = context_dir / "last_compact_summary.md"
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        target.write_text(
            f"# Last Compact Summary\n\n- Updated: {timestamp}\n\n{compact_summary}\n",
            encoding="utf-8",
        )

    conventions = read_text(context_dir / "0x_conventions.md")
    if conventions:
        emit_additional_context(
            "# 数仓 Harness 规范重注入\n\n"
            "以下内容来自 `.claude/context/0x_conventions.md`，请在 compact 后继续遵守。\n\n"
            f"{conventions}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
