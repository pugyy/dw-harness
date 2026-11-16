"""dw plan: DDL migration candidates and backfill rehearsal (read-only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .ddl import DDLChange, REBUILD_STEPS, TableDDL, diff_ddl, parse_create_table


@dataclass
class DDLPlan:
    table: str
    dialect: str
    candidates: List[Dict] = field(default_factory=list)
    risks: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"table": self.table, "dialect": self.dialect,
                "candidates": self.candidates, "risks": self.risks}


def plan_ddl(before_sql: str, after_sql: str, dialect: str = "odps",
             allow_narrowing: bool = False) -> DDLPlan:
    before = parse_create_table(before_sql, dialect)
    after = parse_create_table(after_sql, dialect)
    if not before or not after:
        raise ValueError("could not parse a CREATE TABLE from one of the DDL inputs")
    plan = DDLPlan(table=after[0].table, dialect=dialect)
    for change in diff_ddl(before[0], after[0], allow_narrowing=allow_narrowing):
        entry = {"kind": change.kind, "column": change.column, "detail": change.detail}
        if change.candidate_sql:
            entry["sql"] = change.candidate_sql
        if change.kind in ("add_column", "widen"):
            plan.candidates.append(entry)
        elif change.kind in ("narrow", "remove_column", "key_change", "partition_change"):
            if change.candidate_sql:
                entry["sql"] = change.candidate_sql
                entry["note"] = ("emitted because --allow-narrowing was given; "
                                 "verify data compatibility before running")
                plan.candidates.append(entry)
            entry_risk = dict(entry)
            entry_risk["steps"] = REBUILD_STEPS
            plan.risks.append(entry_risk)
    return plan


@dataclass
class BackfillPlan:
    environment: str
    table: str
    partition_start: str
    partition_end: str
    idempotency: str
    checkpoints: str
    scan_estimation: Dict
    readonly: bool = True
    recover: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "environment": self.environment, "table": self.table,
            "partition_range": [self.partition_start, self.partition_end],
            "idempotency": self.idempotency,
            "checkpoints": self.checkpoints,
            "scan_estimation": self.scan_estimation,
            "readonly": self.readonly,
            "recover": self.recover,
        }


def plan_backfill(table: str, partition_start: str, partition_end: str,
                  insert_sql: str = "", environment: str = "dev",
                  cost_sql_available: bool = False) -> BackfillPlan:
    estimation: Dict = {"status": "unknown", "detail": "COST SQL not executed in preview mode"}
    if insert_sql:
        estimation["cost_sql"] = f"COST SQL {insert_sql.strip().splitlines()[0][:200]}"
        estimation["note"] = ("run via your MaxCompute client to obtain an estimate; "
                              "StarRocks EXPLAIN ANALYZE executes the statement and must "
                              "stay outside preview")
    plan = BackfillPlan(
        environment=environment,
        table=table,
        partition_start=partition_start,
        partition_end=partition_end,
        idempotency="INSERT OVERWRITE per partition: re-running a partition replaces it fully; "
                    "never mix INSERT INTO into a backfill",
        checkpoints=f".claude/dw/backfill/{table}.json — one entry per partition: "
                    f"pending | running | done | failed",
        scan_estimation=estimation,
        recover=[
            "keep the pre-backfill snapshot of each partition (or the source retention window) "
            "for the duration of the backfill",
            "a failed partition is re-runnable idempotently; a wrong-value backfill is restored "
            "by re-running the corrected SQL over the same range",
        ],
    )
    return plan
