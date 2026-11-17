"""dw init: merge-style migration from v1 (and fresh installs).

Managed files are tracked in .claude/dw/managed.json with content hashes.
Only unmodified managed files (or files matching the bundled v1 hashes) get
replaced; user-modified files are reported as conflicts and left untouched.
Re-running never duplicates hook entries.
"""
from __future__ import annotations

import hashlib
import json
import re
import shlex
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
        {"matcher": "Bash|PowerShell", "script": "guard_shell.py", "timeout": 20, "onFailure": "block"},
        {"matcher": "Write|Edit", "script": "guard_write.py", "timeout": 20, "onFailure": "block"},
    ],
    "PostToolUse": [
        {"matcher": "Write|Edit", "script": "validate_post.py", "timeout": 60},
    ],
    "SessionStart": [
        {"matcher": "startup|resume|clear|compact", "script": "session_context.py", "timeout": 10},
    ],
    "PostCompact": [
        {"matcher": "manual|auto", "script": "post_compact.py", "timeout": 10},
    ],
    "SessionEnd": [
        {"script": "handoff.py", "timeout": 10},
    ],
}


def _split_python(python: str) -> Tuple[List[str], List[str]]:
    """'python' -> (['python'], []); 'py -3' -> (['py'], ['-3']);
    'C:\\Program Files\\Py39\\python.exe' (spaces, no flags) stays ONE
    executable. No JSON string surgery, no quote stripping of real paths."""
    raw = python.strip()
    for quote in ('"', "'"):
        if len(raw) >= 2 and raw.startswith(quote) and raw.endswith(quote):
            return [raw[1:-1]], []
    if " " not in raw:
        return [raw or "python"], []
    if " -" in raw:  # flag-looking tokens: "py -3", "python -u x.py"
        try:
            parts = [p.strip('"\'') for p in shlex.split(raw, posix=False)
                     if p.strip()]
        except ValueError:
            parts = raw.split()
        if parts:
            return parts[:1], parts[1:]
    # spaces but no flags: treat the whole string as one (quoted) executable
    return [raw], []


def _v2_hook_block(block: Dict, python: str) -> Dict:
    exe, extra = _split_python(python)
    hook = {"type": "command", "command": exe[0],
            "args": [*extra, "${CLAUDE_PROJECT_DIR}/.claude/hooks/" + block["script"]],
            "timeout": block.get("timeout", 30)}
    if "onFailure" in block:
        hook["onFailure"] = block["onFailure"]
    entry = {"matcher": block["matcher"]} if block.get("matcher") else {}
    entry["hooks"] = [hook]
    return entry

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
                   report: MigrationReport, statusline: bool = False,
                   mode: str = "template") -> None:
    settings_path = target / ".claude" / "settings.json"
    settings: Dict = {}
    if settings_path.is_file():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            report.conflicts.append(f"{settings_path}: not valid JSON; left untouched, "
                                    f"merge hooks manually")
            return
    if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
        report.conflicts.append("settings.json: invalid settings structure")
        return
    hooks = settings.get("hooks", {})
    original = json.dumps(settings, sort_keys=True)
    wiring = {event: [_v2_hook_block(block, python) for block in blocks]
              for event, blocks in V2_TEMPLATE_HOOKS.items()}
    owned = {(event, block.get("matcher"), block["hooks"][0]["args"][-1]): block["hooks"][0]
             for event, blocks in wiring.items() for block in blocks}
    legacy_scripts = {command.split()[-1] for command in V1_HOOK_COMMANDS}
    legacy = re.compile(r"^(?:python(?:3|\.exe)?|py(?:\.exe)?(?:\s+-3)?)\s+[\"']?([^'\"\s]+)[\"']?$", re.I)
    # drop v1 entries, remember which v2 scripts are already wired (by script
    # identity, NOT by matcher: a user hook on the same matcher must never
    # silently suppress our guards)
    wired_scripts = set()
    for event, entries in list(hooks.items()):
        kept = []
        for entry in entries:
            handlers = []
            for hook in entry.get("hooks", []):
                command = hook.get("command", "")
                match = legacy.fullmatch(command)
                if (hook.get("type") == "command" and match
                        and match[1].replace(chr(92), "/") in legacy_scripts):
                    report.removed_v1_hooks.append(f"{event}: {command}")
                    continue
                args = hook.get("args") or []
                key = (event, entry.get("matcher"), args[-1] if args else None)
                if hook.get("type") == "command" and key in owned:
                    if key not in wired_scripts and mode == "template":
                        handlers.append(owned[key])
                        wired_scripts.add(key)
                    continue
                handlers.append(hook)
            if handlers:
                kept.append({**entry, "hooks": handlers})
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    if mode == "template":
        for event, entries in wiring.items():
            for entry in entries:
                key = (event, entry.get("matcher"), entry["hooks"][0]["args"][-1])
                if key not in wired_scripts:
                    hooks.setdefault(event, []).append(entry)
    settings["hooks"] = hooks
    if statusline and "statusLine" not in settings:
        exe, extra = _split_python(python)
        # official statusLine schema: type/command/padding/refreshInterval;
        # command is ONE shell string (no args field). Paths are ABSOLUTE and
        # quoted: the statusLine contract does not promise ${CLAUDE_PROJECT_DIR}
        # expansion or env injection, and interpreter paths may contain spaces.
        script = target / ".claude" / "hooks" / "statusline.py"
        command = " ".join([f'"{exe[0]}"', *extra, f'"{script}"'])
        settings["statusLine"] = {"type": "command", "command": command, "padding": 0}
        report.actions.append("settings.json: dw statusLine added (user statusLine absent)")
    if json.dumps(settings, sort_keys=True) == original:
        return
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
        new_hash = _sha(src)
        if dst.is_file():
            current = _sha(dst)
            if current == new_hash:
                index[rel_dst] = new_hash
                continue
            known = index.get(rel_dst)
            v1_known = v1_hashes.get(rel_dst)
            if known == current or v1_known == current:
                if not dry_run:
                    shutil.copy2(src, dst)
                report.actions.append(f"updated managed file {rel_dst}")
            else:
                report.conflicts.append(f"{rel_dst}: locally modified; kept yours "
                                        f"(new version available in scaffold)")
                continue
        else:
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            report.actions.append(f"installed {rel_dst}")
        if not dry_run:
            index[rel_dst] = new_hash
    if not dry_run and index != _managed_index(target):
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
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        report.actions.append("CLAUDE.md: installed")


def run_init(target: Path, template_root: Path, python: str, dialect: str,
             dry_run: bool = False, v1_hashes: Optional[Dict[str, str]] = None,
             mcp: bool = False, statusline: bool = False,
             mode: str = "template") -> MigrationReport:
    """Merge-install the copy-template form into *target*.

    *template_root* is the generated ``template/`` directory: CLAUDE.md /
    AGENTS.md at its root, machinery under ``.claude/``.
    """
    report = MigrationReport()
    if v1_hashes is None:
        index = template_root / ".claude/dw/v1_hashes.json"
        v1_hashes = json.loads(index.read_text(encoding="utf-8-sig")) if index.is_file() else {}
    if mcp and not (template_root / ".claude/dw/mcp/server.py").is_file():
        report.conflicts.append("MCP server missing from the installation package")
        return report
    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)
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
    groups = ["hooks", "dw_core", "skills", "agents", "output-styles"] if mode == "template" else []
    if mcp and "dw_core" not in groups:
        groups.append("dw_core")
    if mcp:
        rel = ".claude/dw/mcp/server.py"
        machinery.append((rel, rel))
    if statusline and mode == "plugin":
        rel = ".claude/hooks/statusline.py"
        machinery.append((rel, rel))
        rel = ".claude/hooks/_bootstrap.py"
        machinery.append((rel, rel))
        if "dw_core" not in groups:
            groups.append("dw_core")
    for group in groups:
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
    # Wheel builds exclude template/.claude/dw_core to avoid shipping a second
    # copy of the package. Copy the installed core into the project instead.
    if "dw_core" in groups and not (template_root / ".claude" / "dw_core").is_dir():
        core_root = Path(__file__).resolve().parent
        core_files: List[Tuple[str, str]] = []
        for item in sorted(core_root.rglob("*")):
            if not item.is_file():
                continue
            rel = item.relative_to(core_root)
            if rel.parts[:2] == ("data", "template"):
                continue
            if "__pycache__" in rel.parts or item.suffix == ".pyc":
                continue
            rel_posix = rel.as_posix()
            core_files.append((rel_posix, f".claude/dw_core/{rel_posix}"))
        if core_files:
            install_tree(target, core_root, core_files, dry_run, report, v1_hashes)
    merge_settings(target, python, dry_run, report, statusline=statusline, mode=mode)
    if mcp:
        mcp_path = target / ".mcp.json"
        exe, flags = _split_python(python)
        entry = {"mcpServers": {"dw-harness": {
            "command": exe[0],
            "args": [*flags, str(target / ".claude" / "dw" / "mcp" / "server.py")],
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
    if dialect and not dry_run:
        cfg_path = target / ".claude" / "dw" / "harness.json"
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            if cfg.setdefault("dialect", {}).get("default") == dialect:
                return report
            cfg["dialect"]["default"] = dialect
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
