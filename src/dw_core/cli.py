"""dw — command line entry for dw-harness v2."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .config import HarnessConfig, find_project_root


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dw", description="dw-harness CLI")
    parser.add_argument("--version", action="version", version=f"dw-harness {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="install/merge harness into a project")
    p.add_argument("--target", default=".", help="project directory (default: cwd)")
    p.add_argument("--python", default="python", help="interpreter used by hooks")
    p.add_argument("--dialect", default="", help="default SQL dialect")
    p.add_argument("--dry-run", action="store_true", help="preview only, write nothing")
    p.add_argument("--mcp", action="store_true", help="register the local stdio MCP server")
    p.add_argument("--scaffold", default="", help="scaffold dir (default: bundled)")

    p = sub.add_parser("doctor", help="self-check")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("lint", help="lint SQL files")
    p.add_argument("files", nargs="+")
    p.add_argument("--dialect", default="")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true", help="exit non-zero on warnings too")

    p = sub.add_parser("contract", help="contract operations")
    csub = p.add_subparsers(dest="contract_cmd", required=True)
    c = csub.add_parser("validate"); c.add_argument("file")
    c = csub.add_parser("compile"); c.add_argument("file"); c.add_argument("--out", default="")
    c = csub.add_parser("diff"); c.add_argument("file"); c.add_argument("--baseline", required=True)
    c = csub.add_parser("decide"); c.add_argument("file"); c.add_argument("--baseline", required=True)
    c.add_argument("--approver", required=True); c.add_argument("--reason", required=True)

    p = sub.add_parser("plan", help="DDL migration / backfill rehearsal")
    psub = p.add_subparsers(dest="plan_cmd", required=True)
    c = psub.add_parser("ddl")
    c.add_argument("--from", dest="from_ddl", required=True)
    c.add_argument("--to", dest="to_ddl", required=True)
    c.add_argument("--dialect", default="odps")
    c.add_argument("--allow-narrowing", action="store_true")
    c = psub.add_parser("backfill")
    c.add_argument("--table", required=True)
    c.add_argument("--start", required=True)
    c.add_argument("--end", required=True)
    c.add_argument("--sql", default="")
    c.add_argument("--env", default="dev")

    p = sub.add_parser("dqc", help="DQC rule generation")
    dsub = p.add_subparsers(dest="dqc_cmd", required=True)
    c = dsub.add_parser("gen"); c.add_argument("--contract", required=True); c.add_argument("--out", default="")
    c = dsub.add_parser("check"); c.add_argument("--contract", required=True); c.add_argument("--config", required=True)

    p = sub.add_parser("impact", help="lineage / downstream impact")
    p.add_argument("--table", required=True)
    p.add_argument("--json", action="store_true")
    p.add_argument("--dataworks", action="store_true", help="enable DataWorks adapter (env-configured)")

    p = sub.add_parser("reconcile", help="key-level reconciliation")
    p.add_argument("--spec", required=True, help="JSON spec file")
    p.add_argument("--save-evidence", action="store_true")

    p = sub.add_parser("check", help="acceptance report")
    p.add_argument("--table", required=True)
    p.add_argument("--env", default="dev")
    p.add_argument("--partition", default="")
    p.add_argument("--sql", action="append", default=[])
    p.add_argument("--contract", default="")
    p.add_argument("--ddl", default="")
    p.add_argument("--dqc", default="")
    p.add_argument("--baseline", default="")
    p.add_argument("--mode", choices=["strict", "local"], default="strict")
    p.add_argument("--out-json", default="")
    p.add_argument("--out-md", default="")

    p = sub.add_parser("next", help="infer progress from deliverables")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("demo", help="offline end-to-end demo on the orders table")
    p.add_argument("--fixtures", default="", help="fixtures dir (default: repo examples/demo)")
    p.add_argument("--out", default="", help="report output dir")

    p = sub.add_parser("mcp", help="MCP server helpers")
    p.add_argument("--selftest", action="store_true")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = find_project_root()
    config = HarnessConfig.load(root=root)

    if args.cmd == "doctor":
        from .doctor import run_doctor
        return run_doctor(root, json_out=args.json)

    if args.cmd == "lint":
        from .rules import lint_sql
        results = []
        failed = False
        for name in args.files:
            path = Path(name)
            dialect = config.resolve_dialect(name, args.dialect or None)
            result = lint_sql(path.read_text(encoding="utf-8-sig", errors="replace"), dialect, config)
            results.append({"file": name, **result.to_dict()})
            if result.errors or (args.strict and result.warns):
                failed = True
        if args.json:
            _print_json(results)
        else:
            for r in results:
                status = r["status"]
                print(f"{r['file']}: {status} ({r['dialect']})")
                for issue in r["issues"]:
                    print(f"  [{issue['severity']}] line {issue['line']} {issue['rule']}: {issue['message']}")
        return 1 if failed else 0

    if args.cmd == "contract":
        from . import contracts
        path = Path(args.file)
        if args.contract_cmd == "validate":
            normalized, _ = contracts.load_contract(path)
            problems = contracts.validate_contract(normalized)
            _print_json({"file": str(path), "valid": not problems, "problems": problems,
                         "digest": normalized["digest"]})
            return 0 if not problems else 1
        if args.contract_cmd == "compile":
            out = contracts.compile_contract(path, Path(args.out) if args.out else None)
            print(f"compiled -> {out}")
            return 0
        if args.contract_cmd == "diff":
            current, _ = contracts.load_contract(path)
            baseline, _ = contracts.load_contract(Path(args.baseline))
            changes = contracts.diff_contracts(current, baseline)
            _print_json({"from": baseline["digest"], "to": current["digest"], "changes": changes})
            return 0
        if args.contract_cmd == "decide":
            from datetime import date
            current, _ = contracts.load_contract(path)
            baseline, _ = contracts.load_contract(Path(args.baseline))
            contracts.record_decision(root, current["contract_id"], {
                "date": date.today().isoformat(),
                "approver": args.approver,
                "reason": args.reason,
                "from_hash": baseline["digest"],
                "to_hash": current["digest"],
                "objects": [current["contract_id"]],
            })
            print(f"decision recorded for {current['contract_id']}")
            return 0

    if args.cmd == "plan":
        if args.plan_cmd == "ddl":
            from .plan import plan_ddl
            plan = plan_ddl(Path(args.from_ddl).read_text(encoding="utf-8-sig"),
                            Path(args.to_ddl).read_text(encoding="utf-8-sig"),
                            args.dialect, args.allow_narrowing)
            _print_json(plan.to_dict())
            return 0
        if args.plan_cmd == "backfill":
            from .plan import plan_backfill
            sql = Path(args.sql).read_text(encoding="utf-8-sig") if args.sql else ""
            plan = plan_backfill(args.table, args.start, args.end, sql, args.env)
            _print_json(plan.to_dict())
            return 0

    if args.cmd == "dqc":
        from .contracts import load_contract
        from .dqc import check_rules, gen_rules
        if args.dqc_cmd == "gen":
            contract, _ = load_contract(Path(args.contract))
            rules = gen_rules(contract)
            out = Path(args.out) if args.out else Path(f"dqc_{contract['table'].split('.')[-1]}.json")
            out.write_text(json.dumps(rules, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"generated {len(rules['rules'])} rules -> {out}")
            return 0
        if args.dqc_cmd == "check":
            contract, _ = load_contract(Path(args.contract))
            cfg = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
            problems = check_rules(cfg, contract)
            _print_json({"config": args.config, "problems": problems})
            return 0 if not problems else 1

    if args.cmd == "impact":
        from .impact import DataWorksLineage, analyze_impact
        adapter = DataWorksLineage() if args.dataworks else None
        report = analyze_impact(root, args.table, adapter)
        _print_json(report.to_dict())
        return 0

    if args.cmd == "reconcile":
        from .reconcile import ReconcileSpec, reconcile
        from .evidence import build_evidence, save_evidence, text_digest
        spec_raw = json.loads(Path(args.spec).read_text(encoding="utf-8-sig"))
        spec = ReconcileSpec(**{k: spec_raw.get(k) for k in
                                ("left", "right", "keys", "metrics", "sample_rows", "max_rows")})
        result = reconcile(spec)
        payload = {"spec": spec.to_dict(), **result.to_dict()}
        if args.save_evidence and result.status != "unverified":
            ev = build_evidence(
                f"reconcile-{spec_raw.get('table', 'table')}",
                {"spec": text_digest(json.dumps(spec.to_dict(), sort_keys=True))},
                {"status": result.status}, root,
                environments={"left": spec.left, "right": spec.right})
            save_evidence(ev, root, f"reconcile-{spec_raw.get('table', 'table')}")
            payload["evidence"] = "saved"
        _print_json(payload)
        return 0 if result.status == "pass" else (1 if result.status == "fail" else 2)

    if args.cmd == "check":
        from .check import run_checks
        report = run_checks(
            config, args.table, args.env, args.partition,
            sql_files=[Path(p) for p in args.sql] or None,
            contract_path=Path(args.contract) if args.contract else None,
            ddl_path=Path(args.ddl) if args.ddl else None,
            dqc_path=Path(args.dqc) if args.dqc else None,
            baseline=Path(args.baseline) if args.baseline else None,
            mode=args.mode)
        payload = report.to_dict()
        md = report.to_markdown()
        if args.out_json:
            Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out_json).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if args.out_md:
            Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out_md).write_text(md, encoding="utf-8")
        print(md)
        return report.exit_code

    if args.cmd == "next":
        from .state import infer_step, load_state
        payload = {"state": load_state(root), "progress": infer_step(root)}
        if args.json:
            _print_json(payload)
        else:
            state = payload["state"]
            if state:
                print(f"表: {state.get('table', '-')}  Step: {state.get('step', '-')}")
            for c in payload["progress"]["completed"]:
                print(f"  done  Step {c['step']}/8 {c['name']} ({', '.join(c['deliverables'])})")
            nxt = payload["progress"]["next"]
            if nxt:
                print(f"  next  Step {nxt['step']}/8 {nxt['name']}")
        return 0

    if args.cmd == "demo":
        from .demo import run_demo
        return run_demo(fixtures=Path(args.fixtures) if args.fixtures else None,
                        out_dir=Path(args.out) if args.out else None)

    if args.cmd == "mcp" and args.selftest:
        from .mcp_selftest import mcp_selftest
        ok = mcp_selftest()
        print("mcp selftest:", "ok" if ok else "failed")
        return 0 if ok else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
