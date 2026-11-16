"""P0 regression tests from the rc.1 audit: the evidence chain must work on
the REAL CLI producer path, truncation must never pass, unreadable -f must
not allow, interpreter substitution must survive Windows paths, migration
must not silently drop guards behind a user matcher."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from . import SRC

REPO = Path(__file__).resolve().parents[1]


def run_cli(args, cwd, env=None):
    import os
    full_env = dict(os.environ)
    full_env["PYTHONPATH"] = str(SRC) + os.pathsep + full_env.get("PYTHONPATH", "")
    if env:
        full_env.update(env)
    return subprocess.run([sys.executable, "-m", "dw_core.cli", *args],
                          cwd=str(cwd), capture_output=True, text=True,
                          timeout=120, env=full_env)


class CliEvidenceChainTests(unittest.TestCase):
    """CLI reconcile --save-evidence -> dw check must verify (P0-1/P0-2)."""

    KEY = "test-evidence-key"

    def setUp(self):
        import os
        os.environ["DW_HARNESS_EVIDENCE_KEY"] = self.KEY

    def tearDown(self):
        import os
        os.environ.pop("DW_HARNESS_EVIDENCE_KEY", None)

    def _project(self, root: Path):
        (root / ".claude" / "dw").mkdir(parents=True)
        (root / "contracts").mkdir()
        shutil_copy = __import__("shutil").copyfile
        shutil_copy(REPO / "examples" / "demo" / "harness.json",
                    root / ".claude" / "dw" / "harness.json")
        shutil_copy(REPO / "examples" / "demo" / "contract.json",
                    root / "contracts" / "contract.json")
        (root / "insert_dws_trade_order_di.sql").write_text(
            (REPO / "examples" / "demo" / "insert_orders.sql").read_text(encoding="utf-8"),
            encoding="utf-8")
        (root / "ddl_dws_trade_order_di.sql").write_text(
            "CREATE TABLE IF NOT EXISTS db_a.dws_trade_order_di (\n"
            "    order_no STRING NOT NULL COMMENT '订单号|dwd|直接继承',\n"
            "    net_amount DECIMAL(20,4) COMMENT '净额|dwd|直接继承',\n"
            "    pay_amount DECIMAL(20,4) COMMENT '支付金额|dwd|直接继承',\n"
            "    order_status STRING COMMENT '状态|dwd|直接继承'\n"
            ")\n"
            "PARTITIONED BY (partition_dt STRING)\n"
            "COMMENT 'orders'\n"
            "LIFECYCLE 365;\n", encoding="utf-8")
        csv_path = root / "orders.csv"
        shutil_copy(REPO / "examples" / "demo" / "csv" / "old.csv", csv_path)
        spec = {
            "table": "db_a.dws_trade_order_di",
            "left": {"adapter": "file",
                     "path": str(csv_path),
                     "partition": "20261115"},
            "right": {"adapter": "file",
                      "path": str(csv_path),
                      "partition": "20261115"},
            "keys": ["order_no"],
            "metrics": [{"column": "net_amount", "abs_tol": "0", "rel_tol": "0",
                         "unit_left": "fen", "unit_right": "fen"}],
        }
        (root / "reconcile_dws_trade_order_di.json").write_text(
            json.dumps(spec, indent=2), encoding="utf-8")
        return root / "reconcile_dws_trade_order_di.json"

    def test_cli_produce_then_check_verifies(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = self._project(root)
            proc = run_cli(["reconcile", "--spec", str(spec_path), "--save-evidence",
                            "--contract", str(root / "contracts" / "contract.json"),
                            "--sql", str(root / "insert_dws_trade_order_di.sql"),
                            "--ddl", str(root / "ddl_dws_trade_order_di.sql")], root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["evidence"], "saved")
            # generate DQC from the same contract via the real CLI producer
            proc = run_cli(["dqc", "gen",
                            "--contract", str(root / "contracts" / "contract.json"),
                            "--out", str(root / "dqc_dws_trade_order_di.json")], root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            from dw_core.check import run_checks
            from dw_core.config import HarnessConfig
            config = HarnessConfig.load(root=root)
            report = run_checks(
                config, "db_a.dws_trade_order_di", "offline", "20261115", sql_files=[
                    root / "insert_dws_trade_order_di.sql"],
                contract_path=root / "contracts" / "contract.json",
                ddl_path=root / "ddl_dws_trade_order_di.sql",
                dqc_path=root / "dqc_dws_trade_order_di.json",
                reconcile_spec=spec_path, mode="strict")
            item = next(i for i in report.items if i.name == "reconcile")
            self.assertEqual(item.status, "pass", item.reason)
            self.assertEqual(report.exit_code, 0,
                             json.dumps([i.to_dict() for i in report.items]))

            # input drift -> unverified, strict exit 2
            (root / "insert_dws_trade_order_di.sql").write_text(
                "-- touched\n" + (root / "insert_dws_trade_order_di.sql")
                .read_text(encoding="utf-8"), encoding="utf-8")
            report2 = run_checks(
                config, "db_a.dws_trade_order_di", "offline", "20261115", sql_files=[
                    root / "insert_dws_trade_order_di.sql"],
                contract_path=root / "contracts" / "contract.json",
                reconcile_spec=spec_path, mode="strict")
            item2 = next(i for i in report2.items if i.name == "reconcile")
            self.assertEqual(item2.status, "unverified")
            self.assertIn("changed", item2.reason)

    def test_cli_rejects_replayed_scope_and_mutated_source_data(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = self._project(root)
            contract = "contracts/contract.json"
            sql = "insert_dws_trade_order_di.sql"
            ddl = "ddl_dws_trade_order_di.sql"
            result = run_cli(["reconcile", "--spec", str(spec), "--save-evidence",
                              "--contract", contract, "--sql", sql, "--ddl", ddl], root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(run_cli(["dqc", "gen", "--contract", contract], root).returncode, 0)
            cmd = ["check", "--table", "db_a.dws_trade_order_di", "--contract", contract,
                   "--sql", sql, "--ddl", ddl, "--reconcile-spec", str(spec), "--out-json", "report.json"]

            def check(environment, partition, expected):
                proc = run_cli([*cmd, "--env", environment, "--partition", partition], root)
                self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
                return next(i for i in json.loads((root / "report.json").read_text(encoding="utf-8"))
                            ["items"] if i["name"] == "reconcile")

            self.assertEqual(check("offline", "20261115", 0)["status"], "pass")
            for environment, partition in (("prod", "20261115"), ("offline", "20261116")):
                self.assertIn("scope", check(environment, partition, 2)["reason"])
            csv = root / "orders.csv"
            previous_csv = csv.read_text(encoding="utf-8")
            csv.write_text(previous_csv.replace("1000", "1001"), encoding="utf-8")
            self.assertIn("file", check("offline", "20261115", 2)["reason"])
            csv.write_text(previous_csv, encoding="utf-8")
            config = root / ".claude" / "dw" / "harness.json"
            data = json.loads(config.read_text(encoding="utf-8"))
            data["money_fields"] = "tax"
            config.write_text(json.dumps(data), encoding="utf-8")
            self.assertIn("policy", check("offline", "20261115", 2)["reason"])

    def test_manual_producer_rejected_in_strict_check(self):
        import tempfile
        from dw_core.evidence import verify_evidence
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = self._project(root)
            run_cli(["reconcile", "--spec", str(spec_path), "--save-evidence"],
                    root, env={"DW_HARNESS_EVIDENCE_KEY": self.KEY})
            from dw_core.evidence import load_evidence
            ev = load_evidence(root, "reconcile-db_a.dws_trade_order_di")
            self.assertEqual(ev.get("producer"), "dw-reconcile")
            forged = dict(ev)
            forged["producer"] = "manual"
            state = verify_evidence(forged, {}, strict=True)
            self.assertEqual(state["state"], "untrusted")

    def test_partial_binding_cannot_hide_sql_drift(self):
        """R1: evidence bound only to the contract; the SQL drifts -> UNVERIFIED."""
        import tempfile
        from dw_core.check import run_checks
        from dw_core.config import HarnessConfig
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_path = self._project(root)
            proc = run_cli(["reconcile", "--spec", str(spec_path), "--save-evidence",
                            "--contract", str(root / "contracts" / "contract.json")],
                           root, env={"DW_HARNESS_EVIDENCE_KEY": self.KEY})
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            (root / "insert_dws_trade_order_di.sql").write_text(
                "-- drifted\n" + (root / "insert_dws_trade_order_di.sql")
                .read_text(encoding="utf-8"), encoding="utf-8")
            config = HarnessConfig.load(root=root)
            report = run_checks(
                config, "db_a.dws_trade_order_di", "offline", "20261115",
                sql_files=[root / "insert_dws_trade_order_di.sql"],
                contract_path=root / "contracts" / "contract.json",
                reconcile_spec=spec_path, mode="strict")
            item = next(i for i in report.items if i.name == "reconcile")
            self.assertEqual(item.status, "unverified")
            self.assertIn("not covered", item.reason)

    def test_forged_producer_without_key_rejected(self):
        """R2: unsigned producer=dw-reconcile claims are refused in strict."""
        import os
        import tempfile
        from dw_core.evidence import build_evidence, verify_evidence
        with tempfile.TemporaryDirectory() as tmp:
            os.environ.pop("DW_HARNESS_EVIDENCE_KEY", None)
            ev = build_evidence("reconcile-x", {"contract": "a" * 64},
                                {"status": "pass"}, Path(tmp), producer="dw-reconcile")
            self.assertEqual(ev["signature"], "")  # produced without a key
            state = verify_evidence(ev, {"contract": "a" * 64}, strict=True)
            self.assertEqual(state["state"], "untrusted")
            self.assertIn("forged", state["reason"])

    def test_signed_evidence_roundtrip_and_tamper(self):
        """key closed loop: sign -> verify ok; tamper -> signature mismatch."""
        import tempfile
        from dw_core.evidence import build_evidence, verify_evidence
        with tempfile.TemporaryDirectory() as tmp:
            ev = build_evidence("reconcile-x", {"contract": "a" * 64},
                                {"status": "pass"}, Path(tmp), producer="dw-reconcile")
            self.assertNotEqual(ev["signature"], "")
            self.assertEqual(verify_evidence(ev, {"contract": "a" * 64},
                                             strict=True)["state"], "valid")
            tampered = dict(ev)
            tampered["result_summary"] = {"status": "pass", "note": "hand-blessed"}
            state = verify_evidence(tampered, {"contract": "a" * 64}, strict=True)
            self.assertEqual(state["state"], "untrusted")


class TruncationTests(unittest.TestCase):
    def test_truncated_never_passes(self):
        from dw_core.reconcile import ReconcileSpec, reconcile
        fix = REPO / "examples" / "demo" / "csv"
        spec = ReconcileSpec(
            left={"adapter": "file", "path": str(fix / "old.csv"), "partition": "p"},
            right={"adapter": "file", "path": str(fix / "old.csv"), "partition": "p"},
            keys=["order_no"],
            metrics=[{"column": "net_amount", "abs_tol": "0", "rel_tol": "0",
                      "unit_left": "fen", "unit_right": "fen"}],
            sample_rows=5, max_rows=2)
        result = reconcile(spec)
        self.assertTrue(result.truncated)
        self.assertEqual(result.status, "unverified")
        self.assertTrue(any("truncated" in r for r in result.reasons))


class DbCredentialTests(unittest.TestCase):
    def test_maxcompute_missing_credentials_is_unverified_not_traceback(self):
        """rc.3 audit: partition_exists failures must surface as UNVERIFIED
        with a reason, never as an exception out of reconcile()."""
        import os
        from dw_core.reconcile import ReconcileSpec, reconcile
        saved = {k: os.environ.pop(k, None) for k in list(os.environ)
                 if k.startswith("DW_HARNESS_ODPS_")}
        try:
            spec = ReconcileSpec(
                left={"adapter": "maxcompute", "table": "db.t",
                      "partition": "20261115"},
                right={"adapter": "file",
                       "path": str(REPO / "examples" / "demo" / "csv" / "old.csv"),
                       "partition": "20261115"},
                keys=["order_no"],
                metrics=[{"column": "net_amount", "abs_tol": "0", "rel_tol": "0",
                          "unit_left": "fen", "unit_right": "fen"}])
            result = reconcile(spec)  # must not raise
            self.assertEqual(result.status, "unverified")
            self.assertTrue(any("credential" in r or "partition check failed" in r
                                for r in result.reasons), result.reasons)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


class StatuslineCommandTests(unittest.TestCase):
    def _command(self, python: str) -> str:
        import tempfile
        from dw_core.migrate import run_init
        template = REPO / "template"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude").mkdir(parents=True)
            (root / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
            run_init(root, template, python, "", statusline=True)
            settings = json.loads((root / ".claude" / "settings.json")
                                  .read_text(encoding="utf-8"))
            status = settings["statusLine"]
            self.assertNotIn("args", status)
            self.assertEqual(status["type"], "command")
            return status["command"]

    def test_space_path_quoted(self):
        command = self._command(r"C:\Program Files\Python39\python.exe")
        self.assertIn('"C:\\Program Files\\Python39\\python.exe"', command)
        self.assertTrue(command.rstrip().endswith('statusline.py"'), command)
        self.assertNotIn("${CLAUDE_PROJECT_DIR}", command)  # absolute, not env-gamble

    def test_cjk_path_quoted(self):
        command = self._command(r"D:\工具\python.exe")
        self.assertIn('"D:\\工具\\python.exe"', command)

    def test_py_dash_three(self):
        command = self._command("py -3")
        self.assertIn('"py" -3 ', command)


class DialectPackTests(unittest.TestCase):
    def test_bundled_packs_load(self):
        from dw_core.config import DEFAULT_CONFIG, HarnessConfig
        config = HarnessConfig(data=dict(DEFAULT_CONFIG), root=Path("."), path=None)
        pack = config.dialect_pack("starrocks")
        self.assertEqual(pack.get("rule_levels", {}).get("insert-requires-partition"),
                         "warn")
        for dialect in ("odps", "hive", "spark", "starrocks"):
            self.assertTrue(config.dialect_pack(dialect), dialect)

    def test_custom_pack_overrides_rules(self):
        import tempfile
        from dw_core.config import DEFAULT_CONFIG, HarnessConfig
        from dw_core.rules import lint_sql
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = Path(tmp)
            (pack_dir / "hive.json").write_text(
                json.dumps({"rule_levels": {"no-select-star": "off"}}), encoding="utf-8")
            config = HarnessConfig(data=dict(DEFAULT_CONFIG), root=Path(tmp),
                                   path=None, dialect_dir=pack_dir)
            result = lint_sql("SELECT * FROM t", "hive", config)
            self.assertNotIn("no-select-star", {i.rule for i in result.issues})


class UnreadableScriptGuardTests(unittest.TestCase):
    def test_missing_f_script_not_allowed(self):
        import tempfile
        from dw_core.config import DEFAULT_CONFIG, HarnessConfig
        from dw_core.guard import GuardEngine
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = GuardEngine(HarnessConfig(data=dict(DEFAULT_CONFIG), root=root,
                                               path=None), env={})
            decision = engine.evaluate_command("odpscmd -f no_such_file.sql", cwd=root)
            self.assertIn(decision.decision, ("ask", "deny"))
            self.assertTrue(any("unreadable" in r for r in decision.reasons))

    def test_windows_client_wrappers_recognized(self):
        import tempfile
        from dw_core.config import DEFAULT_CONFIG, HarnessConfig
        from dw_core.guard import GuardEngine
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = GuardEngine(HarnessConfig(data=dict(DEFAULT_CONFIG), root=root,
                                               path=None), env={})
            decision = engine.evaluate_command("odpscmd.exe -e 'DROP TABLE db.t'")
            self.assertEqual(decision.decision, "deny")
            decision = engine.evaluate_command("beeline.cmd -e 'TRUNCATE TABLE db.t'")
            self.assertEqual(decision.decision, "deny")

    def test_drop_partition_is_destructive(self):
        import tempfile
        from dw_core.config import DEFAULT_CONFIG, HarnessConfig
        from dw_core.guard import GuardEngine
        with tempfile.TemporaryDirectory() as tmp:
            engine = GuardEngine(HarnessConfig(data=dict(DEFAULT_CONFIG),
                                               root=Path(tmp), path=None), env={})
            decision = engine.evaluate_command(
                "odpscmd -e 'ALTER TABLE db.t DROP PARTITION (dt=20200101)'")
            self.assertEqual(decision.decision, "deny")


class PythonSubstitutionTests(unittest.TestCase):
    def _settings_after_init(self, python: str) -> dict:
        import tempfile
        from dw_core.migrate import run_init
        template = REPO / "template"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude").mkdir(parents=True)
            (root / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
            run_init(root, template, python, "")
            return json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))

    def test_windows_absolute_path(self):
        settings = self._settings_after_init(r"C:\Python39\python.exe")
        pre = settings["hooks"]["PreToolUse"]
        commands = [h["command"] for block in pre for h in block["hooks"]]
        self.assertIn(r"C:\Python39\python.exe", commands)

    def test_py_dash_three_splits_into_command_and_args(self):
        settings = self._settings_after_init("py -3")
        pre = settings["hooks"]["PreToolUse"]
        hook = next(h for block in pre for h in block["hooks"]
                    if "guard_shell" in str(h["args"]))
        self.assertEqual(hook["command"], "py")
        self.assertEqual(hook["args"][0], "-3")
        self.assertTrue(hook["args"][-1].endswith("guard_shell.py"))

    def test_chinese_path_survives(self):
        settings = self._settings_after_init(r"D:\工具\python.exe")
        pre = settings["hooks"]["PreToolUse"]
        commands = [h["command"] for block in pre for h in block["hooks"]]
        self.assertIn(r"D:\工具\python.exe", commands)


class MigrationConflictTests(unittest.TestCase):
    def test_user_hook_same_matcher_does_not_suppress_guards(self):
        import tempfile
        from dw_core.migrate import run_init
        template = REPO / "template"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude").mkdir(parents=True)
            (root / ".claude" / "settings.json").write_text(json.dumps({
                "hooks": {"PreToolUse": [
                    {"matcher": "Bash|PowerShell",
                     "hooks": [{"type": "command", "command": "my-own-linter",
                                "timeout": 5}]}
                ]}}), encoding="utf-8")
            run_init(root, template, "python", "")
            settings = json.loads((root / ".claude" / "settings.json")
                                  .read_text(encoding="utf-8"))
            pre = settings["hooks"]["PreToolUse"]
            scripts = [Path(str(h["args"][-1])).name
                       for block in pre for h in block["hooks"] if h.get("args")]
            self.assertIn("guard_shell.py", scripts)
            self.assertIn("guard_write.py", scripts)
            self.assertEqual(sum(1 for s in scripts if s == "guard_shell.py"), 1)
            commands = [h["command"] for block in pre for h in block["hooks"]]
            self.assertIn("my-own-linter", commands)  # user hook preserved


class DoctorModeTests(unittest.TestCase):
    def test_plugin_mode_on_repo_checkout(self):
        from dw_core.doctor import run_doctor
        code = run_doctor(REPO, python=sys.executable, mode="plugin",
                          plugin_dir=str(REPO / "plugins" / "dw-harness"))
        self.assertEqual(code, 0)

    def test_auto_mode_detects_repo_as_plugin(self):
        from dw_core.doctor import _detect_mode
        detected = _detect_mode(REPO, "auto", "")
        self.assertIn("plugin", detected["mode"])


class SkillFrontmatterLint(unittest.TestCase):
    def test_no_comma_inside_parenthesized_rules(self):
        for skill in sorted((REPO / "src" / "skills").glob("*/SKILL.md")):
            for line in skill.read_text(encoding="utf-8").splitlines():
                if line.startswith("allowed-tools:"):
                    import re
                    for rule in re.findall(r"\w+\([^)]*\)", line):
                        self.assertNotIn(",", rule,
                                         f"{skill.name}: '{rule}' is one malformed rule")

    def test_statusline_hook_selftest_and_plain_text(self):
        script = REPO / "template" / ".claude" / "hooks" / "statusline.py"
        proc = subprocess.run([sys.executable, str(script), "--selftest"],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # statusLine prints ONE plain-text line (stdout shown verbatim)
        proc = subprocess.run([sys.executable, str(script)],
                              input=json.dumps({"model": {"display_name": "Sonnet"}}),
                              capture_output=True, text=True, timeout=30,
                              cwd=str(REPO))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.strip(), "empty statusline")
        self.assertFalse(proc.stdout.lstrip().startswith("{"), proc.stdout)


class GitBaselineTests(unittest.TestCase):
    def test_contract_diff_against_git_ref(self):
        import tempfile
        from dw_core.contracts import read_baseline
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*argv):
                return subprocess.run(["git", *argv], cwd=str(root),
                                      capture_output=True, text=True, timeout=30,
                                      check=True).stdout
            git("init", "-q")
            git("config", "user.name", "t"); git("config", "user.email", "t@t")
            (root / "contract.json").write_text(
                (REPO / "examples" / "demo" / "contract.json").read_text(encoding="utf-8"),
                encoding="utf-8")
            git("add", "contract.json"); git("commit", "-qm", "base")
            (root / "contract.json").write_text(
                (REPO / "examples" / "demo" / "contract_changed.json").read_text(encoding="utf-8"),
                encoding="utf-8")
            base, digest = read_baseline("git:HEAD:contract.json", root)
            self.assertEqual(len(digest), 64)
            from dw_core.contracts import diff_contracts, load_contract
            current, _ = load_contract(root / "contract.json")
            changes = diff_contracts(current, base)
            self.assertTrue(any(c["type"] == "unit_changed" for c in changes))


if __name__ == "__main__":
    unittest.main()
