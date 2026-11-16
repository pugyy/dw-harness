"""dw doctor: config present / scripts runnable / real-app wiring verified."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__

MIN_CLAUDE_CODE = "2.1.271"  # userConfig `options`; declared floor for plugin installs

CHECKS = [
    ("python-version", "Python >= 3.9"),
    ("config-present", "harness.json found and valid"),
    ("core-import", "dw_core importable from install location"),
    ("hook-scripts", "all hook scripts execute (--selftest)"),
    ("settings-wiring", "settings.json references existing hook scripts"),
    ("app-wiring-verified", "real Claude Code load verified (.claude/dw/wiring_verified.json)"),
]


def run_doctor(root: Path, python: str = sys.executable,
               hooks_dir: Optional[Path] = None, json_out: bool = False) -> int:
    hooks_dir = hooks_dir or (root / ".claude" / "hooks")
    results: List[Dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        results.append({"check": name, "status": "ok" if ok else "problem", "detail": detail})

    ok = sys.version_info >= (3, 9)
    add("python-version", ok, f"{sys.version.split()[0]} at {sys.executable}")

    from .config import HarnessConfig, ConfigError
    try:
        config = HarnessConfig.load(root=root)
        add("config-present", True, str(config.path or "defaults (no harness.json yet)"))
    except ConfigError as exc:
        config = None
        add("config-present", False, str(exc))

    add("core-import", True, f"dw_core {__version__} from {Path(__file__).parent}")

    hook_files = sorted(hooks_dir.glob("*.py")) if hooks_dir.is_dir() else []
    script_names = ["guard_shell.py", "guard_write.py", "validate_post.py",
                    "session_context.py", "post_compact.py", "file_changed.py", "handoff.py"]
    runnable = True
    detail_parts: List[str] = []
    for name in script_names:
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
    add("hook-scripts", runnable, "; ".join(detail_parts))

    settings_path = root / ".claude" / "settings.json"
    wiring_ok = True
    wiring_notes: List[str] = []
    if settings_path.is_file():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
            for event, entries in (settings.get("hooks") or {}).items():
                for entry in entries:
                    for hook in entry.get("hooks", []):
                        args = hook.get("args") or []
                        for arg in args:
                            if "hooks" in str(arg) and str(arg).endswith(".py"):
                                resolved = str(arg).replace("${CLAUDE_PROJECT_DIR}", str(root))
                                if not Path(resolved).is_file():
                                    wiring_ok = False
                                    wiring_notes.append(f"{event}: missing {arg}")
            wiring_notes.insert(0, f"{len(settings.get('hooks') or {})} event(s) wired")
        except json.JSONDecodeError:
            wiring_ok = False
            wiring_notes.append("settings.json not valid JSON")
    else:
        wiring_ok = False
        wiring_notes.append("no .claude/settings.json (plugin mode: wiring lives in the plugin)")
    add("settings-wiring", wiring_ok, "; ".join(wiring_notes))

    verified = (root / ".claude" / "dw" / "wiring_verified.json").is_file()
    note = f"min Claude Code {MIN_CLAUDE_CODE}"
    if verified:
        try:
            note += "; " + (root / ".claude" / "dw" / "wiring_verified.json").read_text(
                encoding="utf-8-sig").strip()
        except OSError:
            pass
    add("app-wiring-verified", verified, note)

    if json_out:
        print(json.dumps({"doctor": results, "tool_version": __version__}, indent=2))
    else:
        for r in results:
            mark = "OK " if r["status"] == "ok" else "!! "
            print(f"{mark}{r['check']}: {r['detail']}")
    return 0 if all(r["status"] == "ok" for r in results) else 1
