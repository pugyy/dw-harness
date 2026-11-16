"""dw check: four-state acceptance report (pass / fail / unverified / n-a).

Exit codes: 0 policy allows merge, 1 known failure, 2 required evidence
unverified. Failures outrank missing evidence; local mode may allow
unverified items but never rewrites their status.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__
from .config import HarnessConfig
from .contracts import (ContractError, crosscheck_ddl, diff_contracts, read_baseline,
                        load_contract, load_decisions,
                        unapproved_breaking)
from .ddl import parse_create_table
from .dqc import check_rules
from .evidence import (evidence_policy, file_digest, load_evidence, path_binding,
                       verify_evidence)
from .rules import lint_sql

STATUS_ORDER = {"fail": 0, "unverified": 1, "pass": 2, "not_applicable": 3}
STATUS_LABEL = {"pass": "PASS", "fail": "FAIL", "unverified": "UNVERIFIED",
                "not_applicable": "N/A"}


@dataclass
class CheckItem:
    name: str
    status: str
    reason: str = ""
    evidence: str = ""

    def to_dict(self) -> Dict:
        return {"name": self.name, "status": self.status,
                "reason": self.reason, "evidence": self.evidence}


@dataclass
class CheckReport:
    table: str
    environment: str
    partition: str
    items: List[CheckItem] = field(default_factory=list)
    mode: str = "strict"  # strict | local

    @property
    def overall(self) -> str:
        worst = "pass"
        for item in self.items:
            if item.status == "not_applicable":
                continue
            if STATUS_ORDER[item.status] < STATUS_ORDER[worst]:
                worst = item.status
        return worst

    @property
    def exit_code(self) -> int:
        if any(i.status == "fail" for i in self.items):
            return 1
        if self.mode == "strict" and any(i.status == "unverified" for i in self.items):
            return 2
        return 0

    def to_dict(self) -> Dict:
        return {
            "schema": "dw-check/1",
            "tool_version": __version__,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "table": self.table, "environment": self.environment,
            "partition": self.partition, "mode": self.mode,
            "overall": self.overall, "exit_code": self.exit_code,
            "items": [i.to_dict() for i in self.items],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# dw check — {self.table}",
            "",
            f"- environment: `{self.environment}`  |  partition: `{self.partition or '-'}`  "
            f"|  mode: `{self.mode}`  |  overall: **{STATUS_LABEL[self.overall]}**",
            "",
            "| check | status | reason | evidence |",
            "|---|---|---|---|",
        ]
        for item in self.items:
            reason = (item.reason or "-").replace("|", "\\|")
            lines.append(f"| `{item.name}` | {STATUS_LABEL[item.status]} | {reason} | "
                         f"{item.evidence or '-'} |")
        lines += ["", f"_dw-harness v{__version__}_"]
        return "\n".join(lines) + "\n"


def _item(name: str, status: str, reason: str = "", evidence: str = "") -> CheckItem:
    return CheckItem(name, status, reason, evidence)


def run_checks(config: HarnessConfig, table: str, environment: str = "dev",
               partition: str = "", sql_files: Optional[List[Path]] = None,
               contract_path: Optional[Path] = None, ddl_path: Optional[Path] = None,
               dqc_path: Optional[Path] = None, baseline: Optional[str] = None,
               reconcile_spec: Optional[Path] = None,
               mode: str = "strict") -> CheckReport:
    report = CheckReport(table=table, environment=environment,
                         partition=partition, mode=mode)
    root = config.root
    inputs: Dict[str, str] = {"policy": evidence_policy(config), "contract-baseline": "none"}

    # ---- lint changed SQL ------------------------------------------------
    sql_files = sql_files or []
    if sql_files:
        errors = 0
        details: List[str] = []
        unreadable = []
        for path in sql_files:
            try:
                inputs[f"sql:{path_binding(path, root)}"] = file_digest(path)
                sql = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                unreadable.append(str(path))
                continue
            dialect = config.resolve_dialect(str(path))
            result = lint_sql(sql, dialect, config)
            for issue in result.errors:
                errors += 1
                details.append(f"{path.name}:{issue.line} {issue.rule}")
        if errors:
            report.items.append(_item("lint-sql", "fail",
                                      f"{errors} error(s): {'; '.join(details[:5])}"))
        elif unreadable:
            report.items.append(_item("lint-sql", "unverified", "cannot read: " + ", ".join(unreadable)))
        else:
            report.items.append(_item("lint-sql", "pass",
                                      f"{len(sql_files)} file(s) clean (offline rules)"))
    else:
        report.items.append(_item("lint-sql", "not_applicable",
                                  "no SQL files in this changeset"))

    # ---- contract ---------------------------------------------------------
    contract_path = contract_path or _find_unique(root, [
        f"contracts/{table}.json", f"contracts/{table}.yaml", f"contracts/{table}.yml",
        "contract.json", "contract.yaml", "contract.yml"])
    contract = None
    if contract_path is None:
        report.items.append(_item("contract-validate", "unverified",
                                  "no contract found for this table; unmanaged tables need "
                                  "explicit onboarding (docs/upgrade-from-v1.md)"))
    else:
        try:
            contract, _ = load_contract(contract_path)
            inputs["contract"] = file_digest(contract_path)
        except Exception as exc:  # noqa: BLE001 - report, don't crash acceptance
            report.items.append(_item("contract-validate", "fail", f"contract unreadable: {exc}"))
            contract = None
        if contract is not None:
            from .contracts import validate_contract
            problems = validate_contract(contract)
            if contract.get("table", "").lower() != table.lower():
                problems.append(f"contract table {contract.get('table')!r} does not match {table}")
            report.items.append(
                _item("contract-validate", "fail" if problems else "pass",
                      "; ".join(problems) if problems else "schema valid",
                      evidence=str(contract_path)))
            # DDL cross-check (provable attributes only)
            ddl_path = ddl_path or _find_unique(root, [f"ddl_{table.split('.')[-1]}.sql",
                                                       f"**/ddl_{table.split('.')[-1]}.sql"])
            if ddl_path is None or not ddl_path.is_file():
                report.items.append(_item("ddl-vs-contract", "unverified",
                                          "no DDL found in changeset"))
            else:
                tables = parse_create_table(ddl_path.read_text(encoding="utf-8-sig", errors="replace"),
                                            config.resolve_dialect(str(ddl_path)))
                names = {table.lower(), table.rsplit(".", 1)[-1].lower()}
                tables = [ddl for ddl in tables if ddl.table.lower() in names]
                if len(tables) != 1:
                    report.items.append(_item("ddl-vs-contract", "unverified",
                                              "DDL file has no unique CREATE TABLE for the requested table"))
                else:
                    inputs[f"ddl:{path_binding(ddl_path, root)}"] = file_digest(ddl_path)
                    findings = crosscheck_ddl(contract, tables[0])
                    hard = [f for f in findings if f["finding"] != "missing_in_contract"]
                    report.items.append(_item(
                        "ddl-vs-contract", "fail" if hard else "pass",
                        "; ".join(f"{f['field']}: {f['note']}" for f in hard[:5]) if hard
                        else "provable attributes consistent; business semantics confirmed in review",
                        evidence=str(ddl_path)))
            # contract diff vs baseline + migration decisions
            if baseline is not None:
                try:
                    base_raw, baseline_digest = read_baseline(baseline, root)
                    if base_raw.get("table") != contract.get("table"):
                        raise ValueError("baseline contract belongs to a different table")
                    changes = diff_contracts(contract, base_raw)
                    pending = unapproved_breaking(changes, contract, base_raw,
                                                  load_decisions(root, contract.get("contract_id", "")))
                    inputs["contract-baseline"] = baseline_digest
                    if pending:
                        report.items.append(_item(
                            "contract-diff", "fail",
                            f"breaking change(s) without recorded migration decision: "
                            f"{'; '.join(p['field'] + ' ' + p['type'] for p in pending[:5])}. "
                            f"Record via `dw contract decide` (docs/configuration.md)"))
                    else:
                        report.items.append(_item("contract-diff", "pass",
                                                  "no unapproved breaking changes vs baseline",
                                                  evidence=str(baseline)))
                except (OSError, ValueError, subprocess.SubprocessError, ContractError, TypeError, AttributeError) as exc:
                    inputs["contract-baseline"] = "unreadable"
                    report.items.append(_item("contract-diff", "unverified",
                                              f"baseline unreadable: {exc}"))
            else:
                report.items.append(_item("contract-diff", "not_applicable",
                                          "no baseline requested for this check"))

    # ---- DQC ---------------------------------------------------------------
    dqc_path = dqc_path or _find_unique(root, [f"dqc_{table.split('.')[-1]}.json"])
    if contract is None:
        report.items.append(_item("dqc-config", "not_applicable", "no contract to derive rules from"))
    elif dqc_path is None:
        report.items.append(_item("dqc-config", "unverified",
                                  "no DQC config file; generate via `dw dqc gen`"))
    else:
        try:
            dqc_json = json.loads(dqc_path.read_text(encoding="utf-8-sig"))
            problems = check_rules(dqc_json, contract)
            inputs[f"dqc:{dqc_path.name}"] = file_digest(dqc_path)
            report.items.append(_item("dqc-config", "fail" if problems else "pass",
                                      "; ".join(problems[:5]) if problems
                                      else f"{len(dqc_json.get('rules', []))} rules stable vs contract",
                                      evidence=str(dqc_path)))
        except (json.JSONDecodeError, OSError) as exc:
            report.items.append(_item("dqc-config", "unverified", f"dqc config unreadable: {exc}"))

    # Establish trust before following any paths carried inside a report.
    from .reconcile import ReconcileError, ReconcileSpec
    ev = load_evidence(root, f"reconcile-{table}")
    ttl = int(config.data.get("evidence", {}).get("freshness_hours", 72))
    fresh = verify_evidence(ev, {}, freshness_hours=ttl, strict=(mode == "strict"))
    if fresh["state"] == "valid":
        try:
            names = [f"reconcile_{table}.json", f"reconcile_{table.rsplit('.', 1)[-1]}.json"]
            spec_path = reconcile_spec or _find_unique(root, names)
            if spec_path is None:
                raise ValueError("no reconciliation spec selected; pass --reconcile-spec")
            raw, spec = ReconcileSpec.load(spec_path)
            requested = {"table": table, "environment": environment, "partition": partition}
            scope = spec.evidence_scope(raw.get("table"))
            if scope != requested or ev.get("scope") != requested:
                raise ValueError("evidence scope does not match target table, environment and partition")
            inputs["reconcile:spec"] = file_digest(spec_path)
            for role, path in spec.file_inputs().items():
                inputs[role] = file_digest(path)
            current = {key: value for key, value in inputs.items()
                       if not key.startswith("dqc:")}
            for role, raw_path in (ev.get("binding_paths") or {}).items():
                if role.startswith(("sql:", "ddl:")) and role not in current:
                    path = root / Path(raw_path)
                    if path_binding(path, root) != role.partition(":")[2]:
                        raise ValueError(f"evidence file binding does not match role {role}")
                    current[role] = file_digest(path)
            fresh = verify_evidence(ev, current, freshness_hours=ttl, strict=(mode == "strict"))
        except (OSError, TypeError, ValueError, AttributeError, KeyError, ReconcileError) as exc:
            fresh = {"state": "stale", "reason": str(exc)}
    if ev is None:
        report.items.append(_item("reconcile", "unverified",
                                  "no reconciliation evidence for this table/partition"))
    elif fresh["state"] == "untrusted":
        report.items.append(_item("reconcile", "unverified",
                                  f"evidence untrusted: {fresh['reason']}; "
                                  f"re-run `dw reconcile --save-evidence` (deterministic producer)"))
    elif fresh["state"] != "valid":
        report.items.append(_item("reconcile", "unverified",
                                  f"evidence stale: {fresh['reason']}; re-run `dw reconcile`"))
    elif ev.get("result_summary", {}).get("status") == "pass":
        report.items.append(_item("reconcile", "pass",
                                  "key-level comparison within tolerance "
                                  f"(producer={ev.get('producer', 'unknown')})",
                                  evidence=f".claude/dw/evidence/reconcile-{table}.json"))
    elif ev.get("result_summary", {}).get("status") == "fail":
        report.items.append(_item("reconcile", "fail",
                                  "recorded reconciliation did not pass",
                                  evidence=f".claude/dw/evidence/reconcile-{table}.json"))

    else:
        report.items.append(_item("reconcile", "unverified", "invalid evidence result state"))
    return report


def _find_unique(root: Path, patterns: List[str]) -> Optional[Path]:
    for pattern in patterns:
        matches = sorted(root.rglob(pattern))
        matches = [m for m in matches if ".git" not in m.parts and ".claude" not in m.parts]
        if len(matches) == 1:
            return matches[0]
        if matches:
            return None  # ambiguous results require an explicit path
    return None
