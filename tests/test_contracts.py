"""Contract / DDL / plan / DQC / impact tests per spec items 10-13."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dw_core.contracts import (crosscheck_ddl, diff_contracts, load_decisions,
                               normalize, record_decision, unapproved_breaking,
                               validate_contract)
from dw_core.ddl import diff_ddl, parse_create_table
from dw_core.dqc import check_rules, gen_rules, stable_id
from dw_core.impact import analyze_impact, collect_repo_edges

GOOD = {
    "contract_id": "db.t", "table": "db.t", "version": "1", "owner": "team",
    "granularity": "row per order", "business_keys": ["order_no"],
    "partition": {"column": "partition_dt", "type": "string", "format": "yyyyMMdd"},
    "columns": [
        {"name": "order_no", "type": "string", "nullable": True, "caliber": "k", "source": "s"},
        {"name": "net_amount", "type": "decimal(20,4)", "currency": "CNY", "unit": "fen"},
    ],
    "quality": {"money_tolerance": "0.01%"},
    "sla": {"time": "08:00"},
    "sources": ["db.src"],
}

DDL_ODPS = """
CREATE TABLE IF NOT EXISTS db.t (
    order_no STRING COMMENT '订单号|src|直接继承',
    net_amount DECIMAL(20,4) COMMENT '净额|src|直接继承'
)
PARTITIONED BY (partition_dt STRING)
COMMENT 'orders'
LIFECYCLE 365;
"""


class ContractTests(unittest.TestCase):
    def test_validate_ok(self):
        self.assertEqual(validate_contract(normalize(GOOD)), [])

    def test_currency_without_unit_rejected(self):
        bad = json.loads(json.dumps(GOOD))
        bad["columns"][1].pop("unit")
        problems = validate_contract(normalize(bad))
        self.assertTrue(any("unit" in p for p in problems))

    def test_unit_change_is_breaking(self):
        changed = json.loads(json.dumps(GOOD))
        changed["columns"][1]["unit"] = "yuan"
        diffs = diff_contracts(normalize(changed), normalize(GOOD))
        self.assertTrue(any(c["type"] == "unit_changed" and c["breaking"] for c in diffs))

    def test_migration_decision_unblocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changed = json.loads(json.dumps(GOOD))
            changed["columns"][1]["unit"] = "yuan"
            cur, base = normalize(changed), normalize(GOOD)
            diffs = diff_contracts(cur, base)
            self.assertTrue(unapproved_breaking(diffs, cur, base, []))
            record_decision(root, "db.t", {"from_hash": base["digest"],
                                           "to_hash": cur["digest"],
                                           "approver": "lead", "reason": "unit migration"})
            self.assertFalse(unapproved_breaking(diffs, cur, base,
                                                 load_decisions(root, "db.t")))

    def test_ddl_crosscheck(self):
        ddl = parse_create_table(DDL_ODPS)[0]
        self.assertEqual([c.name for c in ddl.columns], ["order_no", "net_amount"])
        self.assertEqual([p.name for p in ddl.partition_columns], ["partition_dt"])
        findings = crosscheck_ddl(normalize(GOOD), ddl)
        self.assertEqual(findings, [])

    def test_ddl_crosscheck_catches_type_mismatch(self):
        ddl_text = DDL_ODPS.replace("DECIMAL(20,4)", "DOUBLE")
        findings = crosscheck_ddl(normalize(GOOD), parse_create_table(ddl_text)[0])
        self.assertTrue(any(f["finding"] == "type_mismatch" for f in findings))


class DdlDiffTests(unittest.TestCase):
    def test_add_column_generates_alter(self):
        before = parse_create_table(DDL_ODPS)[0]
        after = parse_create_table(
            DDL_ODPS.replace("net_amount DECIMAL(20,4)", "net_amount DECIMAL(20,4),\n    channel STRING COMMENT '渠道|src|直接继承'"))[0]
        changes = diff_ddl(before, after)
        added = [c for c in changes if c.kind == "add_column"]
        self.assertEqual(len(added), 1)
        self.assertIn("ADD COLUMNS", added[0].candidate_sql)

    def test_narrowing_requires_flag(self):
        after = parse_create_table(DDL_ODPS.replace("DECIMAL(20,4)", "DECIMAL(10,2)"))[0]
        before = parse_create_table(DDL_ODPS)[0]
        strict = diff_ddl(before, after, allow_narrowing=False)
        self.assertTrue(any(c.kind == "narrow" and not c.candidate_sql for c in strict))
        loose = diff_ddl(before, after, allow_narrowing=True)
        self.assertTrue(any(c.kind == "narrow" and c.candidate_sql for c in loose))

    def test_starrocks_modify_syntax(self):
        before = parse_create_table(DDL_ODPS, dialect="starrocks")[0]
        after = parse_create_table(DDL_ODPS.replace("DECIMAL(20,4)", "DECIMAL(24,4)"),
                                   dialect="starrocks")[0]
        changes = diff_ddl(before, after)
        widen = [c for c in changes if c.kind == "widen"]
        self.assertTrue(widen)
        self.assertIn("MODIFY COLUMN", widen[0].candidate_sql)


class DqcTests(unittest.TestCase):
    def test_stable_ids(self):
        a = stable_id("db.t", "pk_not_null", ["order_no"], "0 null rows")
        b = stable_id("db.t", "pk_not_null", ["order_no"], "0 null rows")
        c = stable_id("db.t", "pk_not_null", ["order_no"], "1 null rows")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_gen_and_check(self):
        contract = normalize(GOOD)
        rules = gen_rules(contract)
        self.assertEqual(check_rules(rules, contract), [])
        rules["rules"][0]["threshold"] = "5 null rows"
        self.assertTrue(check_rules(rules, contract))


class ImpactTests(unittest.TestCase):
    def test_repo_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "insert_a.sql").write_text(
                "INSERT OVERWRITE TABLE db.dws_a PARTITION (partition_dt='20260101')\n"
                "SELECT order_no, net_amount FROM db.dwd_b WHERE partition_dt='20260101';\n",
                encoding="utf-8")
            report = analyze_impact(root, "db.dws_a")
            self.assertEqual(len(report.upstream), 1)
            self.assertEqual(report.upstream[0]["source"], "db.dwd_b")
            self.assertEqual(set(report.upstream[0]["columns"]), {"order_no", "net_amount"})
            unknown_report = analyze_impact(root, "db.unknown")
            self.assertTrue(unknown_report.unknown)


if __name__ == "__main__":
    unittest.main()
