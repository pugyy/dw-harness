#!/usr/bin/env python3
"""dw-harness local stdio MCP server (default OFF; register explicitly).

Registration (independent and verifiable):
    dw init --mcp          # writes .mcp.json entry pointing at this file
    dw mcp --selftest      # spawns the server, performs MCP handshake + tools/list

Protocol: newline-delimited JSON-RPC 2.0 over stdio (MCP stdio transport).
All tools are read-only and return limited, structured results.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

INSTALL_ROOT = Path(__file__).resolve().parent.parent
for candidate in (INSTALL_ROOT, INSTALL_ROOT.parent, INSTALL_ROOT / "src"):
    if (candidate / "dw_core").is_dir():
        sys.path.insert(0, str(candidate))
        break

from dw_core import __version__  # noqa: E402

MAX_RESULTS = 50

TOOLS = [
    {
        "name": "lint_sql",
        "description": "Lint SQL text with project rules; returns structured issues.",
        "inputSchema": {"type": "object", "properties": {
            "sql": {"type": "string"},
            "dialect": {"type": "string", "enum": ["odps", "hive", "spark", "starrocks"]},
        }, "required": ["sql"]},
    },
    {
        "name": "get_contract",
        "description": "Return the compiled table contract (source file + freshness).",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "contract yaml/json path"},
        }},
    },
    {
        "name": "get_table_schema",
        "description": "Table schema parsed from repo DDL files (source: repo-ddl).",
        "inputSchema": {"type": "object", "properties": {
            "table": {"type": "string"},
        }, "required": ["table"]},
    },
    {
        "name": "get_lineage",
        "description": "Table-level lineage from repo SQL; marks source and unknowns.",
        "inputSchema": {"type": "object", "properties": {
            "table": {"type": "string"},
        }, "required": ["table"]},
    },
    {
        "name": "get_check_report",
        "description": "Latest dw check report (four-state acceptance).",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "report json path"},
        }},
    },
]


def _root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    cur = Path(os.getcwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".claude" / "dw").is_dir() or (candidate / ".git").exists():
            return candidate
    return cur


def _project_path(root: Path, path: Path) -> Path:
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("path lies outside the project")
    return resolved


def _tool_lint_sql(params: dict) -> dict:
    from dw_core.config import HarnessConfig
    from dw_core.rules import lint_sql
    config = HarnessConfig.load(root=_root())
    result = lint_sql(str(params.get("sql", "")),
                      config.resolve_dialect(explicit=params.get("dialect")), config)
    payload = result.to_dict()
    payload["issues"] = payload["issues"][:MAX_RESULTS]
    payload["truncated"] = len(result.issues) > MAX_RESULTS
    return payload


def _tool_get_contract(params: dict) -> dict:
    from dw_core.contracts import load_contract
    path = Path(params.get("path") or "") if params.get("path") else None
    if path is None:
        root = _root()
        matches = sorted(list(root.glob("contracts/*.json")) + list(root.glob("contracts/*.yaml")))
        if not matches:
            return {"error": "no contract found; pass explicit path"}
        path = matches[0]
    try:
        root = _root()
        path = _project_path(root, path)
        if (path.suffix.lower() not in {".json", ".yaml", ".yml"} or
                (not path.is_relative_to(root / "contracts") and
                 (path.parent != root or path.stem != "contract"))):
            raise ValueError("path must point to a project contract")
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("contract exceeds the response size limit")
        contract, _ = load_contract(path)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"contract unreadable: {exc}"}
    import datetime
    return {"source": str(path), "freshness": datetime.datetime.fromtimestamp(
        path.stat().st_mtime).isoformat(timespec="seconds"), "contract": contract}


def _tool_get_table_schema(params: dict) -> dict:
    from dw_core.ddl import parse_create_table
    root = _root()
    want = str(params.get("table", "")).lower()
    found = []
    for sql_file in root.rglob("*.sql"):
        if any(part in (".git", ".claude", "node_modules") for part in sql_file.parts):
            continue
        try:
            sql_file = _project_path(root, sql_file)
            tables = parse_create_table(sql_file.read_text(encoding="utf-8-sig", errors="replace"))
        except (OSError, ValueError):
            continue
        for table in tables:
            if want in table.table.lower():
                found.append({
                    "source": f"repo-ddl:{sql_file.relative_to(root).as_posix()}",
                    "table": table.table,
                    "columns": [{"name": c.name, "type": c.type_key(),
                                 "nullable": c.nullable, "comment": c.comment}
                                for c in table.columns],
                    "partition_columns": [c.name for c in table.partition_columns],
                    "unresolved": table.unresolved,
                })
    return {"table": want, "matches": found[:MAX_RESULTS],
            "note": "schema proven from repo DDL only; live catalog not queried"}


def _tool_get_lineage(params: dict) -> dict:
    from dw_core.impact import DataWorksLineage, analyze_impact
    adapter = DataWorksLineage() if os.environ.get("DW_HARNESS_DW_ENDPOINT") else None
    report = analyze_impact(_root(), str(params.get("table", "")), adapter)
    payload = report.to_dict()
    return payload


def _tool_get_check_report(params: dict) -> dict:
    root = _root()
    path = Path(params.get("path") or "") if params.get("path") else root / ".claude" / "dw" / "check_report.json"
    path = _project_path(root, path)
    if path.suffix.lower() != ".json" or not any(
            path.is_relative_to(root / folder) for folder in (".claude/dw", "reports")):
        raise ValueError("report must be under .claude/dw or reports")
    if not path.is_file():
        return {"error": "no check report; run dw check first"}
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("report exceeds the response size limit")
    report = json.loads(path.read_text(encoding="utf-8-sig"))
    if (not isinstance(report, dict) or
            report.get("schema") not in {"dw-check/1", "dw-check-batch/1"}):
        raise ValueError("file is not a dw check report")
    return report


HANDLERS = {
    "lint_sql": _tool_lint_sql,
    "get_contract": _tool_get_contract,
    "get_table_schema": _tool_get_table_schema,
    "get_lineage": _tool_get_lineage,
    "get_check_report": _tool_get_check_report,
}


def handle(message: dict) -> dict | None:
    method = message.get("method", "")
    msg_id = message.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": message.get("params", {}).get(
                "protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "dw-harness", "version": __version__},
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name", "")
        handler = HANDLERS.get(name)
        if not handler:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {
                "code": -32601, "message": f"unknown tool: {name}"}}
        try:
            result = handler(params.get("arguments") or {})
        except Exception as exc:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": msg_id, "result": {
                "content": [{"type": "text", "text": json.dumps({"error": str(exc)})}],
                "isError": True}}
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False,
                                                            default=str)}]}}
    if msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {
            "code": -32601, "message": f"method not found: {method}"}}
    return None  # notification: no response


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = {"jsonrpc": "2.0", "id": None, "error": {
                "code": -32700, "message": "parse error"}}
        else:
            response = handle(message)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
