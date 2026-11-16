"""Resolve a Git changeset to independently checked warehouse tables."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .contracts import ContractError, load_contract, read_baseline
from .ddl import parse_create_table
from .guard import _target_table
from .sqlsplit import scan_sql


def _is_contract(path: Path) -> bool:
    return (path.suffix.lower() in {".json", ".yaml", ".yml"}
            and ("contracts" in path.parent.parts or path.stem.startswith("contract"))
            and "schema" not in path.parent.parts
            and not path.name.endswith((".example.json", ".schema.json")))


def _git_paths(root: Path, base: str):
    cmd = ["git", "ls-tree", "-r", "--name-only", "-z", base]
    output = subprocess.run(cmd, cwd=root, capture_output=True, check=True, timeout=30)
    return set(output.stdout.decode("utf-8").split("\0"))


def resolve_table_checks(root: Path, base: str, paths, table: str = ""):
    """Group changed SQL, contracts and DQC by target table; surface ambiguities."""
    existing = _git_paths(root, base)
    targets = {}
    unresolved = []
    changed_contracts = {}
    candidates = list(dict.fromkeys([
        *(p for p in paths if _is_contract(p.relative_to(root))),
        *(p for p in (root / "contracts").rglob("*") if p.is_file() and _is_contract(p.relative_to(root))),
        *(p for p in root.glob("contract.*") if p.is_file() and _is_contract(p.relative_to(root))),
    ]))
    contracts = {}
    for path in candidates:
        rel = path.relative_to(root).as_posix()
        baseline = f"git:{base}:{rel}" if rel in existing else None
        try:
            if path.is_file():
                name = load_contract(path)[0]["table"]
            elif baseline:
                name = read_baseline(baseline, root)[0]["table"]
            else:
                raise ValueError("contract deleted")
            if not name:
                raise ValueError("no target table")
            contracts.setdefault(name, []).append((path, baseline))
            if path in paths:
                changed_contracts.setdefault(name, []).append((path, baseline))
                if not table or table == name:
                    targets.setdefault(name, {})
        except (OSError, ValueError, TypeError, KeyError, AttributeError, ContractError,
                subprocess.SubprocessError):
            if path in paths:
                unresolved.append(rel)

    for path in paths:
        rel = path.relative_to(root).as_posix()
        if not path.is_file():
            if path.suffix.lower() == ".sql" or _is_contract(path) or path.name.startswith("dqc_"):
                unresolved.append(rel + " (deleted)")
            continue
        if path.suffix.lower() == ".sql":
            sql = path.read_text(encoding="utf-8-sig", errors="replace")
            ddls = parse_create_table(sql)
            names = {ddl.table for ddl in ddls}
            names.update(filter(None, (_target_table(st.code) for st in scan_sql(sql)[0])))
            if not names and table:
                names.add(table)
            if not names:
                unresolved.append(rel)
            for name in sorted(names):
                matches = [key for key in contracts if key == name or
                           ("." not in name and key.rsplit(".", 1)[-1] == name)]
                if len(matches) > 1:
                    unresolved.append(rel + " (ambiguous target " + name + ")")
                    continue
                name = matches[0] if matches else name
                if table and table != name:
                    continue
                options = targets.setdefault(name, {})
                options.setdefault("sql_files", []).append(path)
                if any(ddl.table in {name, name.rsplit(".", 1)[-1]} for ddl in ddls):
                    if "ddl_path" in options and options["ddl_path"] != path:
                        unresolved.append(rel + " (multiple DDLs for " + name + ")")
                    else:
                        options["ddl_path"] = path
        elif path.name.startswith("dqc_") and path.suffix.lower() == ".json":
            try:
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
                name = raw.get("table") or raw.get("table_name")
                if not isinstance(name, str) or not name:
                    raise ValueError("no target table")
                if not table or table == name:
                    targets.setdefault(name, {})["dqc_path"] = path
            except (OSError, ValueError, AttributeError):
                unresolved.append(rel)

    if table:
        targets.setdefault(table, {})
    for name, options in targets.items():
        choices = changed_contracts.get(name) or contracts.get(name, [])
        if len(choices) == 1:
            options["contract_path"], options["baseline"] = choices[0]
        elif choices:
            unresolved.append(f"{name} (multiple contracts)")
    return dict(sorted(targets.items())), sorted(set(unresolved))
