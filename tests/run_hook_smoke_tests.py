#!/usr/bin/env python3
"""Smoke tests for dw-harness hook scripts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "template" / ".claude" / "hooks"
SAMPLES = ROOT / "examples" / "sample-sql"


def run_hook(
    script: str,
    payload: dict,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    hook_env = os.environ.copy()
    hook_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        hook_env.update(env)

    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
        env=hook_env,
    )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_validate_good_sql() -> None:
    result = run_hook(
        "validate_sql.py",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(SAMPLES / "good_insert.sql")},
        },
    )
    assert_true(result.returncode == 0, result.stderr)


def test_validate_bad_sql() -> None:
    result = run_hook(
        "validate_sql.py",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(SAMPLES / "bad_select_star.sql")},
        },
    )
    assert_true(result.returncode == 2, "bad SQL should be blocked")
    assert_true("no-select-star" in result.stderr, result.stderr)
    assert_true("insert-requires-partition" in result.stderr, result.stderr)


def test_validate_bad_hive() -> None:
    result = run_hook(
        "validate_sql.py",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(SAMPLES / "bad_hive_multi.sql")},
        },
    )
    assert_true(result.returncode == 2, "bad Hive SQL should be blocked")
    assert_true("dialect=hive" in result.stderr, result.stderr)
    assert_true("insert-requires-partition" in result.stderr, result.stderr)
    assert_true("money-decimal" in result.stderr, result.stderr)
    assert_true("partition-name" in result.stderr, result.stderr)
    assert_true("hive-format-hint" in result.stderr, result.stderr)


def test_validate_good_spark() -> None:
    result = run_hook(
        "validate_sql.py",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(SAMPLES / "good_spark_insert.sql")},
        },
    )
    assert_true(result.returncode == 0, result.stderr)


def test_validate_bad_spark_create() -> None:
    result = run_hook(
        "validate_sql.py",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(SAMPLES / "bad_spark_create_missing_using.sql")},
        },
    )
    assert_true(result.returncode == 2, "bad Spark SQL should be blocked")
    assert_true("dialect=spark" in result.stderr, result.stderr)
    assert_true("spark-format-hint" in result.stderr, result.stderr)


def test_dialect_env_override() -> None:
    result = run_hook(
        "validate_sql.py",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(SAMPLES / "bad_spark_create_missing_using.sql")},
        },
        env={"DW_HARNESS_DIALECT": "odps"},
    )
    assert_true(result.returncode == 0, result.stderr)


def test_block_dangerous_ddl() -> None:
    result = run_hook(
        "block_dangerous_ddl.py",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "odpscmd -e \"DROP TABLE db_a.dws_trade_order_di;\""},
        },
    )
    assert_true(result.returncode == 0, result.stderr)
    payload = json.loads(result.stdout)
    decision = payload["hookSpecificOutput"]["permissionDecision"]
    assert_true(decision == "deny", result.stdout)


def test_block_delete_without_where() -> None:
    result = run_hook(
        "block_dangerous_ddl.py",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "hive -e \"DELETE FROM db_a.dws_trade_order_di;\""},
        },
    )
    assert_true(result.returncode == 0, result.stderr)
    payload = json.loads(result.stdout)
    decision = payload["hookSpecificOutput"]["permissionDecision"]
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert_true(decision == "deny", result.stdout)
    assert_true("无 WHERE" in reason or "without WHERE" in reason, result.stdout)


def test_allow_safe_bash() -> None:
    result = run_hook(
        "block_dangerous_ddl.py",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "odpscmd -e \"SELECT count(1) FROM db_a.dws_trade_order_di;\""},
        },
    )
    assert_true(result.returncode == 0, result.stderr)
    assert_true(result.stdout.strip() == "", result.stdout)


def test_inject_context_outputs_additional_context() -> None:
    result = run_hook(
        "inject_context.py",
        {"hook_event_name": "PostCompact", "trigger": "manual"},
        env={"CLAUDE_PROJECT_DIR": str(ROOT / "template")},
    )
    assert_true(result.returncode == 0, result.stderr)
    payload = json.loads(result.stdout)
    output = payload["hookSpecificOutput"]
    assert_true(output["hookEventName"] == "PostCompact", result.stdout)
    assert_true("additionalContext" in output, result.stdout)
    assert_true("SQL 强制规范" in output["additionalContext"], result.stdout)


def main() -> int:
    tests = [
        test_validate_good_sql,
        test_validate_bad_sql,
        test_validate_bad_hive,
        test_validate_good_spark,
        test_validate_bad_spark_create,
        test_dialect_env_override,
        test_block_dangerous_ddl,
        test_block_delete_without_where,
        test_allow_safe_bash,
        test_inject_context_outputs_additional_context,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("All hook smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
