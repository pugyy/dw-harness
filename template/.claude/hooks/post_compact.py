#!/usr/bin/env python3
"""PostCompact adapter: local state capture only — no context injection.

The PostCompact event has no additionalContext contract; the compaction
record is persisted so `dw next` / handoff can use it later.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from _bootstrap import project_root, read_payload, selftest


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest("post_compact")
    payload = read_payload()
    try:
        dw_dir = project_root() / ".claude" / "dw"
        dw_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "trigger": payload.get("trigger", payload.get("source", "")),
            "summary_chars": len(str(payload.get("compact_summary", "") or "")),
        }
        (dw_dir / "last_compact.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 0
    except Exception:
        return 0  # never disturb the session over local bookkeeping


if __name__ == "__main__":
    raise SystemExit(main())
