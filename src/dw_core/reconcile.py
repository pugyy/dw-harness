"""dw reconcile: key-level reconciliation with Decimal money semantics.

Adapters: file (CSV fixtures, full offline demo), MaxCompute, StarRocks.
Database adapters use parameter binding for values and a strict identifier
allowlist for table/partition names (identifiers cannot be bound); read-only
credentials come exclusively from environment variables.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Tuple

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,2}$")
UNIT_FACTORS = {  # to the smallest unit (fen) for CNY-style scaling
    "fen": Decimal(1), "cent": Decimal(1), "yuan": Decimal(100),
    "qian_yuan": Decimal(100000), "thousand": Decimal(100000),
    "million": Decimal(100000000),
}


@dataclass
class ReconcileSpec:
    left: Dict                      # {adapter, path|table, partition}
    right: Dict
    keys: List[str]
    metrics: List[Dict]             # {column, abs_tol, rel_tol, unit_left, unit_right}
    sample_rows: int = 20
    max_rows: int = 1000000

    def to_dict(self) -> Dict:
        return {"left": self.left, "right": self.right, "keys": self.keys,
                "metrics": self.metrics, "sample_rows": self.sample_rows,
                "max_rows": self.max_rows}

    @classmethod
    def load(cls, path: Path) -> Tuple[Dict, "ReconcileSpec"]:
        import json
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raise ValueError("reconciliation spec must be an object")
        fields = ("left", "right", "keys", "metrics", "sample_rows", "max_rows")
        spec = cls(**{k: raw[k] for k in fields if k in raw})
        for side in ("left", "right"):
            desc = getattr(spec, side)
            if not isinstance(desc, dict):
                raise ValueError(f"{side} must be an object")
            if desc.get("adapter", "file") == "file" and desc.get("path"):
                desc = {**desc, "path": str((path.resolve().parent / desc["path"]).resolve())}
                setattr(spec, side, desc)
        return raw, spec

    def evidence_scope(self, table: str) -> Dict:
        if not isinstance(table, str) or not IDENT_RE.fullmatch(table):
            raise ReconcileError("an explicit target table is required for evidence")
        offline = self.right.get("adapter", "file") == "file"
        environment = "offline" if offline else self.right.get("environment")
        if not offline and (not environment or environment == "offline"):
            raise ReconcileError("right.environment must identify the database environment")
        if not offline and self.right.get("table") != table:
            raise ReconcileError("right.table must match the evidence target")
        partition = self.right.get("partition")
        if not isinstance(partition, str) or not partition.strip():
            raise ReconcileError("right.partition is required for evidence")
        return {"table": table, "environment": environment, "partition": partition}

    def file_inputs(self) -> Dict[str, Path]:
        return {f"reconcile:{side}:file": Path(desc["path"])
                for side, desc in (("left", self.left), ("right", self.right))
                if desc.get("adapter", "file") == "file"}


class ReconcileError(Exception):
    pass


def _to_decimal(raw) -> Optional[Decimal]:
    if raw is None or raw == "":
        return None
    try:
        value = Decimal(str(raw).strip().replace(",", ""))
        if not value.is_finite():
            raise InvalidOperation
        return value
    except (InvalidOperation, ValueError):
        raise ReconcileError(f"value not numeric: {raw!r}")


class FileAdapter:
    kind = "file"

    def __init__(self, desc: Dict, keys: List[str], metrics: List[str]):
        self.path = Path(desc["path"])
        self.partition = desc.get("partition", "")
        self.keys = keys
        self.metrics = metrics

    def partition_exists(self) -> bool:
        return self.path.is_file()

    def fetch(self, limit: int) -> Tuple[List[Dict], bool]:
        rows: List[Dict] = []
        truncated = False
        with self.path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            headers = [name.strip() for name in (reader.fieldnames or [])]
            missing = sorted(set(self.keys + self.metrics) - set(headers))
            if missing:
                raise ReconcileError(f"missing required CSV columns: {', '.join(missing)}")
            if len(set(headers)) != len(headers):
                raise ReconcileError("duplicate CSV headers")
            reader.fieldnames = headers
            for row in reader:
                if None in row or any(v is None for v in row.values()):
                    raise ReconcileError(f"CSV row {reader.line_num} does not match its header")
                rows.append(row)
                if len(rows) > limit:
                    truncated = True
                    break
        return rows, truncated


def _q(identifier: str) -> str:
    """Re-validate an identifier against the allowlist before it may appear
    in a query string. Identifiers cannot be parameter-bound; values can and
    always are. Raises instead of returning anything unvalidated."""
    if not IDENT_RE.match(identifier or ""):
        raise ReconcileError(f"identifier rejected (allowlist): {identifier!r}")
    return identifier


def _quoted(identifier: str) -> str:
    return ".".join(f"`{part}`" for part in _q(identifier).split("."))


class _DbAdapter:
    kind = "db"

    def __init__(self, desc: Dict, keys: List[str], metrics: List[str], timeout: int = 60):
        self.table = desc["table"]
        self.partition = desc.get("partition", "")
        self.partition_column = desc.get("partition_column", "partition_dt")
        self.partition_name = desc.get("partition_name")
        self.keys = keys
        self.metrics = metrics
        self.timeout = timeout
        for ident in [self.table, self.partition_column, *keys, *metrics]:
            _q(ident)

    def partition_exists(self) -> bool:
        """Metadata-level check: is the partition present at all?

        COUNT cannot distinguish 'missing' from 'present but empty'; adapters
        must consult metadata (audit R6). Value is parameter-bound where the
        query is SQL; identifiers stay allowlist-validated.
        """
        exists = self._partition_in_metadata()
        if exists is None:
            raise ReconcileError(
                f"partition existence undeterminable for {self.table}")
        return exists

    def partition_count(self) -> Optional[int]:
        raise ReconcileError("partition_count not implemented for this adapter")

    def _partition_in_metadata(self) -> Optional[bool]:
        raise ReconcileError("partition metadata not implemented for this adapter")


class MaxComputeAdapter(_DbAdapter):
    def _connect(self):
        try:
            from odps import ODPS  # type: ignore
        except ImportError as exc:
            raise ReconcileError(
                "MaxCompute adapter needs the optional pyodps capability "
                "(pip install dw-harness[odps]) and read-only credentials from "
                "DW_HARNESS_ODPS_ACCESS_ID / _ACCESS_KEY / _PROJECT / _ENDPOINT env vars") from exc
        import os
        for var in ("DW_HARNESS_ODPS_ACCESS_ID", "DW_HARNESS_ODPS_ACCESS_KEY",
                    "DW_HARNESS_ODPS_PROJECT", "DW_HARNESS_ODPS_ENDPOINT"):
            if not os.environ.get(var):
                raise ReconcileError(f"missing read-only credential env var: {var}")
        return ODPS(os.environ["DW_HARNESS_ODPS_ACCESS_ID"],
                    os.environ["DW_HARNESS_ODPS_ACCESS_KEY"],
                    project=os.environ["DW_HARNESS_ODPS_PROJECT"],
                    endpoint=os.environ["DW_HARNESS_ODPS_ENDPOINT"])

    def _partition_in_metadata(self) -> Optional[bool]:
        from odps.types import PartitionSpec
        table = self._connect().get_table(self.table)
        spec = PartitionSpec()
        spec[self.partition_column] = self.partition
        return bool(table.exist_partition(spec))

    def fetch(self, limit: int) -> Tuple[List[Dict], bool]:
        from odps import dbapi
        names = [*self.keys, *self.metrics]
        cols = ", ".join(_quoted(c) for c in names)
        sql = (f"SELECT {cols} FROM {_quoted(self.table)} "
               f"WHERE {_quoted(self.partition_column)} = ? LIMIT ?")
        conn = dbapi.connect(self._connect())
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, (self.partition, limit + 1))
                rows = [dict(zip(names, row)) for row in cursor.fetchmany(limit + 1)]
            finally:
                cursor.close()
        finally:
            conn.close()
        return rows[:limit], len(rows) > limit


class StarRocksAdapter(_DbAdapter):
    def _connect(self):
        try:
            import pymysql  # type: ignore
        except ImportError as exc:
            raise ReconcileError(
                "StarRocks adapter needs the optional pymysql capability "
                "(pip install dw-harness[sr]) and read-only credentials from "
                "DW_HARNESS_SR_HOST / _PORT / _USER / _PASSWORD / _DATABASE env vars") from exc
        import os
        for var in ("DW_HARNESS_SR_HOST", "DW_HARNESS_SR_USER",
                    "DW_HARNESS_SR_PASSWORD", "DW_HARNESS_SR_DATABASE"):
            if not os.environ.get(var):
                raise ReconcileError(f"missing read-only credential env var: {var}")
        return pymysql.connect(
            host=os.environ["DW_HARNESS_SR_HOST"],
            port=int(os.environ.get("DW_HARNESS_SR_PORT", "9030")),
            user=os.environ["DW_HARNESS_SR_USER"],
            password=os.environ["DW_HARNESS_SR_PASSWORD"],
            database=os.environ["DW_HARNESS_SR_DATABASE"],
            connect_timeout=self.timeout,
            read_timeout=self.timeout,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def _partition_in_metadata(self) -> Optional[bool]:
        # StarRocks returns PartitionName and Range, rather than Hive-style
        # partition key/value strings. An explicit partition name supports
        # projects with a custom naming policy.
        names = [self.partition_name] if self.partition_name else [self.partition, f"p{self.partition}"]
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                for name in names:
                    cursor.execute(f"SHOW PARTITIONS FROM {_quoted(self.table)} WHERE PartitionName = %s",
                                   (name,))
                    if any(row.get("PartitionName") == name for row in cursor.fetchall()):
                        return True
                return False
        finally:
            conn.close()

    def fetch(self, limit: int) -> Tuple[List[Dict], bool]:
        conn = self._connect()
        cols = ", ".join(_quoted(c) for c in [*self.keys, *self.metrics])
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT {cols} FROM {_quoted(self.table)} "
                    f"WHERE {_quoted(self.partition_column)} = %s LIMIT %s",
                    (self.partition, limit + 1))  # parameter binding, no string assembly
                rows = cursor.fetchall()
        finally:
            conn.close()
        return rows[:limit], len(rows) > limit


ADAPTERS = {"file": FileAdapter, "maxcompute": MaxComputeAdapter, "starrocks": StarRocksAdapter}


def _key_of(row: Dict, keys: List[str]) -> Tuple:
    return tuple(_key_part(row.get(k)) for k in keys)


def _key_part(value) -> str:
    return "" if value is None else str(value).strip()


def _unit_factor(unit: Optional[str]) -> Decimal:
    return UNIT_FACTORS.get((unit or "").lower(), Decimal(1))


@dataclass
class ReconcileResult:
    status: str  # pass | fail | unverified
    reasons: List[str] = field(default_factory=list)
    prechecks: Dict = field(default_factory=dict)
    totals: Dict = field(default_factory=dict)
    diffs: List[Dict] = field(default_factory=list)
    null_mismatches: List[Dict] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> Dict:
        return {"status": self.status, "reasons": self.reasons,
                "prechecks": self.prechecks, "totals": self.totals,
                "diffs": self.diffs, "null_mismatches": self.null_mismatches,
                "truncated": self.truncated}


def reconcile(spec: ReconcileSpec) -> ReconcileResult:
    result = ReconcileResult(status="unverified", reasons=[])
    try:
        metric_cols = [m["column"] for m in spec.metrics]
        if (not isinstance(spec.keys, list) or not spec.keys or not metric_cols
                or not all(isinstance(col, str) and col for col in spec.keys + metric_cols)
                or any(type(n) is not int or n <= 0 for n in (spec.sample_rows, spec.max_rows))):
            raise ValueError("keys, metrics, sample_rows and max_rows must be nonempty")
        if not isinstance(spec.left, dict) or not isinstance(spec.right, dict):
            raise ValueError("left and right must be objects")
        for metric in spec.metrics:
            for key in ("abs_tol", "rel_tol"):
                value = _to_decimal(metric.get(key, 0))
                if value is None or value < 0:
                    raise ValueError(f"{key} must be nonnegative")
            for key in ("unit_left", "unit_right"):
                if metric.get(key) and str(metric[key]).lower() not in UNIT_FACTORS:
                    raise ValueError(f"unsupported reconciliation unit: {metric[key]}")
    except (KeyError, TypeError, ValueError, ReconcileError) as exc:
        result.reasons.append(f"invalid reconciliation spec: {exc}")
        return result
    left_desc = spec.left or {}
    right_desc = spec.right or {}
    try:
        left_ad = ADAPTERS[left_desc.get("adapter", "file")](left_desc, spec.keys, metric_cols)
        right_ad = ADAPTERS[right_desc.get("adapter", "file")](right_desc, spec.keys, metric_cols)
    except KeyError as exc:
        result.reasons.append(f"unknown adapter: {exc}")
        return result
    except ReconcileError as exc:  # bad identifiers, missing required fields
        result.reasons.append(f"adapter rejected the spec: {exc}")
        return result
    except (TypeError, ValueError) as exc:  # malformed spec shapes
        result.reasons.append(f"spec malformed: {type(exc).__name__}: {exc}")
        return result

    def _partition_present(adapter, side: str) -> Optional[bool]:
        """None = existence undeterminable (missing credentials, metadata
        query failure...): a distinguishable UNVERIFIED, never a traceback."""
        try:
            return adapter.partition_exists()
        except ReconcileError as exc:
            result.reasons.append(f"{side} partition check failed: {exc}")
        except Exception as exc:  # driver errors (timeout, auth, schema)
            result.reasons.append(f"{side} partition check failed: "
                                  f"{type(exc).__name__}: {exc}")
        return None

    left_present = _partition_present(left_ad, "left")
    if left_present is None:
        return result
    right_present = _partition_present(right_ad, "right")
    if right_present is None:
        return result
    if not left_present:
        result.reasons.append(f"left partition missing/unreadable: {spec.left.get('path', spec.left.get('table'))}")
        return result
    if not right_present:
        result.reasons.append(f"right partition missing/unreadable: {spec.right.get('path', spec.right.get('table'))}")
        return result
    try:
        left_rows, trunc_l = left_ad.fetch(spec.max_rows)
        right_rows, trunc_r = right_ad.fetch(spec.max_rows)
        for side, rows in (("left", left_rows), ("right", right_rows)):
            for row in rows:
                missing = set(spec.keys + metric_cols) - row.keys()
                if missing:
                    raise ReconcileError(f"{side} missing columns: {', '.join(sorted(missing))}")
                for col in metric_cols:
                    _to_decimal(row[col])
    except ReconcileError as exc:
        result.reasons.append(f"adapter error: {exc}")
        return result
    except Exception as exc:  # driver errors (timeout, auth, limit)
        result.reasons.append(f"query failed: {type(exc).__name__}: {exc}")
        return result
    result.truncated = trunc_l or trunc_r
    if result.truncated:
        result.reasons.append(f"row limit ({spec.max_rows}) exceeded; result unverified")

    left_map: Dict[Tuple, Dict] = {}
    dup_l: Dict[Tuple, int] = {}
    for row in left_rows:
        key = _key_of(row, spec.keys)
        dup_l[key] = dup_l.get(key, 0) + 1
        left_map[key] = row
    right_map: Dict[Tuple, Dict] = {}
    dup_r: Dict[Tuple, int] = {}
    for row in right_rows:
        key = _key_of(row, spec.keys)
        dup_r[key] = dup_r.get(key, 0) + 1
        right_map[key] = row
    empty_l = sum(1 for k in left_map if all(v == "" for v in k))
    empty_r = sum(1 for k in right_map if all(v == "" for v in k))
    dups = {"left": {str(k): c for k, c in dup_l.items() if c > 1},
            "right": {str(k): c for k, c in dup_r.items() if c > 1}}
    missing_left = [str(k) for k in right_map if k not in left_map]
    missing_right = [str(k) for k in left_map if k not in right_map]
    result.prechecks = {
        "rows": {"left": len(left_rows), "right": len(right_rows)},
        "empty_keys": {"left": empty_l, "right": empty_r},
        "duplicate_keys": dups,
        "keys_missing_on_left": missing_left[:spec.sample_rows],
        "keys_missing_on_right": missing_right[:spec.sample_rows],
    }
    if dups["left"] or dups["right"]:
        result.status = "fail"
        result.reasons.append("duplicate business keys found; fix duplicates before reconciling")
        return result
    if empty_l or empty_r:
        result.status = "fail"
        result.reasons.append("empty business keys found")
        return result

    totals: Dict[str, Dict] = {}
    for metric in spec.metrics:
        col = metric["column"]
        fl = _unit_factor(metric.get("unit_left"))
        fr = _unit_factor(metric.get("unit_right"))
        sum_l = sum((v for v in (_to_decimal(r.get(col)) for r in left_rows) if v is not None), Decimal(0)) * fl
        sum_r = sum((v for v in (_to_decimal(r.get(col)) for r in right_rows) if v is not None), Decimal(0)) * fr
        totals[col] = {"left_base_unit": str(sum_l), "right_base_unit": str(sum_r),
                       "delta_base_unit": str(sum_r - sum_l)}

    diffs: List[Dict] = []
    null_mis: List[Dict] = []
    for key in sorted(set(left_map) & set(right_map)):
        for metric in spec.metrics:
            col = metric["column"]
            lv = _to_decimal(left_map[key].get(col)) if left_map[key].get(col) not in (None, "") else None
            rv = _to_decimal(right_map[key].get(col)) if right_map[key].get(col) not in (None, "") else None
            fl = _unit_factor(metric.get("unit_left"))
            fr = _unit_factor(metric.get("unit_right"))
            if lv is None and rv is None:
                continue  # NULL == NULL: equal by contract semantics
            if lv is None or rv is None:
                null_mis.append({"key": str(key), "column": col,
                                 "left": "NULL" if lv is None else str(lv * fl),
                                 "right": "NULL" if rv is None else str(rv * fr)})
                continue
            lbase, rbase = lv * fl, rv * fr
            delta = rbase - lbase
            # abs_tol is expressed in LEFT-side units; rel_tol is unit-free
            abs_tol = Decimal(str(metric.get("abs_tol", "0"))) * fl
            rel_tol = Decimal(str(metric.get("rel_tol", "0")))
            tolerance = max(abs_tol, rel_tol * max(abs(lbase), abs(rbase)))
            zero_baseline = (lbase == 0 or rbase == 0)
            if delta == 0:
                continue
            if zero_baseline:
                diffs.append({"key": str(key), "column": col,
                              "left": str(lbase), "right": str(rbase),
                              "delta": str(delta), "tolerance": "zero-baseline: any nonzero delta fails"})
            elif abs(delta) > tolerance:
                diffs.append({"key": str(key), "column": col,
                              "left": str(lbase), "right": str(rbase),
                              "delta": str(delta), "tolerance": str(tolerance)})
            if len(diffs) >= spec.sample_rows:
                break
        if len(diffs) >= spec.sample_rows:
            break
    result.totals = totals
    result.diffs = diffs
    result.null_mismatches = null_mis[:spec.sample_rows]

    if result.truncated:
        # row limit hit: never upgrade to pass; distinguishable outcome (spec 14)
        result.status = "unverified"
        result.reasons.append("row limit reached: totals/key-level results computed on a "
                              "truncated window only")
        return result
    if missing_left or missing_right:
        result.status = "fail"
        result.reasons.append("business keys present on one side only")
    if null_mis:
        result.status = "fail"
        result.reasons.append("NULL vs value mismatches on money columns")
    if diffs:
        result.status = "fail"
        result.reasons.append(f"{len(diffs)} key-level difference(s) beyond tolerance "
                              f"(samples capped at {spec.sample_rows})")
    if result.status == "unverified":
        result.status = "pass"
        result.reasons.append("rows, totals and per-key comparisons within tolerance "
                              "over the full (untruncated) window")
    return result
