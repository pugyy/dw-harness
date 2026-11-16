#!/usr/bin/env python3
"""One-command offline end-to-end acceptance (clean-environment reproducible):

    python scripts/run_demo.py

No credentials, no Claude Code, no databases required. Exit 0 = all cases
PASS. Counter-cases (a)-(f) from the v2 acceptance spec are included.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from dw_core.demo import run_demo  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run_demo(fixtures=REPO / "examples" / "demo",
                              out_dir=REPO / "examples" / "demo" / "report"))
