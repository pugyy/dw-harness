#!/usr/bin/env python3
"""Validate SQL files from Claude Code PostToolUse hook input."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def read_hook_input() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_input": raw}


def hook_file_path(payload: dict) -> str:
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if file_path:
        return str(file_path)
    if len(sys.argv) > 1:
        return sys.argv[1]
    return ""


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def strip_sql_comments(sql: str) -> str:
    def keep_newlines(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    sql = re.sub(r"/\*.*?\*/", keep_newlines, sql, flags=re.S)
    return re.sub(r"--[^\n]*", "", sql)


def iter_statements(sql: str):
    for match in re.finditer(r"[^;]+", sql):
        statement = match.group(0)
        if statement.strip():
            line_no = sql.count("\n", 0, match.start()) + 1
            yield line_no, statement


def line_number(sql: str, offset: int) -> int:
    return sql.count("\n", 0, offset) + 1


def validate(sql: str) -> list[dict]:
    issues: list[dict] = []
    uncommented = strip_sql_comments(sql)

    for match in re.finditer(r"\bselect\s+\*", uncommented, flags=re.I):
        issues.append(
            {
                "line": line_number(uncommented, match.start()),
                "severity": "ERROR",
                "rule": "no-select-star",
                "message": "禁止使用 SELECT *，请明确指定字段列表。",
            }
        )

    for line_no, statement in iter_statements(uncommented):
        has_insert = re.search(
            r"\binsert\s+(?:overwrite|into)\s+(?:table\s+)?",
            statement,
            flags=re.I,
        )
        if has_insert and not re.search(r"\bpartition\s*\(", statement, flags=re.I):
            issues.append(
                {
                    "line": line_no,
                    "severity": "ERROR",
                    "rule": "insert-requires-partition",
                    "message": "INSERT/INSERT OVERWRITE 语句必须包含 PARTITION 子句。",
                }
            )

        if re.search(r"\bupdate\s+[\w.]+", statement, flags=re.I) and not re.search(
            r"\bwhere\b", statement, flags=re.I
        ):
            issues.append(
                {
                    "line": line_no,
                    "severity": "ERROR",
                    "rule": "update-requires-where",
                    "message": "UPDATE 必须包含 WHERE 条件。",
                }
            )

        if re.search(r"\bdelete\s+from\s+[\w.]+", statement, flags=re.I) and not re.search(
            r"\bwhere\b", statement, flags=re.I
        ):
            issues.append(
                {
                    "line": line_no,
                    "severity": "ERROR",
                    "rule": "delete-requires-where",
                    "message": "DELETE 必须包含 WHERE 条件。",
                }
            )

        if re.search(r"\bpartitioned\s+by\b", statement, flags=re.I) and re.search(
            r"\bdt\s+(?:string|varchar)\b", statement, flags=re.I
        ):
            issues.append(
                {
                    "line": line_no,
                    "severity": "ERROR",
                    "rule": "partition-name",
                    "message": "分区字段必须命名为 partition_dt，不使用 dt。",
                }
            )

    money_field = re.compile(r"\b(amount|price|fee|cost|money|pay)\w*\b", flags=re.I)
    for index, line in enumerate(uncommented.splitlines(), start=1):
        if money_field.search(line) and re.search(r"\bdouble\b", line, flags=re.I):
            issues.append(
                {
                    "line": index,
                    "severity": "ERROR",
                    "rule": "money-decimal",
                    "message": "金额字段必须使用 DECIMAL(20,4)，不允许 DOUBLE。",
                }
            )

    return issues


def main() -> int:
    payload = read_hook_input()
    file_path = hook_file_path(payload)
    if not file_path:
        return 0

    path = Path(file_path)
    if path.suffix.lower() != ".sql":
        return 0
    if not path.exists():
        print(f"[dw-harness] SQL 文件不存在: {path}", file=sys.stderr)
        return 2

    issues = validate(read_text(path))
    if not issues:
        return 0

    print(f"[dw-harness] SQL 规范检查失败: {path}", file=sys.stderr)
    for issue in issues:
        print(
            f"[{issue['severity']}] line {issue['line']} "
            f"{issue['rule']}: {issue['message']}",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
