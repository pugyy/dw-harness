"""Versioned table contracts (contract.yaml / contract.json).

Authors edit YAML (requires the optional PyYAML capability) or JSON; the
runtime always consumes a normalized JSON form. Money keeps currency and
unit separate so "CNY in fen" vs "CNY in yuan" vs "CNY in thousands" are
distinct, provable contract facts.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import CONTRACT_SCHEMA
from .ddl import Column, TableDDL, is_narrowing, parse_type

VALID_UNITS = ("fen", "cent", "yuan", "qian_yuan", "thousand", "million", "share", "percent", "ratio")
VALID_CURRENCIES = ("CNY", "USD", "EUR", "JPY", "GBP", "HKD")
REQUIRED_TOP = ("contract_id", "owner", "granularity", "business_keys", "columns", "version")


class ContractError(Exception):
    pass


def _load_any(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ContractError(
                f"{path.name} is YAML but PyYAML is not installed; "
                f"install the optional capability (pip install dw-harness[yaml]) "
                f"or author the contract as .json") from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ContractError(f"{path.name}: contract must be a mapping")
    return data


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Canonical form: sorted keys, defaulted optionals, normalized columns."""
    columns = []
    for col in raw.get("columns", []):
        entry = {
            "name": str(col.get("name", "")),
            "type": str(col.get("type", "")).lower(),
        }
        for key in ("precision", "scale", "nullable", "caliber", "source"):
            if col.get(key) is not None:
                entry[key] = col[key]
        if col.get("currency") is not None:
            entry["currency"] = str(col["currency"]).upper()
        if col.get("unit") is not None:
            entry["unit"] = str(col["unit"]).lower()
        columns.append(entry)
    normalized = {
        "schema": CONTRACT_SCHEMA,
        "contract_id": str(raw.get("contract_id", "")),
        "table": str(raw.get("table") or raw.get("contract_id", "")),
        "version": str(raw.get("version", "1")),
        "owner": str(raw.get("owner", "")),
        "granularity": str(raw.get("granularity", "")),
        "business_keys": [str(k) for k in raw.get("business_keys", [])],
        "partition": raw.get("partition") or {},
        "columns": columns,
        "quality": raw.get("quality") or {},
        "sla": raw.get("sla") or {},
        "sources": [str(s) for s in raw.get("sources", [])],
        "digest": "",
    }
    normalized["partition"] = {
        "column": str(normalized["partition"].get("column", "")),
        "type": str(normalized["partition"].get("type", "")),
        "format": str(normalized["partition"].get("format", "")),
    }
    normalized["digest"] = _digest({k: v for k, v in normalized.items() if k != "digest"})
    return normalized


def validate_contract(normalized: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for key in REQUIRED_TOP:
        if not normalized.get(key):
            errors.append(f"missing required field: {key}")
    for col in normalized.get("columns", []):
        name = col.get("name", "")
        if not name:
            errors.append("column without a name")
        if col.get("currency") and col["currency"] not in VALID_CURRENCIES:
            errors.append(f"column {name}: unknown currency {col['currency']}")
        if col.get("unit") and col["unit"] not in VALID_UNITS:
            errors.append(f"column {name}: unknown unit {col['unit']} (expected one of {', '.join(VALID_UNITS)})")
        if col.get("currency") and not col.get("unit"):
            errors.append(f"column {name}: currency set without unit — unit must be explicit for money columns")
        if col.get("unit") and not col.get("currency"):
            errors.append(f"column {name}: unit set without currency")
    keys = [c["name"] for c in normalized.get("columns", []) if c.get("name")]
    for bk in normalized.get("business_keys", []):
        if bk not in keys:
            errors.append(f"business key {bk} not present in columns")
    part_col = normalized.get("partition", {}).get("column")
    if normalized.get("partition") and part_col and part_col not in keys and part_col != "":
        # partition column may live outside the column list; only flag typos of configured column
        pass
    return errors


def load_contract(path: Path) -> Tuple[Dict[str, Any], Path]:
    raw = _load_any(path)
    return normalize(raw), path


def compile_contract(path: Path, out: Optional[Path] = None) -> Path:
    normalized, _ = load_contract(path)
    errors = validate_contract(normalized)
    if errors:
        raise ContractError("contract invalid: " + "; ".join(errors))
    out = out or path.with_suffix("").with_name(path.stem + ".contract.json")
    out.write_text(json.dumps(normalized, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def compiled_is_fresh(source: Path, compiled: Path) -> bool:
    if not compiled.is_file():
        return False
    try:
        current, _ = load_contract(source)
        existing = json.loads(compiled.read_text(encoding="utf-8-sig"))
    except (ContractError, json.JSONDecodeError, OSError):
        return False
    return existing.get("digest") == current["digest"]


def _col_map(contract: Dict[str, Any]) -> Dict[str, Dict]:
    return {c["name"].lower(): c for c in contract.get("columns", [])}


def diff_contracts(current: Dict[str, Any], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Structural diff; unit/currency changes on money columns are breaking."""
    changes: List[Dict[str, Any]] = []
    cur, base = _col_map(current), _col_map(baseline)
    cid = current.get("contract_id") or baseline.get("contract_id") or ""
    for name, col in base.items():
        if name not in cur:
            changes.append({"field": f"columns.{name}", "type": "removed_column", "breaking": True,
                            "from": col.get("type"), "to": None,
                            "note": f"column {name} removed from contract {cid}"})
    for name, col in cur.items():
        old = base.get(name)
        if not old:
            changes.append({"field": f"columns.{name}", "type": "added_column", "breaking": False,
                            "from": None, "to": col.get("type"), "note": f"column {name} added"})
            continue
        if col.get("type") != old.get("type"):
            oldp, newp = parse_type(str(old.get("type", ""))), parse_type(str(col.get("type", "")))
            oldc = Column(old["name"], str(old.get("type", "")), oldp.family, oldp.precision, oldp.scale)
            newc = Column(col["name"], str(col.get("type", "")), newp.family, newp.precision, newp.scale)
            changes.append({
                "field": f"columns.{name}.type", "type": "type_narrowed" if is_narrowing(oldc, newc) else "type_changed",
                "breaking": is_narrowing(oldc, newc), "from": old.get("type"), "to": col.get("type"),
                "note": f"column {name} type {old.get('type')} -> {col.get('type')}"})
        if col.get("unit") != old.get("unit") or col.get("currency") != old.get("currency"):
            changes.append({
                "field": f"columns.{name}.unit", "type": "unit_changed", "breaking": True,
                "from": f"{old.get('currency', '-')}:{old.get('unit', '-')}",
                "to": f"{col.get('currency', '-')}:{col.get('unit', '-')}",
                "note": (f"money representation changed for {name}: "
                         f"{old.get('currency', '?')} in {old.get('unit', '?')} -> "
                         f"{col.get('currency', '?')} in {col.get('unit', '?')}; "
                         f"a migration decision and downstream conversion plan are required")})
    for list_field in ("business_keys",):
        if sorted(current.get(list_field, [])) != sorted(baseline.get(list_field, [])):
            changes.append({"field": list_field, "type": "key_changed", "breaking": True,
                            "from": baseline.get(list_field), "to": current.get(list_field),
                            "note": f"{list_field} changed"})
    if current.get("granularity") != baseline.get("granularity"):
        changes.append({"field": "granularity", "type": "granularity_changed", "breaking": True,
                        "from": baseline.get("granularity"), "to": current.get("granularity"),
                        "note": "grain changed"})
    if current.get("partition") != baseline.get("partition"):
        changes.append({"field": "partition", "type": "partition_changed", "breaking": True,
                        "from": baseline.get("partition"), "to": current.get("partition"),
                        "note": "partition scheme changed"})
    if current.get("quality") != baseline.get("quality"):
        changes.append({"field": "quality", "type": "quality_changed", "breaking": False,
                        "from": baseline.get("quality"), "to": current.get("quality"),
                        "note": "quality thresholds changed"})
    if current.get("sla") != baseline.get("sla"):
        changes.append({"field": "sla", "type": "sla_changed", "breaking": False,
                        "from": baseline.get("sla"), "to": current.get("sla"),
                        "note": "SLA changed"})
    return changes


# --------------------------------------------------------------------------- #
# migration decisions                                                         #
# --------------------------------------------------------------------------- #
def migrations_path(project_root: Path, contract_id: str) -> Path:
    safe = re.sub(r"[^\w.-]", "_", contract_id)
    return project_root / ".claude" / "dw" / "migrations" / f"{safe}.json"


def load_decisions(project_root: Path, contract_id: str) -> List[Dict[str, Any]]:
    path = migrations_path(project_root, contract_id)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, list) else data.get("decisions", [])
    except (json.JSONDecodeError, OSError):
        return []


def record_decision(project_root: Path, contract_id: str, decision: Dict[str, Any]) -> Path:
    path = migrations_path(project_root, contract_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    decisions = load_decisions(project_root, contract_id)
    decisions.append(decision)
    path.write_text(json.dumps({"contract_id": contract_id, "decisions": decisions},
                               indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def unapproved_breaking(changes: List[Dict[str, Any]], current: Dict[str, Any],
                        baseline: Dict[str, Any], decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    approved = {(d.get("from_hash"), d.get("to_hash")) for d in decisions}
    pending = []
    for change in changes:
        if not change.get("breaking"):
            continue
        pair = (baseline.get("digest"), current.get("digest"))
        if pair not in approved:
            pending.append(change)
    return pending


def crosscheck_ddl(contract: Dict[str, Any], ddl: TableDDL) -> List[Dict[str, str]]:
    """Provable-from-DDL checks only; business semantics stay in review."""
    findings: List[Dict[str, str]] = []
    cols = _col_map(contract)
    for name, ccol in cols.items():
        ddl_col = ddl.find(name)
        if ddl_col is None:
            findings.append({"field": f"columns.{name}", "finding": "missing_in_ddl",
                             "note": f"contract column {name} not found in DDL"})
            continue
        want = parse_type(str(ccol.get("type", "")))
        got = ddl_col
        if want.family and got.family and want.family != got.family:
            findings.append({"field": f"columns.{name}", "finding": "type_mismatch",
                             "note": f"contract says {want.family}, DDL says {got.type_key()}"})
        elif (want.precision is not None and got.precision is not None
              and (want.precision != got.precision or want.scale != got.scale)):
            findings.append({"field": f"columns.{name}", "finding": "precision_mismatch",
                             "note": f"contract says {want.type_key()}, DDL says {got.type_key()}"})
        if ccol.get("nullable") is False and got.nullable:
            findings.append({"field": f"columns.{name}", "finding": "nullability_mismatch",
                             "note": "contract requires NOT NULL, DDL allows NULL"})
    for dcol in ddl.columns:
        if dcol.name.lower() not in cols:
            findings.append({"field": f"ddl.{dcol.name}", "finding": "missing_in_contract",
                             "note": f"DDL column {dcol.name} absent from contract; "
                                     f"add it or confirm intentional"})
    part = contract.get("partition") or {}
    if part.get("column"):
        ddl_parts = [p.name.lower() for p in ddl.partition_columns]
        if part["column"].lower() not in ddl_parts:
            findings.append({"field": "partition", "finding": "partition_mismatch",
                             "note": f"contract partition {part['column']} not found in DDL "
                                     f"(ddl has {ddl_parts or 'none'})"})
    keys = [k.lower() for k in contract.get("business_keys", [])]
    if keys and ddl.primary_key and sorted(keys) != sorted(k.lower() for k in ddl.primary_key):
        findings.append({"field": "business_keys", "finding": "key_mismatch",
                         "note": f"contract keys {keys} != DDL primary key {ddl.primary_key}"})
    return findings
