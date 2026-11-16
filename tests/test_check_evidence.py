"""dw check four-state acceptance and evidence freshness per spec 15/16."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dw_core.check import CheckItem, CheckReport
from dw_core.evidence import build_evidence, save_evidence, text_digest, verify_evidence


class EvidenceTests(unittest.TestCase):
    def test_fresh_and_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = {"sql:x": "a" * 64, "contract": "b" * 64}
            ev = build_evidence("reconcile-db.t", inputs, {"status": "pass"}, root)
            save_evidence(ev, root, "reconcile-db.t")
            self.assertEqual(verify_evidence(ev, inputs)["state"], "valid")
            changed = dict(inputs, **{"sql:x": "c" * 64})
            self.assertEqual(verify_evidence(ev, changed)["state"], "stale")
            # evidence covering a superset of required inputs stays valid
            subset = {"sql:x": "a" * 64}
            self.assertEqual(verify_evidence(ev, subset)["state"], "valid")

    def test_none_evidence(self):
        self.assertEqual(verify_evidence(None, {})["state"], "missing")


class CheckReportTests(unittest.TestCase):
    def _report(self, items, mode="strict"):
        report = CheckReport(table="db.t", environment="dev", partition="20260101",
                             mode=mode)
        report.items.extend(CheckItem(*item) for item in items)
        return report

    def test_fail_outranks_unverified(self):
        report = self._report([("a", "unverified", "why"), ("b", "fail", "boom")])
        self.assertEqual(report.overall, "fail")
        self.assertEqual(report.exit_code, 1)

    def test_unverified_exit_2_strict(self):
        report = self._report([("a", "unverified", "no evidence")])
        self.assertEqual(report.overall, "unverified")
        self.assertEqual(report.exit_code, 2)

    def test_local_mode_keeps_status_but_exits_zero(self):
        report = self._report([("a", "unverified", "no evidence")], mode="local")
        self.assertEqual(report.overall, "unverified")
        self.assertEqual(report.exit_code, 0)
        md = report.to_markdown()
        self.assertIn("UNVERIFIED", md)
        self.assertIn("no evidence", md)

    def test_not_applicable_ignored_for_overall(self):
        report = self._report([("a", "not_applicable", "no baseline"), ("b", "pass", "")])
        self.assertEqual(report.overall, "pass")
        self.assertEqual(report.exit_code, 0)

    def test_markdown_render(self):
        report = self._report([("lint-sql", "pass", "clean"), ("reconcile", "fail", "diffs")])
        md = report.to_markdown()
        self.assertIn("| `lint-sql` | PASS |", md)
        self.assertIn("| `reconcile` | FAIL |", md)


class RunChecksTests(unittest.TestCase):
    def test_unmanaged_table_unverified(self):
        from dw_core.check import run_checks
        from dw_core.config import HarnessConfig
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = HarnessConfig(data={}, root=root, path=None)
            report = run_checks(config, "db.t")
            statuses = {i.name: i.status for i in report.items}
            self.assertEqual(statuses["contract-validate"], "unverified")
            self.assertEqual(statuses["lint-sql"], "not_applicable")
            self.assertEqual(report.exit_code, 2)

    def test_unit_change_fails_without_decision(self):
        from dw_core.check import run_checks
        from dw_core.config import HarnessConfig
        good = json.loads((Path(__file__).parents[1] / "examples" / "demo" / "contract.json").read_text(encoding="utf-8"))
        changed = json.loads((Path(__file__).parents[1] / "examples" / "demo" / "contract_changed.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts").mkdir()
            (root / "contracts" / "contract.json").write_text(json.dumps(changed), encoding="utf-8")
            (root / "baseline.json").write_text(json.dumps(good), encoding="utf-8")
            config = HarnessConfig(data={}, root=root, path=None)
            report = run_checks(config, "db_a.dws_trade_order_di",
                                contract_path=root / "contracts" / "contract.json",
                                baseline=root / "baseline.json")
            diff_item = next(i for i in report.items if i.name == "contract-diff")
            self.assertEqual(diff_item.status, "fail")
            self.assertIn("migration decision", diff_item.reason)
            self.assertEqual(report.exit_code, 1)


if __name__ == "__main__":
    unittest.main()
