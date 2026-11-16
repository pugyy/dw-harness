"""Offline end-to-end demo on a daily-partitioned orders table.

Reproducible from a clean checkout with no credentials:
    python scripts/run_demo.py            (repo)
    dw demo                              (installed CLI)

Covers the positive path plus counter-cases (a)-(f) from the v2 spec:
  a. SELECT t.* hits the same rule via hook and CLI; COUNT(*) and keywords
     inside string literals pass.
  b. net_amount fen -> yuan: SQL stays legal, contract acceptance fails for
     missing migration decision.
  c. two orders with swapped amounts: totals equal, key-level reconcile
     fails; plus duplicate keys / missing partition / zero baseline / NULL /
     tolerance boundaries.
  d. changed SQL/contract inputs make old evidence UNVERIFIED; strict mode
     cannot pass on it.
  e. guard decisions: prod overwrite, unscoped delete, -f indirect drop,
     expired exception, benign read-only command.
  f. repeated migration on a v1 project keeps user config intact and never
     duplicates hooks.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__
from .check import CheckItem, CheckReport
from .config import HarnessConfig
from .contracts import load_contract, normalize
from .evidence import (build_evidence, file_digest, load_evidence,
                       save_evidence, text_digest, verify_evidence)
from .guard import GuardEngine
from .reconcile import ReconcileSpec, reconcile
from .rules import lint_sql

CASES: List[str] = []


def _case(name: str, ok: bool, detail: str) -> None:
    CASES.append({"case": name, "ok": ok, "detail": detail})


def _find_fixtures() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parents[2] / "examples" / "demo",   # repo checkout (src/)
                      here.parents[3] / "examples" / "demo",   # installed near repo
                      here.parents[1] / "examples" / "demo"):
        if candidate.is_dir():
            return candidate
    raise SystemExit("demo fixtures not found; pass --fixtures <dir>")


def run_demo(fixtures: Optional[Path] = None, out_dir: Optional[Path] = None) -> int:
    global CASES
    CASES = []
    fixtures = fixtures or _find_fixtures()
    out_dir = out_dir or (fixtures / "report")
    out_dir.mkdir(parents=True, exist_ok=True)
    workspace = out_dir / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    # project skeleton inside workspace
    (workspace / ".claude" / "dw").mkdir(parents=True)
    (workspace / "contracts").mkdir(parents=True)
    shutil.copyfile(fixtures / "harness.json", workspace / ".claude" / "dw" / "harness.json")
    shutil.copytree(fixtures / "csv", workspace / "csv")
    shutil.copyfile(fixtures / "contract.json", workspace / "contracts" / "contract.json")
    config = HarnessConfig.load(root=workspace)

    # ---- positive path ----------------------------------------------------
    good_sql = (fixtures / "insert_orders.sql").read_text(encoding="utf-8")
    result = lint_sql(good_sql, "odps", config)
    _case("positive: good insert lints clean", not result.errors, str(result.to_dict()["status"]))

    # ---- (a) select-star parity: CLI rule vs hook script -------------------
    bad_sql = (fixtures / "bad_select_t_star.sql").read_text(encoding="utf-8")
    cli_hit = lint_sql(bad_sql, "odps", config)
    bad_path = workspace / "bad_select_t_star.sql"
    bad_path.write_text(bad_sql, encoding="utf-8")
    hook_root = fixtures.parent.parent / "template" / ".claude"
    if not hook_root.is_dir():  # fall back to src layout
        hook_root = fixtures.parent.parent / "src"
    hook_script = _locate_hook("validate_post.py")
    hook_out = ""
    if hook_script:
        payload = json.dumps({"tool_name": "Write",
                              "tool_input": {"file_path": str(bad_path)}})
        proc = subprocess.run([sys.executable, str(hook_script)],
                              input=payload, capture_output=True, text=True, timeout=60)
        hook_out = proc.stderr
    same_rule = (any(i.rule == "no-select-star" for i in cli_hit.errors)
                 and "no-select-star" in hook_out)
    _case("(a) SELECT t.* hits no-select-star in CLI and hook", same_rule,
          f"cli={cli_hit.to_dict()['status']}; hook_stderr_has_rule={'no-select-star' in hook_out}")

    tricky = (fixtures / "tricky_ok.sql").read_text(encoding="utf-8")
    tricky_result = lint_sql(tricky, "odps", config)
    no_false_positive = not [i for i in tricky_result.issues
                             if i.rule in ("no-select-star", "dml-requires-where")]
    _case("(a) COUNT(*) and string-literal 'drop table' pass", no_false_positive,
          json.dumps([i.to_dict() for i in tricky_result.issues]))

    # ---- (b) contract unit change fen -> yuan ------------------------------
    current, _ = load_contract(fixtures / "contract.json")
    changed_raw = json.loads((fixtures / "contract_changed.json").read_text(encoding="utf-8"))
    changed = normalize(changed_raw)
    from .contracts import diff_contracts, load_decisions, unapproved_breaking
    changes = diff_contracts(changed, current)
    pending = unapproved_breaking(changes, changed, current,
                                  load_decisions(workspace, changed["contract_id"]))
    unit_caught = any(c["type"] == "unit_changed" for c in changes)
    _case("(b) net_amount fen->yuan detected as breaking unit change", unit_caught,
          "; ".join(c["type"] for c in changes))
    _case("(b) acceptance fails without migration decision", bool(pending),
          f"{len(pending)} unapproved breaking change(s)")

    # ---- (c) reconcile counter-cases ----------------------------------------
    def spec_for(name_left: str, name_right: str, **overrides) -> ReconcileSpec:
        base = {
            "left": {"adapter": "file", "path": str(workspace / "csv" / name_left), "partition": "20261115"},
            "right": {"adapter": "file", "path": str(workspace / "csv" / name_right), "partition": "20261115"},
            "keys": ["order_no"],
            "metrics": [{"column": "net_amount", "abs_tol": "0", "rel_tol": "0",
                         "unit_left": "fen", "unit_right": "fen"},
                        {"column": "pay_amount", "abs_tol": "0.01", "rel_tol": "0",
                         "unit_left": "yuan", "unit_right": "yuan"}],
            "sample_rows": 20, "max_rows": 100000,
        }
        base.update(overrides)
        return ReconcileSpec(**base)

    swap = reconcile(spec_for("new_swap.csv", "old.csv"))
    totals_equal = (swap.totals.get("net_amount", {}).get("delta_base_unit") == "0")
    _case("(c) swapped amounts: totals equal but key-level FAIL",
          swap.status == "fail" and totals_equal and swap.diffs,
          f"status={swap.status}; delta={swap.totals.get('net_amount', {}).get('delta_base_unit')}; "
          f"diffs={len(swap.diffs)}")

    dup = reconcile(spec_for("dup_keys.csv", "old.csv"))
    _case("(c) duplicate keys fail precheck", dup.status == "fail" and dup.prechecks["duplicate_keys"] != {"left": {}, "right": {}},
          json.dumps(dup.prechecks["duplicate_keys"]))

    missing = reconcile(spec_for("no_such_file.csv", "old.csv"))
    _case("(c) missing partition is UNVERIFIED (not pass/fail)",
          missing.status == "unverified" and "missing" in "; ".join(missing.reasons),
          "; ".join(missing.reasons))

    zero_null = reconcile(spec_for("zero_null.csv", "old.csv"))
    _case("(c) zero-baseline and NULL semantics",
          zero_null.status == "fail" and bool(zero_null.null_mismatches),
          f"null_mismatches={len(zero_null.null_mismatches)}; diffs={len(zero_null.diffs)}")

    tol = reconcile(spec_for("tolerance_edge.csv", "old.csv"))
    _case("(c) tolerance boundary: 0.009 passes, 0.02 fails",
          tol.status == "fail" and len(tol.diffs) == 1,
          f"diffs={[d['key'] for d in tol.diffs]}")

    # ---- (d) stale evidence --------------------------------------------------
    inputs = {"contract": file_digest(workspace / "contracts" / "contract.json"),
              "sql:insert_orders.sql": text_digest(good_sql)}
    ev = build_evidence("reconcile-db_a.dws_trade_order_di", inputs,
                        {"status": "pass"}, workspace, producer="dw-reconcile",
                        binding_paths={
                            "contract": str(workspace / "contracts" / "contract.json"),
                            "sql:insert_orders.sql": str(fixtures / "insert_orders.sql")})
    save_evidence(ev, workspace, "reconcile-db_a.dws_trade_order_di")
    fresh = verify_evidence(
        load_evidence(workspace, "reconcile-db_a.dws_trade_order_di"), inputs)
    stale_inputs = dict(inputs, **{"sql:insert_orders.sql": text_digest(good_sql + "\n-- touched\n")})
    stale = verify_evidence(ev, stale_inputs)
    _case("(d) evidence valid now, stale after input change",
          fresh["state"] == "valid" and stale["state"] == "stale", json.dumps(stale))

    report = CheckReport(table="db_a.dws_trade_order_di", environment="dev",
                         partition="20261115", mode="strict")
    report.items.append(CheckItem("reconcile", "unverified",
                                  "evidence stale: " + stale["reason"]))
    _case("(d) strict mode exits 2 on unverified", report.exit_code == 2,
          f"exit={report.exit_code}")

    # ---- (d2) hand-written PASS cannot gate strict mode --------------------
    manual = dict(ev)
    manual["producer"] = "manual"
    manual["signature"] = ""
    manual_state = verify_evidence(manual, inputs, strict=True)
    _case("(d2) manual/hand-written PASS rejected in strict mode",
          manual_state["state"] == "untrusted", json.dumps(manual_state))

    # ---- (d3) forged producer without an HMAC key is refused ---------------
    import os as _os
    had_key = _os.environ.pop("DW_HARNESS_EVIDENCE_KEY", None)
    forged = dict(ev)
    forged["producer"] = "dw-reconcile"
    forged_state = verify_evidence(forged, inputs, strict=True)
    if had_key:
        _os.environ["DW_HARNESS_EVIDENCE_KEY"] = had_key
    _case("(d3) unsigned producer=dw-reconcile refused in strict mode",
          forged_state["state"] == "untrusted", json.dumps(forged_state))

    # ---- (e) guard decisions ---------------------------------------------------
    engine = GuardEngine(config, env={"DW_HARNESS_PROD": "1"})
    prod_overwrite = engine.evaluate_command(
        "odpscmd -e \"INSERT OVERWRITE TABLE db_a.dws_trade_order_di PARTITION (partition_dt='20261115') SELECT 1\"")
    _case("(e) prod overwrite w/o confirmed scope -> deny/ask",
          prod_overwrite.decision in ("deny", "ask"), json.dumps(prod_overwrite.to_dict()["details"]))

    delete_nowhere = engine.evaluate_command("odpscmd -e 'DELETE FROM db_a.dws_trade_order_di'")
    _case("(e) unscoped DELETE -> deny", delete_nowhere.decision == "deny",
          "; ".join(delete_nowhere.reasons))

    drop_file_src = fixtures / "drop_script.sql"
    drop_file_dst = workspace / "drop_script.sql"
    shutil.copyfile(drop_file_src, drop_file_dst)
    indirect = engine.evaluate_command(f"odpscmd -f {drop_file_dst}", cwd=workspace)
    _case("(e) DROP via -f script caught", indirect.decision == "deny"
          and any("destructive" in r for r in indirect.reasons), "; ".join(indirect.reasons))

    expired_env = {"DW_HARNESS_PROD": ""}
    engine_dev = GuardEngine(config, env=expired_env)
    shutil.copyfile(fixtures / "policy_exceptions_expired.json",
                    workspace / ".claude" / "dw" / "policy_exceptions.json")
    expired = engine_dev.evaluate_command(
        "odpscmd -e 'TRUNCATE TABLE db_a.tmp_scratch'",
        # the copied exception grants this only until 2020-01-01 -> expired
    )
    _case("(e) expired exception does not grant", expired.decision != "allow"
          or bool(expired.reasons), "; ".join(expired.reasons))

    benign = engine.evaluate_command("ls -la && cat report.md | grep total")
    _case("(e) benign non-db command untouched", benign.decision == "allow",
          "; ".join(benign.reasons))

    # ---- (f) v1 project migration, run twice ------------------------------------
    v1_project = workspace / "v1_project"
    _make_v1_project(v1_project, fixtures)
    from .migrate import run_init
    template_root = fixtures.parent.parent / "template"
    v1_hashes = json.loads((fixtures.parent.parent / "src" / "scaffold" / "v1_hashes.json")
                           .read_text(encoding="utf-8"))
    report1 = run_init(v1_project, template_root, "python", "odps")
    report2 = run_init(v1_project, template_root, "python", "odps")
    settings_now = json.loads((v1_project / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hook_blocks = json.dumps(settings_now.get("hooks", {}))
    v1_left = [c for c in ("python .claude/hooks/validate_sql.py",
                           "python .claude/hooks/block_dangerous_ddl.py",
                           "python .claude/hooks/inject_context.py") if c in hook_blocks]
    guard_count = hook_blocks.count("guard_shell.py")
    custom_kept = (v1_project / ".claude" / "skills" / "my-custom-skill" / "SKILL.md").is_file()
    statusline_kept = "statusLine" in settings_now
    _case("(f) migration idempotent + user content preserved",
          not v1_left and guard_count == 1 and custom_kept and statusline_kept,
          f"v1_hooks_left={v1_left}; guard_blocks={guard_count}; custom_skill={custom_kept}; "
          f"statusLine={statusline_kept}; conflicts={report2.conflicts}")

    # ---- summary ------------------------------------------------------------
    failed = [c for c in CASES if not c["ok"]]
    payload = {"tool_version": __version__, "cases": CASES,
               "summary": {"total": len(CASES), "failed": len(failed)},
               "offline": True,
               "note": "offline fixtures only; live MaxCompute/StarRocks/Claude Code "
                       "verification steps: docs/e2e-demo.md"}
    (out_dir / "report.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    lines = [f"# dw demo — offline acceptance ({len(CASES)} cases, {len(failed)} failed)", ""]
    for c in CASES:
        lines.append(f"- [{'x' if c['ok'] else ' '}] {c['case']} — {c['detail'][:160]}")
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for c in CASES:
        print(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['case']}")
    print(f"\nreport: {out_dir / 'report.json'}")
    return 0 if not failed else 1


def _locate_hook(name: str) -> Optional[Path]:
    here = Path(__file__).resolve()
    for base in (here.parents[3] / "template" / ".claude" / "hooks",
                 here.parents[3] / "plugins" / "dw-harness" / "hooks",
                 here.parents[1] / "hooks"):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


def _make_v1_project(root: Path, fixtures: Path) -> None:
    """A v1-shaped project with user customizations that must survive."""
    src = fixtures / "v1_project"
    shutil.copytree(src, root)


def _main() -> int:  # pragma: no cover
    return run_demo()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
