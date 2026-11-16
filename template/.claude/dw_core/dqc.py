"""dw dqc: DQC rule generation with stable IDs, reusing the v1 9-class model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

RULE_CLASSES = (
    "pk_not_null",            # completeness: business keys never NULL
    "partition_row_count",    # completeness: partition volume in expected band
    "required_not_null",      # completeness: core fields never NULL
    "money_tolerance",        # accuracy: money diff vs upstream within tolerance
    "value_range",            # accuracy: numeric range sanity
    "linkage",                # consistency: flag combinations must agree
    "upstream_consistency",   # consistency: aggregate vs detail
    "sla_time",               # timeliness: ready by SLA
    "freshness",              # timeliness: latest partition age
)


def stable_id(table: str, rule_type: str, columns: List[str], threshold: str) -> str:
    basis = f"{table}|{rule_type}|{','.join(sorted(columns))}|{threshold}"
    return "dqc_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:10]


def money_columns(contract: Dict) -> List[Dict]:
    return [c for c in contract.get("columns", []) if c.get("currency") and c.get("unit")]


def gen_rules(contract: Dict, enabled: Optional[List[str]] = None) -> Dict:
    table = contract.get("table") or contract.get("contract_id") or ""
    enabled = enabled or list(RULE_CLASSES)
    quality = contract.get("quality") or {}
    sla = contract.get("sla") or {}
    rules: List[Dict] = []

    def add(rule_type: str, name: str, columns: List[str], threshold: str, severity: str = "critical"):
        if rule_type not in enabled:
            return
        rules.append({
            "id": stable_id(table, rule_type, columns, threshold),
            "type": rule_type,
            "name": name,
            "table": table,
            "fields": columns,
            "threshold": threshold,
            "severity": severity,
        })

    keys = contract.get("business_keys", [])
    if keys:
        add("pk_not_null", "主键非空", keys, "0 null rows")
    part = (contract.get("partition") or {}).get("column") or "partition_dt"
    add("partition_row_count", "分区数据量波动",
        [part], f"±{quality.get('row_count_fluctuation_max', '30%')} vs 7-day mean", "warning")
    required = [c["name"] for c in contract.get("columns", [])
                if c.get("nullable") is False and c["name"] not in keys]
    if required:
        add("required_not_null", "必填字段非空", required, "0 null rows")
    monies = [c["name"] for c in money_columns(contract)]
    if monies:
        add("money_tolerance", "金额字段容差", monies,
            f"≤{quality.get('money_tolerance', '0.01%')} vs upstream")
    add("value_range", "数值范围", monies or keys, "per-contract caliber bounds", "warning")
    add("linkage", "联动逻辑", [], "declared flag linkages", "warning")
    add("upstream_consistency", "上下游一致性", monies,
        f"≤{quality.get('money_tolerance', '0.01%')} aggregate vs detail")
    if sla:
        add("sla_time", "产出时间 SLA", [part], f"ready by {sla.get('time', '08:00')} {sla.get('tz', 'Asia/Shanghai')}", "warning")
    add("freshness", "数据新鲜度", [part],
        f"max partition age ≤ {quality.get('freshness_days', 1)} day(s)", "warning")
    return {"table": table, "sla": sla.get("time", ""), "rules": rules}


def check_rules(config_json: Dict, contract: Dict) -> List[str]:
    problems: List[str] = []
    expected = {r["id"]: r for r in gen_rules(contract).get("rules", [])}
    actual = {r.get("id"): r for r in config_json.get("rules", [])}
    for rid, rule in expected.items():
        if rid not in actual:
            problems.append(f"missing rule {rid} ({rule['type']}) required by contract")
    for rid, rule in actual.items():
        if rid not in expected:
            problems.append(f"rule {rid} ({rule.get('type')}) not derivable from contract; "
                            f" drifted config or stale contract")
        elif rule.get("threshold") != expected[rid]["threshold"]:
            problems.append(f"rule {rid}: threshold '{rule.get('threshold')}' != contract-derived "
                            f"'{expected[rid]['threshold']}'")
    return problems
