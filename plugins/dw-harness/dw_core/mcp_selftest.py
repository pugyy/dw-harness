"""Spawn the MCP server and verify the handshake end-to-end."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def mcp_selftest(server_path: Path = None, root: Path = None) -> bool:
    registration = root / ".mcp.json" if root else None
    if registration and registration.is_file():
        try:
            server = json.loads(registration.read_text(encoding="utf-8-sig"))["mcpServers"]["dw-harness"]
            command = [server["command"], *server.get("args", [])]
            return _probe(command, root, {**os.environ, **server.get("env", {})})
        except (KeyError, ValueError, TypeError, OSError, subprocess.SubprocessError):
            return False
    candidates = [server_path] if server_path else [
        Path(__file__).resolve().parent / "data/template/.claude/dw/mcp/server.py",
        Path(__file__).resolve().parents[2] / "mcp/server.py",
        Path(__file__).resolve().parents[1] / "mcp/server.py",
    ]
    server = next((p for p in candidates if p and p.is_file()), None)
    if server is None:
        return False
    return _probe([sys.executable, str(server)], root, dict(os.environ))


def _probe(command, root, env) -> bool:
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18"}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "lint_sql",
                               "arguments": {"sql": "SELECT * FROM t"}}}),
    ]
    proc = subprocess.run(
        command, cwd=root,
        input="\n".join(lines) + "\n", capture_output=True, text=True,
        timeout=60, env=env)
    if proc.returncode != 0:
        return False
    responses = {}
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") is not None:
            responses[msg["id"]] = msg
    if 1 not in responses or "result" not in responses.get(1, {}):
        return False
    tools = responses.get(2, {}).get("result", {}).get("tools", [])
    if not any(t.get("name") == "lint_sql" for t in tools):
        return False
    call = json.dumps(responses.get(3, {}).get("result", {}))
    return "no-select-star" in call and "isError" not in responses.get(3, {}).get("result", {})
