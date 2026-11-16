"""CREATE TABLE parsing and DDL -> ALTER candidate generation.

Parsing is line/regex based and deliberately conservative: anything the
parser cannot prove is reported as ``unresolved`` instead of guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .sqlsplit import scan_sql

_TYPE_RE = re.compile(r"^([A-Za-z]+)\s*(?:\(\s*(\d+)\s*(?:,\s*(\d+))?\s*\))?")
_COL_RE = re.compile(r"^\s*[`\[]?(\w+)[`\]]?\s+([A-Za-z]+(?:\s*\(\s*\d+\s*(?:,\s*\d+)?\s*\))?)", re.S)
_COMMENT_RE = re.compile(r"comment\s+(?:'((?:[^']|'')*)'|\"([^\"]*)\")", re.I)

INT_FAMILY = {"tinyint": 1, "smallint": 2, "int": 3, "integer": 3, "bigint": 4}
NUMERIC_FAMILY = {"decimal", "numeric"}


@dataclass
class Column:
    name: str
    raw_type: str
    family: str = ""
    precision: Optional[int] = None
    scale: Optional[int] = None
    nullable: bool = True
    comment: str = ""

    def type_key(self) -> str:
        if self.family in NUMERIC_FAMILY and self.precision is not None:
            return f"{self.family}({self.precision},{self.scale or 0})"
        return self.family or self.raw_type.lower()


@dataclass
class TableDDL:
    table: str
    columns: List[Column] = field(default_factory=list)
    partition_columns: List[Column] = field(default_factory=list)
    primary_key: List[str] = field(default_factory=list)
    distributed_by: str = ""
    dialect: str = "odps"
    unresolved: List[str] = field(default_factory=list)

    def find(self, name: str) -> Optional[Column]:
        low = name.lower()
        for col in self.columns:
            if col.name.lower() == low:
                return col
        return None


def parse_type(raw: str) -> Column:
    m = _TYPE_RE.match(raw.strip().lower())
    family = m.group(1) if m else raw.strip().lower()
    precision = int(m.group(2)) if (m and m.group(2)) else None
    scale = int(m.group(3)) if (m and m.group(3)) else None
    return Column(name="", raw_type=raw.strip(), family=family,
                  precision=precision, scale=scale)


def parse_create_table(sql: str, dialect: str = "odps") -> List[TableDDL]:
    tables: List[TableDDL] = []
    for statement in scan_sql(sql)[0]:
        code = statement.code
        head = re.search(r"\bcreate\s+(?:external\s+)?table\s+(?:if\s+not\s+exists\s+)?[\w.`\[\]\"']*?([\w.`\[\]\"]+)", code, re.I)
        if not head:
            continue
        table = head.group(1).strip("`[]\"'")
        ddl = TableDDL(table=table, dialect=dialect)
        body = _outer_parens(code)
        if body is None:
            ddl.unresolved.append("could not locate column list body")
            tables.append(ddl)
            continue
        part = re.search(r"\bpartitioned\s+by\s*\(([^)]*)\)", code, re.I | re.S)
        if part:
            for chunk in _split_top_commas(part.group(1)):
                m = _COL_RE.match(chunk)
                if m:
                    col = parse_type(m.group(2))
                    col.name = m.group(1)
                    ddl.partition_columns.append(col)
        pk = re.search(r"\bprimary\s+key\s*\(([^)]*)\)", code, re.I)
        if pk:
            ddl.primary_key = [c.strip().strip("`[]\"'") for c in pk.group(1).split(",") if c.strip()]
        dist = re.search(r"\bdistributed\s+by\s+hash\s*\(([^)]*)\)", code, re.I)
        if dist:
            ddl.distributed_by = dist.group(1).strip()
        for chunk in _split_top_commas(body):
            low = chunk.strip().lower()
            if not low:
                continue
            if re.match(r"^(primary|unique|duplicate|clustered|sorted|partitioned|distributed|comment|with|tblproperties|lifecycle|stored|row\s+format|location|using)\b", low):
                continue
            m = _COL_RE.match(chunk)
            if not m:
                ddl.unresolved.append(f"unrecognized column clause: {chunk.strip()[:60]}")
                continue
            col = parse_type(m.group(2))
            col.name = m.group(1)
            col.nullable = not re.search(r"\bnot\s+null\b", chunk, re.I)
            cm = _COMMENT_RE.search(chunk)
            if cm:
                col.comment = (cm.group(1) or cm.group(2) or "").replace("''", "'")
            ddl.columns.append(col)
        tables.append(ddl)
    return tables


def _outer_parens(code: str) -> Optional[str]:
    start = code.find("(")
    if start < 0:
        return None
    depth = 0
    for idx in range(start, len(code)):
        if code[idx] == "(":
            depth += 1
        elif code[idx] == ")":
            depth -= 1
            if depth == 0:
                return code[start + 1: idx]
    return None


def _split_top_commas(body: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    cur: List[str] = []
    in_str = None
    i = 0
    while i < len(body):
        ch = body[i]
        if in_str:
            cur.append(ch)
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in "'\"`":
            in_str = ch
            cur.append(ch)
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    if cur:
        parts.append("".join(cur))
    return parts


def is_narrowing(before: Column, after: Column) -> bool:
    bf, af = before.family, after.family
    if bf in INT_FAMILY and af in INT_FAMILY:
        return INT_FAMILY[af] < INT_FAMILY[bf]
    if bf in NUMERIC_FAMILY and af in NUMERIC_FAMILY:
        if before.precision and after.precision and after.precision < before.precision:
            return True
        if before.scale is not None and after.scale is not None and after.scale < before.scale:
            return True
        return False
    if bf in NUMERIC_FAMILY and af in {"double", "float"}:
        return False  # widening in magnitude, precision semantics change
    if bf != af:
        return True  # cross-family: assume risky
    return False


@dataclass
class DDLChange:
    kind: str  # add_column | widen | narrow | remove_column | key_change | partition_change | unresolved
    column: str = ""
    detail: str = ""
    candidate_sql: str = ""


def diff_ddl(before: TableDDL, after: TableDDL, allow_narrowing: bool = False) -> List[DDLChange]:
    changes: List[DDLChange] = []
    before_names = {c.name.lower(): c for c in before.columns}
    after_names = {c.name.lower(): c for c in after.columns}
    for name, col in after_names.items():
        if name not in before_names:
            comment = f" COMMENT '{col.comment}'" if col.comment else ""
            if after.dialect == "starrocks":
                sql = f"ALTER TABLE {after.table} ADD COLUMN {col.name} {col.raw_type}{comment}"
            else:
                sql = f"ALTER TABLE {after.table} ADD COLUMNS ({col.name} {col.raw_type}{comment})"
            changes.append(DDLChange("add_column", col.name, f"new column {col.name} {col.raw_type}", sql))
    for name, col in before_names.items():
        if name not in after_names:
            changes.append(DDLChange("remove_column", col.name,
                                     f"column {name} removed; destructive — requires rebuild/switch plan, "
                                     f"or explicit --allow-narrowing to emit DROP COLUMN"))
            if allow_narrowing:
                sql = f"ALTER TABLE {before.table} DROP COLUMN {col.name}"
                changes[-1].candidate_sql = sql
        else:
            new = after_names[name]
            if new.type_key() != col.type_key():
                if is_narrowing(col, new):
                    detail = (f"{col.type_key()} -> {new.type_key()} narrows value space "
                              f"(precision/scale/int-width)")
                    if allow_narrowing:
                        if after.dialect == "starrocks":
                            sql = f"ALTER TABLE {after.table} MODIFY COLUMN {new.name} {new.raw_type}"
                        else:
                            sql = (f"ALTER TABLE {after.table} CHANGE COLUMN {new.name} {new.name} "
                                   f"{new.raw_type}" + (f" COMMENT '{new.comment}'" if new.comment else ""))
                        changes.append(DDLChange("narrow", col.name, detail, sql))
                    else:
                        changes.append(DDLChange("narrow", col.name, detail))
                else:
                    if after.dialect == "starrocks":
                        sql = f"ALTER TABLE {after.table} MODIFY COLUMN {new.name} {new.raw_type}"
                    else:
                        sql = (f"ALTER TABLE {after.table} CHANGE COLUMN {new.name} {new.name} "
                               f"{new.raw_type}" + (f" COMMENT '{new.comment}'" if new.comment else ""))
                    changes.append(DDLChange("widen", col.name,
                                             f"{col.type_key()} -> {new.type_key()}", sql))
    if {c.name.lower() for c in before.partition_columns} != {c.name.lower() for c in after.partition_columns}:
        changes.append(DDLChange("partition_change", detail="partition column set changed; "
                                "requires rebuild/switch/backfill plan"))
    if [k.lower() for k in before.primary_key] != [k.lower() for k in after.primary_key]:
        changes.append(DDLChange("key_change", detail="primary key changed; "
                                "requires rebuild/switch/verify/recover plan"))
    return changes


REBUILD_STEPS = [
    "1. create shadow table with target DDL (_new suffix)",
    "2. dual-write or backfill data from current table (per partition, idempotent INSERT OVERWRITE)",
    "3. verify: row counts per partition + business-key checksums via `dw reconcile`",
    "4. switch: atomic rename / view swap during a write freeze window",
    "5. recover: keep old table N days as rollback point; record in migration decision",
]
