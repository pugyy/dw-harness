#!/usr/bin/env python3
"""Record compact summaries and keep project context files available."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
