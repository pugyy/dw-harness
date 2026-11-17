"""Regression cases that exercise installed artifacts and release boundaries."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from .test_e2e_cli import REPO, run_cli


class ReleasePathsTests(unittest.TestCase):
    def test_bundled_shell_hook_honors_prod_and_actual_cwd(self):
        hook = REPO / "plugins/dw-harness/hooks/guard_shell.py"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "sql dir"
            work.mkdir()
            (work / "migration.sql").write_text("DROP TABLE db.t;", encoding="utf-8")
            env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "DW_HARNESS_PROD": "1"}
            for command, tool in [
                ('odpscmd -e "INSERT OVERWRITE TABLE db.t PARTITION (partition_dt=\'20260401\') SELECT 1"',
                 "Bash"),
                ('cd "." && odpscmd --file="migration.sql"', "Bash"),
                ('& "C:\\\\Program Files\\\\MaxCompute\\\\odpscmd.exe" -e "DROP TABLE db.t;"', "PowerShell"),
                ('odpscmd -e "UPDATE db.t SET amount = (SELECT x FROM s WHERE id=1)"', "Bash"),
            ]:
                with self.subTest(command=command):
                    proc = subprocess.run([sys.executable, str(hook)], cwd=root, env=env, text=True,
                                          capture_output=True, timeout=15, input=json.dumps({
                                              "cwd": str(work), "tool_name": tool,
                                              "tool_input": {"command": command}}))
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"],
                                     "deny")

    def test_installed_mcp_registration_and_project_boundary(self):
        from dw_core.migrate import run_init
        from dw_core.mcp_selftest import mcp_selftest
        import runpy
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            preview = run_init(project, REPO / "template", sys.executable, "", dry_run=True, mcp=True)
            self.assertFalse(preview.conflicts)
            self.assertFalse(project.exists())
            report = run_init(project, REPO / "template", sys.executable, "", mcp=True, mode="plugin")
            self.assertFalse(report.conflicts)
            self.assertFalse((project / ".claude/hooks/guard_shell.py").exists())
            self.assertTrue(mcp_selftest(root=project))
            script = project / ".claude/dw/mcp/server.py"
            mcp = runpy.run_path(str(script))
            outside = root / "outside.json"
            outside.write_text('{"schema":"dw-check/1"}', encoding="utf-8")
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(project)}):
                with self.assertRaisesRegex(ValueError, "outside the project"):
                    mcp["_tool_get_check_report"]({"path": str(outside)})
                with self.assertRaisesRegex(ValueError, "outside the project"):
                    mcp["_project_path"](project, Path("../outside.json"))
                local = project / ".claude/dw/check_report.json"
                local.write_bytes(outside.read_bytes())
                self.assertEqual(mcp["_tool_get_check_report"]({})["schema"], "dw-check/1")

    def test_init_without_template_core_copies_installed_core(self):
        import shutil
        from dw_core.migrate import run_init
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "template"
            shutil.copytree(REPO / "template", template,
                            ignore=shutil.ignore_patterns("dw_core"))
            self.assertFalse((template / ".claude" / "dw_core").exists())
            project = root / "project"
            report = run_init(project, template, sys.executable, "")
            self.assertFalse(report.conflicts)
            self.assertTrue((project / ".claude/dw_core/__init__.py").is_file())
            self.assertTrue((project / ".claude/dw_core/data/dialects/odps.json").is_file())

    def test_changeset_checks_second_table_against_git_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contracts = root / "contracts"
            contracts.mkdir()
            sample = (REPO / "examples/demo/contract.json").read_text(encoding="utf-8")
            changed = (REPO / "examples/demo/contract_changed.json").read_text(encoding="utf-8")

            def git(*args):
                subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)

            git("init", "-q")
            git("config", "user.name", "dw")
            git("config", "user.email", "dw@example.test")
            a, b = contracts / "first table.json", contracts / "second table.json"
            for path, name in ((a, "db_a.first"), (b, "db_a.second")):
                path.write_text(sample.replace("db_a.dws_trade_order_di", name), encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "baseline")
            a.write_text(a.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            b.write_text(changed.replace("db_a.dws_trade_order_di", "db_a.second"), encoding="utf-8")
            proc = run_cli(["check", "--changed", "--base-ref", "HEAD", "--out-json", "report.json"], root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
            tables = {item["table"]: item for item in report["reports"]}
            self.assertEqual(set(tables), {"db_a.first", "db_a.second"})
            self.assertIn({"contract-diff": "fail"}, [
                {i["name"]: i["status"]} for i in tables["db_a.second"]["items"]])

    def test_maxcompute_dbapi_binds_partition_and_limit(self):
        from dw_core.reconcile import MaxComputeAdapter
        dbapi = Mock()
        cursor = dbapi.connect.return_value.cursor.return_value
        cursor.fetchmany.return_value = [("A001", 123), ("A002", 456)]
        adapter = MaxComputeAdapter({"table": "proj.t", "partition": "20261115"},
                                    ["id"], ["amount"])
        with patch.dict(sys.modules, {"odps": SimpleNamespace(dbapi=dbapi)}), patch.object(
                adapter, "_connect") as odps:
            rows, truncated = adapter.fetch(1)
        self.assertEqual(rows, [{"id": "A001", "amount": 123}])
        self.assertTrue(truncated)
        self.assertEqual(cursor.execute.call_args.args[1], ("20261115", 2))
        self.assertIn("= ? LIMIT ?", cursor.execute.call_args.args[0])
        self.assertIn(chr(96) + "proj" + chr(96) + "." + chr(96) + "t" + chr(96),
                      cursor.execute.call_args.args[0])
        dbapi.connect.assert_called_once_with(odps.return_value)
