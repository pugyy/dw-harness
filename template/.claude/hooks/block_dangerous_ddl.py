#!/usr/bin/env python3
"""Block dangerous SQL commands from Claude Code PreToolUse Bash hooks."""

from __future__ import annotations

import json
import re
import sys


def read_hook_input() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_input": raw}


def command_from_payload(payload: dict) -> str:
    tool_input = payload.get("tool_input") or {}
    if "command" in tool_input:
        return str(tool_input["command"])
    return str(payload.get("raw_input") or "")


def deny(reason: str) -> int:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", "", sql)


def dangerous_reason(command: str) -> str | None:
    normalized = strip_comments(command)
    checks = [
        (r"\bdrop\s+table\b", "检测到 DROP TABLE。请先确认风险，并在 CLAUDE.md 记录原因。"),
        (r"\btruncate\s+table\b", "检测到 TRUNCATE TABLE。请先确认风险，并在 CLAUDE.md 记录原因。"),
        (r"\bdrop\s+database\b", "检测到 DROP DATABASE。请先确认风险，并在 CLAUDE.md 记录原因。"),
        (
            r"\balter\s+table\b[\s\S]*?\bdrop\s+column\b",
            "检测到 ALTER TABLE DROP COLUMN。请先确认风险，并在 CLAUDE.md 记录原因。",
        ),
    ]
    for pattern, reason in checks:
        if re.search(pattern, normalized, flags=re.I):
            return reason

    for statement in re.split(r";+", normalized):
        if re.search(r"\bdelete\s+from\s+[\w.]+", statement, flags=re.I) and not re.search(
            r"\bwhere\b", statement, flags=re.I
        ):
            return "检测到无 WHERE 的 DELETE。请补充 WHERE 条件或人工确认后再执行。"

    return None


def main() -> int:
    payload = read_hook_input()
    command = command_from_payload(payload)
    reason = dangerous_reason(command)
    if reason:
        return deny(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
