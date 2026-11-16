"""Guard policy tests per spec items 7/8: deny / ask / allow, -f scripts,
prod escalation, expired exceptions, PII, benign commands."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from dw_core.config import DEFAULT_CONFIG, HarnessConfig
from dw_core.guard import GuardEngine, scan_pii


def make_config(root: Path, **overrides) -> HarnessConfig:
    data = copy.deepcopy(DEFAULT_CONFIG)
    data["guard"].update(overrides)
    config = HarnessConfig(data=data, root=root, path=None)
    return config


class ShellGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = GuardEngine(make_config(self.root), env={},
                                  today=date(2026, 11, 16))

    def tearDown(self):
        self.tmp.cleanup()

    def test_drop_table_denied(self):
        decision = self.engine.evaluate_command("odpscmd -e 'DROP TABLE db.t'")
        self.assertEqual(decision.decision, "deny")

    def test_delete_without_where_denied(self):
        decision = self.engine.evaluate_command("odpscmd -e 'DELETE FROM db.t'")
        self.assertEqual(decision.decision, "deny")

    def test_f_script_inspected(self):
        script = self.root / "m.sql"
        script.write_text("TRUNCATE TABLE db.t;\n", encoding="utf-8")
        decision = self.engine.evaluate_command(f"odpscmd -f {script}", cwd=self.root)
        self.assertEqual(decision.decision, "deny")

    def test_prod_escalates_ask_to_deny(self):
        engine = GuardEngine(make_config(self.root), env={"DW_HARNESS_PROD": "1"},
                             today=date(2026, 11, 16))
        decision = engine.evaluate_command(
            "odpscmd -e \"INSERT OVERWRITE TABLE db.t PARTITION (partition_dt='20261115') SELECT 1\"")
        self.assertEqual(decision.decision, "deny")

    def test_dev_scoped_overwrite_allowed(self):
        decision = self.engine.evaluate_command(
            "odpscmd -e \"INSERT OVERWRITE TABLE db.t PARTITION (partition_dt='20261115') SELECT 1\"")
        self.assertEqual(decision.decision, "allow")

    def test_overwrite_without_partition_asks(self):
        decision = self.engine.evaluate_command(
            "odpscmd -e \"INSERT OVERWRITE TABLE db.t SELECT 1\"")
        self.assertEqual(decision.decision, "ask")

    def test_future_partition_asks(self):
        decision = self.engine.evaluate_command(
            "odpscmd -e \"INSERT OVERWRITE TABLE db.t PARTITION (partition_dt='20991231') SELECT 1\"")
        self.assertEqual(decision.decision, "ask")

    def test_benign_command_untouched(self):
        for command in ("ls -la", "git diff --stat", "cat report.md | grep total",
                        "npm run build", "echo hello"):
            decision = self.engine.evaluate_command(command)
            self.assertEqual(decision.decision, "allow", command)

    def test_string_literal_not_sql(self):
        decision = self.engine.evaluate_command("echo 'drop table db.t' >> notes.txt")
        self.assertEqual(decision.decision, "allow")

    def test_exception_within_window_grants(self):
        (self.root / ".claude" / "dw").mkdir(parents=True)
        (self.root / ".claude" / "dw" / "policy_exceptions.json").write_text(json.dumps([{
            "id": "exc-1", "approver": "lead", "reason": "scratch cleanup",
            "environment": "dev", "objects": ["db.scratch"],
            "operations": ["destructive"], "not_after": "2099-01-01"}]), encoding="utf-8")
        decision = self.engine.evaluate_command("odpscmd -e 'TRUNCATE TABLE db.scratch'")
        self.assertEqual(decision.decision, "allow")
        self.assertIn("exc-1", decision.exceptions)

    def test_expired_exception_does_not_grant(self):
        (self.root / ".claude" / "dw").mkdir(parents=True)
        (self.root / ".claude" / "dw" / "policy_exceptions.json").write_text(json.dumps([{
            "id": "exc-2", "approver": "lead", "reason": "old",
            "environment": "dev", "objects": ["db.scratch"],
            "operations": ["destructive"], "not_after": "2020-01-01"}]), encoding="utf-8")
        decision = self.engine.evaluate_command("odpscmd -e 'TRUNCATE TABLE db.scratch'")
        self.assertEqual(decision.decision, "deny")

    def test_decision_logged_with_hash(self):
        self.engine.evaluate_command("odpscmd -e 'DROP TABLE db.t'")
        log = self.root / ".claude" / "dw" / "guard_log.jsonl"
        self.assertTrue(log.is_file())
        entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(entry["decision"], "deny")
        self.assertEqual(len(entry["input_sha256_12"]), 12)

    def test_protected_object(self):
        config = make_config(self.root)
        config.data["protected_objects"] = ["db_a.dwd_trade_order_detail"]
        engine = GuardEngine(config, env={}, today=date(2026, 11, 16))
        decision = engine.evaluate_command(
            "odpscmd -e \"INSERT INTO db_a.dwd_trade_order_detail PARTITION (partition_dt='20261115') SELECT 1\"")
        self.assertEqual(decision.decision, "deny")


class PiiTests(unittest.TestCase):
    def test_phone_detected_and_masked(self):
        hits = scan_pii("contact 13812345678 now", ["cn_phone"])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["sample"], "138***78")
        self.assertNotIn("13812345678", json.dumps(hits))

    def test_write_guard_warns_on_pii(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = GuardEngine(make_config(root), env={})
            decision = engine.evaluate_write("data/seed.sql",
                                             "INSERT INTO t VALUES ('13812345678')")
            self.assertEqual(decision.decision, "allow")  # default action = warn
            self.assertTrue(any("PII" in r for r in decision.reasons))

    def test_write_guard_denies_when_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = make_config(root)
            config.data["pii"]["action"] = "deny"
            engine = GuardEngine(config, env={})
            decision = engine.evaluate_write("data/seed.sql",
                                             "INSERT INTO t VALUES ('11010119900307867X')")
            self.assertEqual(decision.decision, "deny")


if __name__ == "__main__":
    unittest.main()
