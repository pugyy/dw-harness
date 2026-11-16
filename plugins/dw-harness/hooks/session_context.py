#!/usr/bin/env python3
"""SessionStart adapter: inject the short session state card."""
from __future__ import annotations

import sys

from _bootstrap import emit_additional_context, project_root, read_payload, selftest


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest("session_context")
    read_payload()  # event input; the card is derived from files, not chat
    try:
        from dw_core.state import session_card
        card = session_card(project_root())
        # hookEventName MUST match the event that fired: SessionStart.
        emit_additional_context("SessionStart", card)
        return 0
    except Exception as exc:
        print(f"[dw-harness] session card error (non-blocking): "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
