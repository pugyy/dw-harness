"""MCP protocol selftest + offline demo run (spec items 19-21)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from dw_core.mcp_selftest import mcp_selftest

REPO = Path(__file__).resolve().parents[1]


class McpTests(unittest.TestCase):
    def test_handshake_list_and_call(self):
        self.assertTrue(mcp_selftest(REPO / "mcp" / "server.py"))


class DemoTests(unittest.TestCase):
    """The offline end-to-end acceptance (counter-cases a-f) as a test."""

    def test_demo_all_cases_pass(self):
        from dw_core.demo import run_demo
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report"
            code = run_demo(fixtures=REPO / "examples" / "demo", out_dir=out)
            payload = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["failed"], 0,
                             json.dumps(payload["cases"], ensure_ascii=False, indent=1))
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
