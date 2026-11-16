#!/usr/bin/env python3
"""Deterministic build: src/ -> plugins/dw-harness + template/ + marketplace.

Both distribution forms are generated artifacts; `build --check` (CI) fails
on drift so the two can never silently diverge from the single source.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
PLUGIN = REPO / "plugins" / "dw-harness"
TEMPLATE = REPO / "template"
MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"

SKIP_COPY = {"__pycache__", "*.pyc", ".DS_Store"}


def version() -> str:
    for line in (SRC / "dw_core" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("cannot read dw_core.__version__")


def hook_config() -> Dict:
    return json.loads((SRC / "hooks.config.json").read_text(encoding="utf-8"))


def copy_tree(src: Path, dst: Path) -> None:
    if not src.is_dir():
        return
    for item in sorted(src.rglob("*")):
        if any(part == "__pycache__" for part in item.parts):
            continue
        if item.suffix == ".pyc":
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target)


def plugin_hook_entry(event: str, block: Dict) -> Dict:
    hook = {"type": "command",
            "command": "${user_config.python}",
            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/" + block["script"]],
            "timeout": block.get("timeout", 30)}
    if "onFailure" in block:
        hook["onFailure"] = block["onFailure"]
    entry = {"matcher": block["matcher"]} if block.get("matcher") else {}
    entry["hooks"] = [hook]
    return entry


def template_hook_entry(block: Dict) -> Dict:
    hook = {"type": "command",
            "command": "python",
            "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/" + block["script"]],
            "timeout": block.get("timeout", 30)}
    if "onFailure" in block:
        hook["onFailure"] = block["onFailure"]
    entry = {"matcher": block["matcher"]} if block.get("matcher") else {}
    entry["hooks"] = [hook]
    return entry


def write_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


PLUGIN_README = """# dw-harness plugin

Install-time options (userConfig):
- `python`: interpreter used by hook scripts (default `python`; use `py -3`
  or an absolute path on Windows as needed)
- `dialect`: default SQL dialect (odps / hive / spark / starrocks)

Hooks: PreToolUse guards (fail-closed), PostToolUse SQL write-after feedback,
SessionStart state card, PostCompact local capture, FileChanged out-of-band
check, SessionEnd handoff. Skills: the 8-step workflow plus bootstrap /
contract / check / next / review / backfill and an auto-loaded SQL reference.
Agents: dw-explorer, sql-validator, data-quality-checker, data-comparator
(model: inherit; plugin agents ignore permissionMode by design).

Project-side files (AGENTS.md, rules, harness.json, contracts) are generated
by the `dw-bootstrap` skill / `dw init` — they are intentionally NOT shipped
by the plugin. Requires Claude Code >= 2.1.271 (userConfig options).
"""


def build(target_root: Path) -> List[str]:
    """Generate everything under target_root (REPO for real, temp for check)."""
    actions: List[str] = []
    ver = version()
    cfg = hook_config()

    plugin = target_root / "plugins" / "dw-harness"
    if plugin.exists():
        shutil.rmtree(plugin)
    (plugin / ".claude-plugin").mkdir(parents=True)
    write_json(plugin / ".claude-plugin" / "plugin.json", {
        "name": "dw-harness",
        "version": ver,
        "description": "Data warehouse AI engineering layer: guards, contracts, "
                       "reconciliation and the 8-step workflow for MaxCompute -> StarRocks.",
        "author": {"name": "pugyy"},
        "userConfig": {
            "python": {
                "type": "string",
                "title": "Python interpreter",
                "description": "python / python3 / py -3 or an absolute path",
                "default": "python",
            },
            "dialect": {
                "type": "string",
                "title": "Default SQL dialect",
                "options": [
                    {"value": "odps", "label": "ODPS / MaxCompute"},
                    {"value": "hive", "label": "Hive"},
                    {"value": "spark", "label": "Spark"},
                    {"value": "starrocks", "label": "StarRocks"},
                ],
                "default": "odps",
            },
        },
    })
    hooks_json = {event: [plugin_hook_entry(event, b) for b in blocks]
                  for event, blocks in cfg["hooks"].items()}
    write_json(plugin / "hooks" / "hooks.json", {"hooks": hooks_json})
    copy_tree(SRC / "hooks", plugin / "hooks")
    copy_tree(SRC / "dw_core", plugin / "dw_core")
    copy_tree(SRC / "skills", plugin / "skills")
    copy_tree(SRC / "agents", plugin / "agents")
    copy_tree(SRC / "dialects", plugin / "dialects")
    copy_tree(SRC / "output-styles", plugin / "output-styles")
    copy_tree(REPO / "mcp", plugin / "mcp")
    (plugin / "README.md").write_text(PLUGIN_README, encoding="utf-8")
    actions.append("plugins/dw-harness rebuilt")

    template = target_root / "template"
    if template.exists():
        shutil.rmtree(template)
    settings = {"hooks": {event: [template_hook_entry(b) for b in blocks]
                          for event, blocks in cfg["hooks"].items()}}
    write_json(template / ".claude" / "settings.json", settings)
    copy_tree(SRC / "hooks", template / ".claude" / "hooks")
    copy_tree(SRC / "dw_core", template / ".claude" / "dw_core")
    copy_tree(SRC / "skills", template / ".claude" / "skills")
    copy_tree(SRC / "agents", template / ".claude" / "agents")
    copy_tree(SRC / "dialects", template / ".claude" / "dialects")
    copy_tree(SRC / "output-styles", template / ".claude" / "output-styles")
    scaffold = SRC / "scaffold"
    shutil.copyfile(scaffold / "CLAUDE.md", template / "CLAUDE.md")
    shutil.copyfile(scaffold / "AGENTS.md", template / "AGENTS.md")
    copy_tree(scaffold / "rules", template / ".claude" / "rules")
    (template / ".claude" / "dw").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(scaffold / "harness.json", template / ".claude" / "dw" / "harness.json")
    shutil.copyfile(scaffold / "state.json", template / ".claude" / "dw" / "state.json")
    shutil.copyfile(scaffold / "policy_exceptions.json",
                    template / ".claude" / "dw" / "policy_exceptions.json")
    (template / ".claude" / "dw" / "mcp").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / "mcp" / "server.py",
                    template / ".claude" / "dw" / "mcp" / "server.py")
    (template / "contracts").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(scaffold / "contract.example.json",
                    template / "contracts" / "contract.example.json")
    actions.append("template/ rebuilt (copy-mode install, original command names)")

    write_json(target_root / ".claude-plugin" / "marketplace.json", {
        "name": "dw-harness",
        "owner": "pugyy",
        "plugins": [{
            "name": "dw-harness",
            "source": "./plugins/dw-harness",
            "description": "Data warehouse AI engineering layer (guards, contracts, "
                           "reconciliation, 8-step workflow)",
            "version": ver,
            "category": "data",
        }],
    })
    actions.append("marketplace.json written")
    return actions


def trees_equal(a: Path, b: Path) -> List[str]:
    diffs: List[str] = []

    def files(root: Path):
        return {p.relative_to(root).as_posix(): p for p in root.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}

    sa, sb = files(a), files(b)
    for key in sorted(set(sa) | set(sb)):
        if key not in sa:
            diffs.append(f"extra in build: {key}")
        elif key not in sb:
            diffs.append(f"missing from build: {key}")
        elif sa[key].read_bytes() != sb[key].read_bytes():
            diffs.append(f"content drift: {key}")
    return diffs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="build")
    parser.add_argument("--check", action="store_true",
                        help="verify committed artifacts match src/ (CI drift gate)")
    args = parser.parse_args(argv)
    if not args.check:
        for action in build(REPO):
            print(action)
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        expected = Path(tmp)
        build(expected)
        diffs: List[str] = []
        for generated in ("plugins", "template", ".claude-plugin"):
            live = REPO / generated
            want = expected / generated
            if not live.exists():
                diffs.append(f"missing artifact dir: {generated}/")
                continue
            diffs.extend(trees_equal(want, live))
    if diffs:
        print("BUILD DRIFT DETECTED — regenerate with `python scripts/build.py`:")
        for d in diffs[:40]:
            print("  " + d)
        return 1
    print("build --check: clean (plugins/, template/, marketplace match src/)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
