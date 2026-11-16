"""Manifest / migration / drift tests: plugin.json, marketplace.json, skill
frontmatter sanity, v1->v2 merge idempotence (spec 20f, 21)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

V1_SETTINGS = {
    "statusLine": {"type": "command", "command": "echo v1"},
    "permissions": {"allow": ["Bash(git diff:*)"]},
    "hooks": {
        "PostToolUse": [{"matcher": "Write|Edit|MultiEdit",
                         "hooks": [{"type": "command",
                                    "command": "python .claude/hooks/validate_sql.py",
                                    "timeout": 60}]}],
        "PreToolUse": [{"matcher": "Bash",
                        "hooks": [{"type": "command",
                                   "command": "python .claude/hooks/block_dangerous_ddl.py",
                                   "timeout": 10}]}],
        "SessionStart": [{"matcher": "compact",
                          "hooks": [{"type": "command",
                                     "command": "python .claude/hooks/inject_context.py",
                                     "timeout": 10}]}],
    },
}


class ManifestTests(unittest.TestCase):
    def test_plugin_manifest(self):
        path = REPO / "plugins" / "dw-harness" / ".claude-plugin" / "plugin.json"
        if not path.is_file():
            self.skipTest("plugin not built")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "dw-harness")
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertIn("python", manifest["userConfig"])
        self.assertTrue(manifest["userConfig"]["dialect"]["options"])
        for option in manifest["userConfig"]["dialect"]["options"]:
            self.assertTrue({"value", "label"} <= set(option), option)

    def test_marketplace(self):
        path = REPO / ".claude-plugin" / "marketplace.json"
        if not path.is_file():
            self.skipTest("marketplace not built")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["plugins"][0]["source"], "./plugins/dw-harness")
        # official schema: owner is an object, not a bare string (audit P0-5)
        self.assertIsInstance(data.get("owner"), dict, data.get("owner"))
        self.assertIn("name", data["owner"])
        self.assertTrue((REPO / "plugins" / "dw-harness" / ".claude-plugin" / "plugin.json").is_file())

    def test_statusline_settings_schema(self):
        """--statusline must write the official statusLine shape (audit R3):
        one shell `command` string, NO args field."""
        from dw_core.migrate import run_init
        template = REPO / "template"
        if not (template / ".claude" / "dw").is_dir():
            self.skipTest("template not built")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude").mkdir(parents=True)
            (root / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
            run_init(root, template, r"C:\Py39\python.exe", "", statusline=True)
            settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
            status = settings["statusLine"]
            self.assertEqual(status["type"], "command")
            self.assertNotIn("args", status)
            self.assertIn("statusline.py", status["command"])
            self.assertIn(r"C:\Py39\python.exe", status["command"])

    def test_skill_frontmatter_names_match_dirs(self):
        skills = REPO / "src" / "skills"
        expected = {"dw-requirement-analysis", "dw-technical-design", "dw-etl",
                    "dw-self-test", "dw-data-comparison", "dw-sr",
                    "dw-performance-optimization", "dw-dqc", "dw-bootstrap",
                    "dw-contract", "dw-check", "dw-next", "dw-review",
                    "dw-backfill", "dw-sql-reference"}
        found = {p.name for p in skills.iterdir() if p.is_dir()}
        self.assertEqual(found, expected)
        for skill_dir in sorted(skills.iterdir()):
            text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            m = re.search(r"^name:\s*(\S+)", text, re.M)
            self.assertTrue(m, skill_dir)
            self.assertEqual(m.group(1), skill_dir.name)
            self.assertNotIn("直接调用命令", text)

    def test_agents_flat_and_no_permission_mode(self):
        agents = REPO / "src" / "agents"
        files = sorted(p.name for p in agents.glob("*.md"))
        self.assertEqual(files, ["data-comparator.md", "data-quality-checker.md",
                                 "dw-explorer.md", "sql-validator.md"])
        for path in agents.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("permissionMode", text)
            self.assertIn("model: inherit", text)

    def test_build_check_clean(self):
        proc = subprocess.run([sys.executable, str(REPO / "scripts" / "build.py"), "--check"],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_doc_test_counts_match_reality(self):
        """Anti-drift: every '<N> 个测试 / <N> tests' in README/CHANGELOG must
        equal the actual number of collected test methods (audit P2)."""
        import re as _re
        actual = 0
        for path in sorted((REPO / "tests").glob("test_*.py")):
            actual += len(_re.findall(r"^\s*def test_", path.read_text(encoding="utf-8"), _re.M))
        pattern = _re.compile(r"(\d+)\s*(?:个测试|个测试全绿|tests\b)")
        for doc in (REPO / "README.md", REPO / "CHANGELOG.md"):
            text = doc.read_text(encoding="utf-8")
            found = [int(m.group(1)) for m in pattern.finditer(text)]
            self.assertTrue(found, f"{doc.name}: no test-count claims found")
            for number in found:
                self.assertEqual(number, actual,
                                 f"{doc.name} claims {number} tests, reality is {actual}")


class MigrationTests(unittest.TestCase):
    def _v1_project(self, root: Path):
        (root / ".claude" / "skills" / "my-custom-skill").mkdir(parents=True)
        (root / ".claude" / "skills" / "my-custom-skill" / "SKILL.md").write_text(
            "---\nname: my-custom-skill\ndescription: mine\n---\nmine\n", encoding="utf-8")
        (root / ".claude" / "rules").mkdir(parents=True)
        (root / ".claude" / "rules" / "my-team.md").write_text("my rule\n", encoding="utf-8")
        (root / ".claude" / "hooks").mkdir(parents=True)
        (root / ".claude" / "hooks" / "validate_sql.py").write_text("print('v1')\n", encoding="utf-8")
        (root / "CLAUDE.md").write_text("# 当前迭代状态\n\n- 表：db.t\n", encoding="utf-8")
        (root / ".claude" / "settings.json").write_text(json.dumps(V1_SETTINGS, indent=2),
                                                        encoding="utf-8")

    def test_migration_idempotent_and_preserves_user_content(self):
        template = REPO / "template"
        if not (template / ".claude" / "dw").is_dir():
            self.skipTest("template not built")
        from dw_core.migrate import run_init
        v1_hashes = json.loads((REPO / "src" / "scaffold" / "v1_hashes.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._v1_project(root)
            first = run_init(root, template, "python", "odps")
            second = run_init(root, template, "python", "odps")
            settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
            raw = json.dumps(settings)
            for v1_cmd in ("python .claude/hooks/validate_sql.py",
                           "python .claude/hooks/block_dangerous_ddl.py",
                           "python .claude/hooks/inject_context.py"):
                self.assertNotIn(v1_cmd, raw)
            self.assertEqual(raw.count("guard_shell.py"), 1)
            self.assertEqual(raw.count("validate_post.py"), 1)
            self.assertIn("statusLine", settings)          # user statusbar kept
            self.assertIn("permissions", settings)         # user permissions kept
            self.assertTrue((root / ".claude" / "skills" / "my-custom-skill" / "SKILL.md").is_file())
            self.assertTrue((root / ".claude" / "rules" / "my-team.md").is_file())
            self.assertTrue((root / "AGENTS.md").is_file())
            self.assertIn("@AGENTS.md", (root / "CLAUDE.md").read_text(encoding="utf-8"))
            self.assertFalse(second.conflicts, second.conflicts)
            self.assertTrue((root / ".claude" / "hooks" / "guard_shell.py").is_file())
            self.assertTrue((root / ".claude" / "dw_core" / "guard.py").is_file())

    def test_dry_run_writes_nothing(self):
        template = REPO / "template"
        if not (template / ".claude" / "dw").is_dir():
            self.skipTest("template not built")
        from dw_core.migrate import run_init
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._v1_project(root)
            before = (root / ".claude" / "settings.json").read_text(encoding="utf-8")
            report = run_init(root, template, "python", "odps", dry_run=True)
            self.assertEqual((root / ".claude" / "settings.json").read_text(encoding="utf-8"), before)
            self.assertFalse((root / "AGENTS.md").exists())
            self.assertTrue(report.actions)


if __name__ == "__main__":
    unittest.main()
