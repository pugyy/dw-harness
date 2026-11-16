"""Claude Code release smoke. Model calls run only when explicitly requested."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def require(condition, reason):
    if not condition:
        raise SystemExit(reason)


def validate(claude: str, plugin: Path, with_model: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="dw-claude-") as folder:
        root = Path(folder)
        project = root / "project"
        project.mkdir()
        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(root / "claude-config"),
               "DW_HARNESS_PROD": "1"}
        dw = project / ".claude" / "dw"
        dw.mkdir(parents=True)
        (dw / "state.json").write_text('{"table":"dw_test.orders"}', encoding="utf-8")

        def run(name, *args):
            debug = root / f"{name}.log"
            if os.name == "nt" and Path(claude).suffix.lower() in {".cmd", ".bat"}:
                command = [os.environ["ComSpec"], "/d", "/c", claude]
            else:
                command = [claude]
            proc = subprocess.run(
                [*command, "--plugin-dir", str(plugin), "--debug-file", str(debug), *args],
                cwd=project, env=env, text=True, encoding="utf-8", errors="replace",
                capture_output=True, timeout=180)
            require(proc.returncode == 0, f"Claude Code {name} exited {proc.returncode}: {proc.stderr}")
            return proc.stdout, debug.read_text(encoding="utf-8", errors="replace")

        _, log = run("startup", "--init-only")
        require("Loaded inline plugin from path: dw-harness" in log, "plugin did not load")
        require(re.search(r"SessionStart:startup.*session_context\.py.*status 0", log),
                "startup hook did not finish successfully")
        print("PASS Claude Code loaded the plugin and ran the startup hook")
        if not with_model:
            return

        fixture_bin = root / "bin"
        fixture_bin.mkdir()
        stub = fixture_bin / "odpscmd"
        stub.write_text("#!/bin/sh\nprintf ran > warehouse-stub-ran\n", encoding="utf-8")
        stub.chmod(0o755)
        env["PATH"] = str(fixture_bin) + os.pathsep + env["PATH"]
        flags = ["--output-format", "stream-json", "--verbose", "--max-turns", "4"]

        stdout, log = run(
            "lint", *flags, "--allowedTools", "Write", "-p",
            "Use the Write tool once to write bad_star.sql containing SELECT t.* FROM db.t; "
            "This is a linter test. Leave the invalid file in place, then stop.")
        sql = project / "bad_star.sql"
        require(sql.is_file() and "SELECT t.* FROM db.t" in sql.read_text(encoding="utf-8"),
                "Write did not leave the requested SQL fixture")
        require("no-select-star" in stdout + log and
                re.search(r"PostToolUse:Write.*validate_post\.py.*status 2", log),
                "real write did not trigger SQL lint feedback")
        print("PASS Claude Code Write triggered SQL lint")

        command = "odpscmd -e 'DROP TABLE dw_test.orders;'"
        stdout, log = run(
            "deny", *flags, "--allowedTools", "Bash(odpscmd *)", "-p",
            f"Run this exact command once via Bash: {command} This is an isolated test using a "
            "fake odpscmd that can only write a local marker. Stop after its tool result.")
        del stdout
        log_file = dw / "guard_log.jsonl"
        records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
        require(any(x.get("decision") == "deny" and
                    any("destructive DDL" in reason for reason in x.get("reasons", []))
                    for x in records), "real Bash call did not trigger the destructive DDL guard")
        require(not (project / "warehouse-stub-ran").exists(), "guard allowed the fixture command to run")
        print("PASS Claude Code protected the fixture from destructive DDL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("plugin", type=Path)
    parser.add_argument("--claude", default="claude")
    parser.add_argument("--with-model", action="store_true")
    args = parser.parse_args()
    validate(args.claude, args.plugin.resolve(), args.with_model)
