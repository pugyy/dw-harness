"""dw init: merge-style migration from v1 (and fresh installs).

Managed files are tracked in .claude/dw/managed.json with content hashes.
Only unmodified managed files (or files matching the bundled v1 hashes) get
replaced; user-modified files are reported as conflicts and left untouched.
Re-running never duplicates hook entries.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

V1_HOOK_COMMANDS = [
    "python .claude/hooks/validate_sql.py",
    "python .claude/hooks/block_dangerous_ddl.py",
    "python .claude/hooks/inject_context.py",
]

V2_TEMPLATE_HOOKS = {
    "PreToolUse": [
        {"matcher": "Bash|PowerShell",
         "hooks": [{"type": "command", "command": "${python}", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/guard_shell.py"], "timeout": 20, "onFailure": "block"}]},
        {"matcher": "Write|Edit",
         "hooks": [{"type": "command", "command": "${python}", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/guard_write.py"], "timeout": 20, "onFailure": "block"}]},
    ],
    "PostToolUse": [
        {"matcher": "Write|Edit",
         "hooks": [{"type": "command", "command": "${python}", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/validate_post.py"], "timeout": 60}]},
    ],
    "SessionStart": [
        {"matcher": "startup|resume|clear|compact",
         "hooks": [{"type": "command", "command": "${python}", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/session_context.py"], "timeout": 10}]},
    ],
    "PostCompact": [
        {"matcher": "manual|auto",
         "hooks": [{"type": "command", "command": "${python}", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/post_compact.py"], "timeout": 10}]},
    ],
    "FileChanged": [
        {"matcher": "**/*.sql",
         "hooks": [{"type": "command", "command": "${python}", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/file_changed.py"], "timeout": 30}]},
    ],
    "SessionEnd": [
        {"hooks": [{"type": "command", "command": "${python}", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/handoff.py"], "timeout": 10}]},
    ],
}

COMMAND_MAP = [
    ("/dw-requirement-analysis", "/dw-harness:dw-requirement-analysis"),
    ("/dw-technical-design", "/dw-harness:dw-technical-design"),
    ("/dw-etl", "/dw-harness:dw-etl"),
    ("/dw-self-test", "/dw-harness:dw-self-test"),
    ("/dw-data-comparison", "/dw-harness:dw-data-comparison"),
    ("/dw-sr", "/dw-harness:dw-sr"),
    ("/dw-performance-optimization", "/dw-harness:dw-performance-optimization"),
    ("/dw-dqc", "/dw-harness:dw-dqc"),
]


@dataclass
class MigrationReport:
    actions: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    removed_v1_hooks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"actions": self.actions, "conflicts": self.conflicts,
                "removed_v1_hooks": self.removed_v1_hooks}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _managed_index(root: Path) -> Dict[str, str]:
    path = root / ".claude" / "dw" / "managed.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_managed(root: Path, index: Dict[str, str]) -> None:
    path = root / ".claude" / "dw" / "managed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def merge_settings(target: Path, python: str, dry_run: bool,
                    report: MigrationReport) -> None:
    settings_path = target / ".claude" / "settings.json"
    settings: Dict = {}
    if settings_path.is_file():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            report.conflicts.append(f"{settings_path}: not valid JSON; left untouched, "
                                    f"merge hooks manually")
            return
    hooks = settings.get("hooks") or {}
    for event, entries in list(hooks.items()):
        kept = []
        for entry in entries:
            entry_cmds = [h.get("command", "") for h in entry.get("hooks", [])]
            joined = "|".join(entry_cmds)
            if any(v1 in joined for v1 in V1_HOOK_COMMANDS):
                report.removed_v1_hooks.append(f"{event}: {joined[:80]}")
                continue
            kept.append(entry)
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    for event, wanted in V2_TEMPLATE_HOOKS.items():
        existing = hooks.setdefault(event, [])
        have_matchers = {json.dumps(e.get("matcher", ""), sort_keys=True) for e in existing}
        for block in wanted:
            key = json.dumps(block.get("matcher", ""), sort_keys=True)
            if key in have_matchers:
                continue  # idempotent: never append a second block for same matcher
            block = json.loads(json.dumps(block).replace("${python}", python))
            existing.append(block)
    settings["hooks"] = hooks
    if not dry_run:
        if settings_path.is_file():
            shutil.copy2(settings_path, settings_path.with_name(
                settings_path.name + f".bak-{_stamp()}"))
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
    report.actions.append(f"settings.json: hooks merged (python={python!r}), "
                          f"{len(report.removed_v1_hooks)} v1 hook entry(ies) disabled")


def _stamp() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")


def install_tree(target: Path, source_dir: Path, managed_rel: List[Tuple[str, str]],
                 dry_run: bool, report: MigrationReport, v1_hashes: Dict[str, str]) -> None:
    """Copy scaffold files, respecting managed-file hashing and conflicts."""
    index = _managed_index(target)
    for rel_src, rel_dst in managed_rel:
        src = source_dir / rel_src
        dst = target / rel_dst
        if not src.is_file():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        new_hash = _sha(src)
        if dst.is_file():
            current = _sha(dst)
            if current == new_hash:
                continue  # already current
            known = index.get(rel_dst)
            v1_known = v1_hashes.get(rel_dst)
            if known == current or v1_known == current:
                if not dry_run:
                    shutil.copy2(src, dst)
                report.actions.append(f"updated managed file {rel_dst}")
            else:
                report.conflicts.append(f"{rel_dst}: locally modified; kept yours "
                                        f"(new version available in scaffold)")
        else:
            if not dry_run:
                shutil.copy2(src, dst)
            report.actions.append(f"installed {rel_dst}")
        if not dry_run:
            index[rel_dst] = new_hash
    if not dry_run:
        _write_managed(target, index)


def merge_claude_md(target: Path, source_dir: Path, dry_run: bool,
                    report: MigrationReport) -> None:
    dst = target / "CLAUDE.md"
    src = source_dir / "CLAUDE.md"
    if dst.is_file():
        text = dst.read_text(encoding="utf-8-sig")
        if "@AGENTS.md" in text:
            report.actions.append("CLAUDE.md: already references AGENTS.md")
            return
        if not dry_run:
            shutil.copy2(dst, dst.with_name(dst.name + f".bak-{_stamp()}"))
            dst.write_text(text.rstrip() + "\n\n@AGENTS.md\n", encoding="utf-8")
        report.actions.append("CLAUDE.md: appended @AGENTS.md reference (backup kept)")
    else:
        if not dry_run:
            shutil.copy2(src, dst)
        report.actions.append("CLAUDE.md: installed")


def run_init(target: Path, template_root: Path, python: str, dialect: str,
             dry_run: bool = False, v1_hashes: Optional[Dict[str, str]] = None,
             mcp: bool = False) -> MigrationReport:
    """Merge-install the copy-template form into *target*.

    *template_root* is the generated ``template/`` directory: CLAUDE.md /
    AGENTS.md at its root, machinery under ``.claude/``.
    """
    report = MigrationReport()
    v1_hashes = v1_hashes or {}
    merge_settings(target, python, dry_run, report)
    merge_claude_md(target, template_root, dry_run, report)
    tree: List[Tuple[str, str]] = [
        ("AGENTS.md", "AGENTS.md"),
        ("contracts/contract.example.json", "contracts/contract.example.json"),
    ]
    scaffold_files = [
        (".claude/dw/harness.json", ".claude/dw/harness.json"),
        (".claude/dw/state.json", ".claude/dw/state.json"),
        (".claude/dw/policy_exceptions.json", ".claude/dw/policy_exceptions.json"),
        (".claude/rules/sql-style.md", ".claude/rules/sql-style.md"),
        (".claude/rules/etl.md", ".claude/rules/etl.md"),
        (".claude/rules/sr.md", ".claude/rules/sr.md"),
    ]
    machinery: List[Tuple[str, str]] = []
    for group in ("hooks", "dw_core", "skills", "agents", "dialects", "output-styles"):
        base = template_root / ".claude" / group
        if base.is_dir():
            for item in sorted(base.rglob("*")):
                if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc":
                    rel = item.relative_to(template_root).as_posix()
                    machinery.append((rel, rel))
    # never manage the wiring file itself in copy mode (settings.json owns it)
    machinery = [(s, d) for s, d in machinery if not d.endswith("hooks/hooks.json")]
    install_tree(target, template_root, tree + scaffold_files + machinery,
                 dry_run, report, v1_hashes)
    if mcp:
        mcp_path = target / ".mcp.json"
        entry = {"mcpServers": {"dw-harness": {
            "command": python,
            "args": [str((target / ".claude" / "dw" / "mcp" / "server.py"))],
            "env": {}}}}
        if mcp_path.is_file():
            try:
                existing = json.loads(mcp_path.read_text(encoding="utf-8-sig"))
                servers = existing.setdefault("mcpServers", {})
                if "dw-harness" not in servers:
                    servers["dw-harness"] = entry["mcpServers"]["dw-harness"]
                    if not dry_run:
                        mcp_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
                    report.actions.append(".mcp.json: added dw-harness server entry")
            except json.JSONDecodeError:
                report.conflicts.append(".mcp.json: invalid JSON, MCP registration skipped")
        else:
            if not dry_run:
                mcp_path.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n",
                                    encoding="utf-8")
            report.actions.append(".mcp.json: created with dw-harness server entry")
        if not dry_run:
            server_src = scaffold_dir / "mcp" / "server.py"
            if server_src.is_file():
                dst = target / ".claude" / "dw" / "mcp" / "server.py"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(server_src, dst)
    if dialect and not dry_run:
        cfg_path = target / ".claude" / "dw" / "harness.json"
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            cfg.setdefault("dialect", {})["default"] = dialect
            cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
            # dw init itself edited the file: refresh the managed hash so the
            # next run does not misread its own change as a user modification
            index = _managed_index(target)
            index[".claude/dw/harness.json"] = _sha(cfg_path)
            _write_managed(target, index)
            report.actions.append(f"harness.json: default dialect = {dialect}")
        except (json.JSONDecodeError, OSError):
            report.conflicts.append("harness.json: could not set dialect")
    return report
