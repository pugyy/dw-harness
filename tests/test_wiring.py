"""Wiring tests: execute the REAL hook scripts from the generated configs,
asserting the Claude Code JSON contract on actual payloads (spec item 21)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN_HOOKS = REPO / "plugins" / "dw-harness" / "hooks"
TEMPLATE_HOOKS = REPO / "template" / ".claude" / "hooks"


def _run(hook_dir: Path, script: str, payload: dict):
    proc = subprocess.run([sys.executable, str(hook_dir / script)],
                          input=json.dumps(payload), capture_output=True,
                          text=True, timeout=60, cwd=str(REPO))
    return proc


def _json_out(proc) -> dict:
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    return json.loads(lines[-1]) if lines else {}


@unittest.skipUnless(PLUGIN_HOOKS.is_dir(), "plugin not built yet")
class PluginWiringTests(unittest.TestCase):
    def test_hooks_json_schema(self):
        config = json.loads((PLUGIN_HOOKS / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("hooks", config)
        events = config["hooks"]
        self.assertIn("PreToolUse", events)
        for block in events["PreToolUse"]:
            for hook in block["hooks"]:
                self.assertEqual(hook["type"], "command")
                self.assertEqual(hook["command"], "${user_config.python}")
                self.assertTrue(hook["args"][0].startswith("${CLAUDE_PLUGIN_ROOT}/hooks/"))
                script = hook["args"][0].split("/")[-1]
                self.assertTrue((PLUGIN_HOOKS / script).is_file(), script)
        # policy hooks are fail-closed
        pre = json.dumps(events["PreToolUse"])
        self.assertIn('"onFailure": "block"', pre)

    def test_guard_shell_deny(self):
        proc = _run(PLUGIN_HOOKS, "guard_shell.py", {
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "odpscmd -e 'DROP TABLE db.t'"}})
        out = _json_out(proc)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_guard_shell_allows_benign(self):
        proc = _run(PLUGIN_HOOKS, "guard_shell.py", {
            "tool_name": "Bash", "tool_input": {"command": "ls -la"}})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_guard_shell_ignores_non_shell_tool(self):
        proc = _run(PLUGIN_HOOKS, "guard_shell.py", {
            "tool_name": "Write", "tool_input": {"command": "irrelevant"}})
        self.assertEqual(proc.stdout.strip(), "")

    def test_session_start_contract(self):
        proc = _run(PLUGIN_HOOKS, "session_context.py", {
            "hook_event_name": "SessionStart", "source": "compact"})
        out = _json_out(proc)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("dw-harness", out["hookSpecificOutput"]["additionalContext"])

    def test_post_compact_writes_local_state_only(self):
        proc = _run(PLUGIN_HOOKS, "post_compact.py", {
            "hook_event_name": "PostCompact", "trigger": "manual",
            "compact_summary": "abc"})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")  # no injection on PostCompact

    def test_validate_post_exit2_on_bad_sql(self):
        bad = REPO / "examples" / "demo" / "bad_select_t_star.sql"
        proc = _run(PLUGIN_HOOKS, "validate_post.py", {
            "hook_event_name": "PostToolUse", "tool_name": "Write",
            "tool_input": {"file_path": str(bad)}})
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no-select-star", proc.stderr)

    def test_validate_post_ok_sql(self):
        good = REPO / "examples" / "demo" / "insert_orders.sql"
        proc = _run(PLUGIN_HOOKS, "validate_post.py", {
            "tool_name": "Write", "tool_input": {"file_path": str(good)}})
        self.assertEqual(proc.returncode, 0)

    def test_validate_post_ignores_non_sql(self):
        proc = _run(PLUGIN_HOOKS, "validate_post.py", {
            "tool_name": "Write", "tool_input": {"file_path": "src/readme.txt"}})
        self.assertEqual(proc.returncode, 0)

    def test_selftest(self):
        for script in ("guard_shell.py", "guard_write.py", "validate_post.py",
                       "session_context.py", "post_compact.py", "file_changed.py",
                       "handoff.py"):
            proc = subprocess.run([sys.executable, str(PLUGIN_HOOKS / script), "--selftest"],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, script)
            self.assertIn("ok", proc.stdout)


@unittest.skipUnless(TEMPLATE_HOOKS.is_dir(), "template not built yet")
class TemplateWiringTests(unittest.TestCase):
    def test_settings_json_paths(self):
        settings = json.loads((REPO / "template" / ".claude" / "settings.json").read_text(encoding="utf-8"))
        for event, blocks in settings["hooks"].items():
            for block in blocks:
                for hook in block["hooks"]:
                    rel = hook["args"][0].replace("${CLAUDE_PROJECT_DIR}", str(REPO / "template"))
                    self.assertTrue(Path(rel).is_file(), rel)
        raw = json.dumps(settings)
        self.assertNotIn("MultiEdit", raw)
        self.assertIn("PowerShell", raw)

    def test_guard_shell_runs_from_template(self):
        proc = _run(TEMPLATE_HOOKS, "guard_shell.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "odpscmd -e 'TRUNCATE TABLE db.t'"}})
        out = _json_out(proc)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
