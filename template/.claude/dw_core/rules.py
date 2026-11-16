"""SQL rule registry and linter.

Every rule declares whether it encodes *engine* syntax limits or *project*
policy, so reports can say "StarRocks accepts this syntax, team policy still
requires an explicit partition" instead of a blanket "syntax error".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import HarnessConfig
from .sqlsplit import Statement, iter_select_clauses, scan_sql

RE_LINE = re.compile(r"\r\n|\r|\n", re.M)


@dataclass
class Issue:
    rule: str
    line: int
    severity: str  # error | warn
    message: str
    kind: str = "policy"  # engine | policy
    dialect: str = ""
    unresolved: bool = False

    def to_dict(self) -> Dict:
        return {
            "rule": self.rule,
            "line": self.line,
            "severity": self.severity,
            "message": self.message,
            "kind": self.kind,
            "dialect": self.dialect,
            "unresolved": self.unresolved,
        }


@dataclass
class LintResult:
    dialect: str
    issues: List[Issue] = field(default_factory=list)
    parse_problems: List[Dict] = field(default_factory=list)
    deep_parse: str = "unavailable"  # unavailable | ok | failed

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warns(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "warn"]

    def to_dict(self) -> Dict:
        return {
            "dialect": self.dialect,
            "status": "fail" if self.errors else ("warn" if self.warns else "pass"),
            "issues": [i.to_dict() for i in self.issues],
            "parse_problems": self.parse_problems,
            "deep_parse": self.deep_parse,
        }


RULE_REGISTRY: Dict[str, Dict] = {
    "no-select-star": {"level": "error", "kind": "policy",
                       "message": "SELECT * / t.* is not allowed; list columns explicitly."},
    "insert-requires-partition": {"level": "error", "kind": "policy",
                                  "message": "INSERT must declare the target PARTITION clause."},
    "dml-requires-where": {"level": "error", "kind": "engine",
                           "message": "UPDATE/DELETE without WHERE is not allowed."},
    "partition-name": {"level": "error", "kind": "policy",
                       "message": "Partition column must be named partition_dt, not dt."},
    "money-decimal": {"level": "error", "kind": "policy",
                      "message": "Money columns must use DECIMAL(20,4), not DOUBLE."},
    "money-precision": {"level": "warn", "kind": "policy",
                        "message": "Money column DECIMAL precision below team standard (20,4)."},
    "spark-create-format": {"level": "warn", "kind": "engine",
                            "message": "Spark CREATE TABLE should specify USING or STORED AS."},
    "hive-create-format": {"level": "warn", "kind": "engine",
                           "message": "Hive CREATE TABLE should specify STORED AS."},
    "sr-table-key": {"level": "warn", "kind": "engine",
                     "message": "StarRocks CREATE TABLE should declare a PRIMARY/DUPLICATE/UNIQUE key."},
    "sr-distributed-by": {"level": "warn", "kind": "engine",
                          "message": "StarRocks CREATE TABLE should declare DISTRIBUTED BY (or rely on default bucketing consciously)."},
    "column-comments": {"level": "off", "kind": "policy",
                        "message": "Columns should carry three-part comments (business | source | logic)."},
}

DIALECT_RULE_DEFAULTS: Dict[str, Dict[str, str]] = {
    # StarRocks INSERT legally omits PARTITION (auto routing): engine-legal,
    # team policy downgraded to warn by default in the dialect pack.
    "starrocks": {"insert-requires-partition": "warn"},
}

_INSERT_RE = re.compile(r"\binsert\s+(?:overwrite\s+)?(?:into\s+)?(?:table\s+)?", re.I)
_PARTITION_RE = re.compile(r"\bpartition\s*[(=]", re.I)
_UPDATE_RE = re.compile(r"\bupdate\s+[\w.`\[\]\"]+", re.I)
_DELETE_RE = re.compile(r"\bdelete\s+from\s+[\w.`\[\]\"]+", re.I)
_WHERE_RE = re.compile(r"\bwhere\b", re.I)
_CREATE_RE = re.compile(r"\bcreate\s+(?:external\s+)?table\b", re.I)
_DT_PARTITION_RE = re.compile(r"\bpartitioned\s+by\s*\(([^)]*)\)", re.I | re.S)
_DT_COL_RE = re.compile(r"^\s*(\w+)\s+(string|varchar)", re.I)


def lint_sql(sql: str, dialect: str, config: Optional[HarnessConfig] = None) -> LintResult:
    config = config or HarnessConfig.load()
    result = LintResult(dialect=dialect)
    statements, problems = scan_sql(sql)
    for problem in problems:
        result.parse_problems.append({"line": problem.line, "message": problem.message})
        result.issues.append(Issue("sql-parse", problem.line, "warn",
                                   f"Could not fully parse statement: {problem.message}",
                                   kind="engine", dialect=dialect, unresolved=True))
    for statement in statements:
        result.issues.extend(_check_statement(statement, dialect, config))
    _deep_parse(sql, dialect, result)
    kept: List[Issue] = []
    for issue in result.issues:
        default = DIALECT_RULE_DEFAULTS.get(dialect, {}).get(issue.rule) or RULE_REGISTRY[issue.rule]["level"]
        level = config.rule_level(issue.rule, default, dialect)
        if level == "off":
            continue
        issue.severity = level
        kept.append(issue)
    result.issues = kept
    return result


def _check_statement(st: Statement, dialect: str, config: HarnessConfig) -> List[Issue]:
    issues: List[Issue] = []
    code = st.code
    issues.extend(_select_star_issues(st, dialect))
    has_insert = _INSERT_RE.search(code)
    if has_insert and not _PARTITION_RE.search(code):
        issues.append(Issue("insert-requires-partition", st.start_line, "error",
                            RULE_REGISTRY["insert-requires-partition"]["message"], "policy", dialect))
    if _UPDATE_RE.search(code) and not _WHERE_RE.search(code):
        issues.append(Issue("dml-requires-where", st.start_line, "error",
                            RULE_REGISTRY["dml-requires-where"]["message"], "engine", dialect))
    if _DELETE_RE.search(code) and not _WHERE_RE.search(code):
        issues.append(Issue("dml-requires-where", st.start_line, "error",
                            RULE_REGISTRY["dml-requires-where"]["message"], "engine", dialect))
    part = _DT_PARTITION_RE.search(code)
    if part:
        for col_def in part.group(1).split(","):
            m = _DT_COL_RE.match(col_def)
            if m and m.group(1).lower() == "dt":
                issues.append(Issue("partition-name", st.start_line, "error",
                                    "Partition column must be named partition_dt (configured), not dt.",
                                    "policy", dialect))
    if _CREATE_RE.search(code):
        if dialect == "spark" and not re.search(r"\busing\s+\w+|\bstored\s+as\b", code, re.I):
            issues.append(Issue("spark-create-format", st.start_line, "warn",
                                RULE_REGISTRY["spark-create-format"]["message"], "engine", dialect))
        if dialect == "hive" and not re.search(r"\bstored\s+as\b", code, re.I):
            issues.append(Issue("hive-create-format", st.start_line, "warn",
                                RULE_REGISTRY["hive-create-format"]["message"], "engine", dialect))
        if dialect == "starrocks":
            if not re.search(r"\b(primary|duplicate|unique)\s+key\b", code, re.I):
                issues.append(Issue("sr-table-key", st.start_line, "warn",
                                    RULE_REGISTRY["sr-table-key"]["message"], "engine", dialect))
            if not re.search(r"\bdistributed\s+by\b", code, re.I):
                issues.append(Issue("sr-distributed-by", st.start_line, "warn",
                                    RULE_REGISTRY["sr-distributed-by"]["message"], "engine", dialect))
    issues.extend(_money_issues(code, dialect, config))
    return issues


def _select_star_issues(st: Statement, dialect: str) -> List[Issue]:
    """Flag `SELECT *`, `SELECT t.*`, `SELECT DISTINCT t.*` at any nesting.

    COUNT(*) sits inside its call's parentheses and never matches; arithmetic
    like `price * 2` has an identifier before `*`, not a list boundary.
    """
    issues: List[Issue] = []
    code = st.code
    for start, end in iter_select_clauses(code):
        head = code[start:end]
        m = re.match(r"\s*select\b(?:\s+distinct\b)?", head, re.I)
        if not m:
            continue
        i = start + m.end()
        depth = 0
        prev = ""  # last non-space char seen at depth 0
        while i < end:
            ch = code[i]
            if ch == "(":
                depth += 1
                i += 1
                continue
            if ch == ")":
                depth = max(0, depth - 1)
                if depth == 0:
                    prev = ")"
                i += 1
                continue
            if depth == 0:
                if ch == "*" and (prev == "." or prev in ("", ",")):
                    line = st.start_line + code.count("\n", 0, i)
                    issues.append(Issue("no-select-star", line, "error",
                                        RULE_REGISTRY["no-select-star"]["message"],
                                        "policy", dialect))
                if not ch.isspace():
                    prev = ch
            i += 1
    return issues


def _money_issues(code: str, dialect: str, config: HarnessConfig) -> List[Issue]:
    issues: List[Issue] = []
    pattern = re.compile(r"\b(" + config.money_fields_pattern + r")\w*\b", re.I)
    for lineno, line in enumerate(RE_LINE.split(code), start=1):
        if not pattern.search(line):
            continue
        if re.search(r"\bdouble\b", line, re.I):
            issues.append(Issue("money-decimal", lineno, "error",
                                "Money columns must use DECIMAL(20,4), not DOUBLE.", "policy", dialect))
            continue
        m = re.search(r"\bdecimal\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", line, re.I)
        if m:
            precision, scale = int(m.group(1)), int(m.group(2))
            if precision < 20 or scale < 4:
                issues.append(Issue("money-precision", lineno, "warn",
                                    f"Money column DECIMAL({precision},{scale}) below team standard (20,4).",
                                    "policy", dialect))
    return issues


def _deep_parse(sql: str, dialect: str, result: LintResult) -> None:
    """Optional sqlglot deep parse: marks unparseable SQL instead of guessing."""
    try:
        import sqlglot  # type: ignore
    except ImportError:
        return
    dialect_map = {"odps": "hive", "hive": "hive", "spark": "spark", "starrocks": ""}
    try:
        sqlglot.parse(sql, read=dialect_map.get(dialect) or None)
        result.deep_parse = "ok"
    except Exception as exc:  # sqlglot raises many error types
        result.deep_parse = "failed"
        result.issues.append(Issue("sql-deep-parse", 1, "warn",
                                   f"sqlglot could not parse this SQL ({type(exc).__name__}); "
                                   f"result based on offline scanner only. Hive-near parsing does not "
                                   f"replace MaxCompute validation.",
                                   kind="engine", dialect=dialect, unresolved=True))
