"""dw doctor: config present / scripts runnable / real-app wiring verified.

Distinguishes install modes: plugin (hooks live under the plugin root) vs
template (hooks live under <project>/.claude/hooks). Exit code counts only
critical checks; app-wiring is informational unless --strict.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__

# userConfig `options` needs 2.1.271; hook `onFailure` needs 2.1.295 — we use
# both, so the honest floor is the higher one.
MIN_CLAUDE_CODE = "2.1.295"

SCRIPT_NAMES = ["guard_shell.py", "guard_write.py", "validate_post.py",
                "session_context.py", "post_compact.py", "handoff.py",
                "statusline.py"]


def _version_tuple(text: str) -> tuple:
    return tuple(int(p) for p in re.findall(r"\d+", text)[:3])


def _detect_mode(root: Path, mode: str, plugin_dir: str) -> Dict:
    if mode == "plugin":
        for candidate in ([plugin_dir] if plugin_dir else []) + [
                os.environ.get("CLAUDE_PLUGIN_ROOT", ""),
                str(root / "plugins" / "dw-harness")]:
            if candidate and (Path(candidate) / "hooks").is_dir():
                return {"mode": "plugin", "hooks_dir": Path(candidate) / "hooks"}
        return {"mode": "plugin", "hooks_dir": root / ".claude" / "hooks"}
    if mode == "template":
        return {"mode": "template", "hooks_dir": root / ".claude" / "hooks"}
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root and (Path(plugin_root) / "hooks").is_dir():
        return {"mode": "plugin", "hooks_dir": Path(plugin_root) / "hooks"}
    if (root / ".claude" / "settings.json").is_file() or (root / ".claude" / "hooks").is_dir():
        return {"mode": "template", "hooks_dir": root / ".claude" / "hooks"}
    repo_plugin = root / "plugins" / "dw-harness" / "hooks"
    if repo_plugin.is_dir():
        return {"mode": "plugin (repo checkout)", "hooks_dir": repo_plugin}
    return {"mode": "template", "hooks_dir": root / ".claude" / "hooks"}


def run_doctor(root: Path, python: str = sys.executable, hooks_dir: Optional[Path] = None,
               json_out: bool = False, mode: str = "auto", plugin_dir: str = "",
               strict: bool = False) -> int:
    detected = _detect_mode(root, mode, plugin_dir)
    hooks_dir = hooks_dir or detected["hooks_dir"]
    results: List[Dict] = []

    def add(name: str, ok: bool, detail: str, critical: bool = True) -> None:
        results.append({"check": name, "status": "ok" if ok else "problem",
                        "detail": detail, "critical": critical})

    add("python-version", sys.version_info >= (3, 9), f"{sys.version.split()[0]} at {sys.executable}")

    from .config import HarnessConfig, ConfigError
    try:
        config = HarnessConfig.load(root=root)
        add("config-present", True, str(config.path or "defaults (no harness.json yet)"))
    except ConfigError as exc:
        config = None
        add("config-present", False, str(exc))

    add("core-import", True, f"dw_core {__version__} from {Path(__file__).parent}", critical=False)

    runnable = True
    detail_parts: List[str] = []
    for name in SCRIPT_NAMES:
        path = hooks_dir / name
        if not path.is_file():
            runnable = False
            detail_parts.append(f"{name}: MISSING")
            continue
        proc = subprocess.run([python, str(path), "--selftest"],
                              capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            runnable = False
            detail_parts.append(f"{name}: exit {proc.returncode} {proc.stderr.strip()[:80]}")
        else:
            detail_parts.append(f"{name}: ok")
    add("hook-scripts", runnable,
        f"[{detected['mode']}] " + "; ".join(detail_parts))

    wiring_ok = True
    wiring_notes: List[str] = [f"mode: {detected['mode']}"]
    if "plugin" in detected["mode"]:
        hooks_json = hooks_dir / "hooks.json"
        if hooks_json.is_file():
            try:
                data = json.loads(hooks_json.read_text(encoding="utf-8-sig"))
                count = 0
                for event, entries in (data.get("hooks") or {}).items():
                    for entry in entries:
                        for hook in entry.get("hooks", []):
                            for arg in hook.get("args") or []:
                                if str(arg).endswith(".py"):
                                    resolved = str(arg).replace(
                                        "${CLAUDE_PLUGIN_ROOT}",
                                        str(hooks_json.parents[1]))
                                    if not Path(resolved).is_file():
                                        wiring_ok = False
                                        wiring_notes.append(f"{event}: missing {arg}")
                                    count += 1
                wiring_notes.append(f"{count} plugin hook path(s) resolve")
            except json.JSONDecodeError:
                wiring_ok = False
                wiring_notes.append("plugin hooks.json not valid JSON")
        else:
            wiring_ok = False
            wiring_notes.append("plugin hooks.json not found next to hooks dir")
    else:
        settings_path = root / ".claude" / "settings.json"
        if settings_path.is_file():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
                for event, entries in (settings.get("hooks") or {}).items():
                    for entry in entries:
                        for hook in entry.get("hooks", []):
                            for arg in hook.get("args") or []:
                                if "hooks" in str(arg) and str(arg).endswith(".py"):
                                    resolved = str(arg).replace("${CLAUDE_PROJECT_DIR}", str(root))
                                    if not Path(resolved).is_file():
                                        wiring_ok = False
                                        wiring_notes.append(f"{event}: missing {arg}")
                wiring_notes.insert(1, f"{len(settings.get('hooks') or {})} event(s) wired")
            except json.JSONDecodeError:
                wiring_ok = False
                wiring_notes.append("settings.json not valid JSON")
        else:
            wiring_ok = False
            wiring_notes.append("no .claude/settings.json in template mode")
    add("settings-wiring", wiring_ok, "; ".join(wiring_notes))

    # live claude --version check when the CLI is present
    claude_ok: Optional[bool] = None
    claude_note = f"min Claude Code {MIN_CLAUDE_CODE}"
    try:
        proc = subprocess.run(["claude", "--version"], capture_output=True,
                              text=True, timeout=15)
        version_text = (proc.stdout or proc.stderr).strip()
        if proc.returncode == 0 and version_text:
            if _version_tuple(version_text) >= _version_tuple(MIN_CLAUDE_CODE):
                claude_ok = True
                claude_note = f"claude {version_text} >= {MIN_CLAUDE_CODE}"
            else:
                claude_ok = False
                claude_note = f"claude {version_text} < required {MIN_CLAUDE_CODE}"
    except (OSError, subprocess.SubprocessError):
        claude_note += "; claude CLI not on PATH (checked only when installed)"
    add("claude-version", True if claude_ok is None else claude_ok, claude_note,
        critical=False)

    verified = (root / ".claude" / "dw" / "wiring_verified.json").is_file()
    note = "run the real-app steps in docs/e2e-demo.md, then write " \
           ".claude/dw/wiring_verified.json"
    if verified:
        try:
            note = (root / ".claude" / "dw" / "wiring_verified.json").read_text(
                encoding="utf-8-sig").strip()
        except OSError:
            pass
    add("app-wiring-verified", verified, note, critical=strict)

    if json_out:
        print(json.dumps({"doctor": results, "tool_version": __version__,
                          "mode": detected["mode"]}, indent=2))
    else:
        for r in results:
            mark = "OK " if r["status"] == "ok" else ("!! " if r["critical"] else "!  ")
            print(f"{mark}{r['check']}: {r['detail']}")
    critical_failures = [r for r in results if r["status"] != "ok" and r["critical"]]
    return 1 if critical_failures else 0
