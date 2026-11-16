"""Reconcile semantics per spec item 14: prechecks, Decimal money, unit
conversion, zero baseline, NULL, tolerance combination, distinguishable
unverified outcomes."""
from __future__ import annotations

import unittest
from pathlib import Path

from dw_core.reconcile import ReconcileSpec, ReconcileError, reconcile

FIX = Path(__file__).resolve().parents[1] / "examples" / "demo" / "csv"


def spec(left: str, right: str, **over):
    base = {
        "left": {"adapter": "file", "path": str(FIX / left), "partition": "20261115"},
        "right": {"adapter": "file", "path": str(FIX / right), "partition": "20261115"},
        "keys": ["order_no"],
        "metrics": [
            {"column": "net_amount", "abs_tol": "0", "rel_tol": "0",
             "unit_left": "fen", "unit_right": "fen"},
            {"column": "pay_amount", "abs_tol": "0.01", "rel_tol": "0",
             "unit_left": "yuan", "unit_right": "yuan"},
        ],
        "sample_rows": 20, "max_rows": 100000,
    }
    base.update(over)
    return ReconcileSpec(**base)


class ReconcileTests(unittest.TestCase):
    def test_identical_pass(self):
        result = reconcile(spec("old.csv", "old.csv"))
        self.assertEqual(result.status, "pass")

    def test_swap_caught_key_level(self):
        result = reconcile(spec("new_swap.csv", "old.csv"))
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.totals["net_amount"]["delta_base_unit"], "0")
        keys = {d["key"].strip("()'). ('") for d in result.diffs}
        self.assertTrue({"O001", "O002"} & keys or len(keys) >= 2)

    def test_duplicate_keys_fail_precheck(self):
        result = reconcile(spec("dup_keys.csv", "old.csv"))
        self.assertEqual(result.status, "fail")
        self.assertTrue(result.prechecks["duplicate_keys"]["left"])

    def test_missing_partition_unverified(self):
        result = reconcile(spec("nope.csv", "old.csv"))
        self.assertEqual(result.status, "unverified")
        self.assertTrue(any("missing" in r for r in result.reasons))

    def test_zero_baseline_and_null(self):
        result = reconcile(spec("zero_null.csv", "old.csv"))
        self.assertEqual(result.status, "fail")
        self.assertTrue(result.null_mismatches)
        zero = [d for d in result.diffs if "zero-baseline" in d["tolerance"]]
        self.assertTrue(zero)

    def test_tolerance_boundary(self):
        result = reconcile(spec("tolerance_edge.csv", "old.csv"))
        failed_keys = [d["key"] for d in result.diffs if d["column"] == "pay_amount"]
        self.assertEqual(failed_keys, ["('O002',)"])

    def test_null_equals_null(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.csv"
            p.write_text("order_no,net_amount,pay_amount\nO001,,10.00\n", encoding="utf-8")
            result = reconcile(spec("old.csv", "old.csv"))  # sanity
            q = Path(tmp) / "b.csv"
            q.write_text("order_no,net_amount,pay_amount\nO001,,10.00\n", encoding="utf-8")
            both = reconcile(ReconcileSpec(
                left={"adapter": "file", "path": str(p), "partition": "x"},
                right={"adapter": "file", "path": str(q), "partition": "x"},
                keys=["order_no"], metrics=[{"column": "net_amount", "abs_tol": "0",
                                             "rel_tol": "0", "unit_left": "fen",
                                             "unit_right": "fen"}]))
            self.assertEqual(both.status, "pass")

    def test_unit_conversion_applies(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.csv"   # 10 yuan
            a.write_text("order_no,amt\nO001,10\n", encoding="utf-8")
            b = Path(tmp) / "b.csv"   # 1000 fen == 10 yuan
            b.write_text("order_no,amt\nO001,1000\n", encoding="utf-8")
            result = reconcile(ReconcileSpec(
                left={"adapter": "file", "path": str(a), "partition": "x"},
                right={"adapter": "file", "path": str(b), "partition": "x"},
                keys=["order_no"], metrics=[{"column": "amt", "abs_tol": "0",
                                             "rel_tol": "0", "unit_left": "yuan",
                                             "unit_right": "fen"}]))
            self.assertEqual(result.status, "pass")

    def test_rejects_bad_identifier(self):
        with self.assertRaises(ReconcileError):
            from dw_core.reconcile import StarRocksAdapter
            StarRocksAdapter({"table": "evil; DROP TABLE x", "partition": "p"},
                             ["k"], ["m"])


if __name__ == "__main__":
    unittest.main()
