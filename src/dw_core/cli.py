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
    p.add_argument("--mode", choices=["template", "plugin"], default="template")
    p.add_argument("--mcp", action="store_true", help="register the local stdio MCP server")
    p.add_argument("--statusline", action="store_true",
                   help="add the dw statusLine entry (keeps an existing user statusLine)")
    p.add_argument("--scaffold", default="", help="scaffold dir (default: bundled)")

    p = sub.add_parser("doctor", help="self-check")
    p.add_argument("--json", action="store_true")
    p.add_argument("--mode", choices=["auto", "plugin", "template"], default="auto")
    p.add_argument("--plugin-dir", default="", help="plugin root for plugin-mode checks")
    p.add_argument("--strict", action="store_true", help="count app-wiring as critical")

    p = sub.add_parser("lint", help="lint SQL files")
    p.add_argument("files", nargs="*")
    p.add_argument("--dialect", default="")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true", help="exit non-zero on warnings too")
    p.add_argument("--changed", action="store_true",
                   help="lint *.sql changed vs the git default branch (or last commit)")

    p = sub.add_parser("contract", help="contract operations")
    csub = p.add_subparsers(dest="contract_cmd", required=True)
    c = csub.add_parser("validate"); c.add_argument("file")
    c = csub.add_parser("compile"); c.add_argument("file"); c.add_argument("--out", default="")
    c = csub.add_parser("diff"); c.add_argument("file")
    c.add_argument("--baseline", required=True,
                   help="contract file, or git:<rev>:<path> for a git baseline")
    c = csub.add_parser("decide"); c.add_argument("file")
    c.add_argument("--baseline", required=True)
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
    p.add_argument("--contract", default="", help="bind contract digest into evidence")
    p.add_argument("--baseline", default="", help="bind the contract baseline file or Git revision")
    p.add_argument("--sql", action="append", default=[],
                   help="bind sql file digest into evidence (repeatable)")
    p.add_argument("--ddl", action="append", default=[],
                   help="bind ddl file digest into evidence (repeatable)")

    p = sub.add_parser("check", help="acceptance report")
    p.add_argument("--table", default="",
                   help="target table; with --changed, inferred from the changeset")
    p.add_argument("--env", default="dev")
    p.add_argument("--partition", default="")
    p.add_argument("--sql", action="append", default=[])
    p.add_argument("--contract", default="")
    p.add_argument("--ddl", default="")
    p.add_argument("--dqc", default="")
    p.add_argument("--baseline", default="")
    p.add_argument("--reconcile-spec", default="", help="spec file bound to the evidence")
    p.add_argument("--changed", action="store_true",
                   help="check all affected tables against the Git base")
    p.add_argument("--base-ref", default="", help="Git revision for --changed")
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

    p = sub.add_parser("evidence", help="evidence trust helpers")
    esub = p.add_subparsers(dest="evidence_cmd", required=True)
    esub.add_parser("keygen", help="print a fresh DW_HARNESS_EVIDENCE_KEY value")

    return parser


def _changed_files(root: Path, suffixes, base_ref: str = "", include_deleted: bool = False):
    """Return the base commit and changed paths, preserving spaces and Unicode."""
    import subprocess

    def git(*argv):
        return subprocess.run(["git", *argv], cwd=root, capture_output=True,
                              timeout=30, check=True).stdout.decode("utf-8")

    refs = (base_ref,) if base_ref else ("origin/main", "main", "HEAD~1")
    for ref in refs:
        try:
            base = git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").strip()
            names = git("diff", "--name-only", "-z", base, "--").split("\0")
            names += git("ls-files", "--others", "--exclude-standard", "-z").split("\0")
            return base, [root / n for n in dict.fromkeys(names)
                          if n and not n.startswith((".", "plugins/", "template/"))
                          and Path(n).suffix.lower() in suffixes
                          and (include_deleted or (root / n).is_file())]
        except (subprocess.SubprocessError, OSError):
            continue
    raise ValueError("no usable Git baseline; specify --base-ref for dw check --changed")


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = find_project_root()
    config = HarnessConfig.load(root=root)

    if args.cmd == "init":
        import json as _json
        from .migrate import run_init
        target = Path(args.target).resolve()
        template_root = Path(args.scaffold).resolve() if args.scaffold else None
        if template_root is None:
            here = Path(__file__).resolve()
            for candidate in (here.parent / "data" / "template",  # wheel
                              here.parents[2] / "template"):        # editable checkout
                if (candidate / ".claude").is_dir():
                    template_root = candidate
                    break
        if template_root is None or not (template_root / ".claude").is_dir():
            print("init: template/ not found (run from the repo, or pass --scaffold)")
            return 2
        report = run_init(target, template_root, args.python, args.dialect,
                          dry_run=args.dry_run, mcp=args.mcp,
                          statusline=args.statusline, mode=args.mode)
        print(_json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 2 if report.conflicts else 0

    if args.cmd == "doctor":
        from .doctor import run_doctor
        return run_doctor(root, json_out=args.json, mode=args.mode,
                          plugin_dir=args.plugin_dir, strict=args.strict)

    if args.cmd == "lint":
        from .rules import lint_sql
        files = list(args.files)
        if args.changed:
            try:
                _, changed = _changed_files(root, {".sql"})
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 2
            files.extend(str(p) for p in changed)
            files = list(dict.fromkeys(files))
        if not files:
            print("lint: no files (pass files or --changed)")
            return 2
        results = []
        failed = False
        for name in files:
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
            baseline, _ = contracts.read_baseline(args.baseline, root)
            changes = contracts.diff_contracts(current, baseline)
            _print_json({"from": baseline["digest"], "to": current["digest"],
                         "baseline": args.baseline, "changes": changes})
            return 0
        if args.contract_cmd == "decide":
            from datetime import date
            current, _ = contracts.load_contract(path)
            baseline, _ = contracts.read_baseline(args.baseline, root)
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
        from .contracts import read_baseline
        from .reconcile import ReconcileSpec, reconcile
        from .evidence import (build_evidence, evidence_policy, file_digest,
                               path_binding, save_evidence)
        try:
            spec_path = Path(args.spec).resolve()
            spec_raw, spec = ReconcileSpec.load(spec_path)
            inputs = {}
            binding_paths = {}
            if args.save_evidence:
                scope = spec.evidence_scope(spec_raw.get("table"))
                bindings = spec_raw.get("bindings") or {}
                baseline = args.baseline or bindings.get("baseline")
                inputs["contract-baseline"] = read_baseline(baseline, root)[1] if baseline else "none"
                inputs["policy"] = evidence_policy(config)
                bound = {"reconcile:spec": spec_path, **spec.file_inputs()}
                contract_path = args.contract or bindings.get("contract")
                if contract_path:
                    bound["contract"] = Path(contract_path)
                for prefix, names in (("sql", args.sql), ("ddl", args.ddl)):
                    for name in [*names, *(bindings.get(prefix) or [])]:
                        path = Path(name).resolve()
                        role = f"{prefix}:{path_binding(path, root)}"
                        bound[role] = path
                        binding_paths[role] = path_binding(path, root)
                inputs.update({role: file_digest(path) for role, path in bound.items()})
        except Exception as exc:
            _print_json({"status": "unverified", "reasons": [f"invalid reconciliation inputs: {exc}"]})
            return 2
        result = reconcile(spec)
        payload = {"spec": spec.to_dict(), **result.to_dict()}
        if args.save_evidence and result.status != "unverified":
            try:
                changed = any(file_digest(path) != inputs[role] for role, path in bound.items())
                changed |= evidence_policy(HarnessConfig.load(root=root)) != inputs["policy"]
                if baseline:
                    changed |= read_baseline(baseline, root)[1] != inputs["contract-baseline"]
                if changed:
                    raise ValueError("reconciliation inputs changed during verification")
                name = f"reconcile-{scope['table']}"
                ev = build_evidence(name, inputs, {"status": result.status}, root,
                                    environments={"left": spec.left, "right": spec.right},
                                    producer="dw-reconcile", scope=scope, binding_paths=binding_paths)
                save_evidence(ev, root, name)
                payload["evidence"] = "saved"
            except Exception as exc:
                payload["status"] = "unverified"
                payload["reasons"].append(f"evidence was not saved: {exc}")
        _print_json(payload)
        return {"pass": 0, "fail": 1, "unverified": 2}[payload["status"]]

    if args.cmd == "check":
        from subprocess import SubprocessError
        from .check import CheckItem, CheckReport, run_checks
        from .batch import resolve_table_checks
        options = {
            "sql_files": [Path(p) for p in args.sql],
            "contract_path": Path(args.contract) if args.contract else None,
            "ddl_path": Path(args.ddl) if args.ddl else None,
            "dqc_path": Path(args.dqc) if args.dqc else None,
            "baseline": args.baseline or None,
            "reconcile_spec": Path(args.reconcile_spec) if args.reconcile_spec else None,
        }
        reports = []
        if args.changed:
            try:
                if not args.table and any(options.values()):
                    raise ValueError("table-specific overrides require --table with --changed")
                base, paths = _changed_files(root, {".sql", ".json", ".yaml", ".yml"},
                                             args.base_ref, include_deleted=True)
                targets, unresolved = resolve_table_checks(root, base, paths, args.table)
                for table, inferred in targets.items():
                    values = {**inferred, **{k: v for k, v in options.items() if v}}
                    values["sql_files"] = list(dict.fromkeys(
                        inferred.get("sql_files", []) + options["sql_files"]))
                    reports.append(run_checks(config, table, args.env, args.partition,
                                              mode=args.mode, **values))
                if unresolved or not reports:
                    report = CheckReport("(changeset)", args.env, args.partition, mode=args.mode)
                    report.items.append(CheckItem(
                        "changeset-scope", "unverified",
                        "unresolved changes: " + ", ".join(unresolved) if unresolved
                        else "no affected tables identified"))
                    reports.append(report)
            except (OSError, ValueError, SubprocessError) as exc:
                report = CheckReport("(changeset)", args.env, args.partition, mode=args.mode)
                report.items.append(CheckItem("changeset-scope", "unverified", str(exc)))
                reports.append(report)
        else:
            if not args.table:
                print("check: --table required (or use --changed)", file=sys.stderr)
                return 2
            reports.append(run_checks(config, args.table, args.env, args.partition,
                                      mode=args.mode, **options))
        exit_code = 1 if any(r.exit_code == 1 for r in reports) else max(r.exit_code for r in reports)
        payload = ({"schema": "dw-check-batch/1", "exit_code": exit_code,
                    "reports": [r.to_dict() for r in reports]} if args.changed else reports[0].to_dict())
        md = "\n".join(report.to_markdown() for report in reports)
        if args.out_json:
            Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out_json).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if args.out_md:
            Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out_md).write_text(md, encoding="utf-8")
        print(md)
        return exit_code

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
        ok = mcp_selftest(root=root)
        print("mcp selftest:", "ok" if ok else "failed")
        return 0 if ok else 1

    if args.cmd == "evidence" and args.evidence_cmd == "keygen":
        import secrets
        key = secrets.token_hex(32)
        print(key)
        print("# export it in BOTH the producing and the checking shell:", file=sys.stderr)
        print(f'#   export DW_HARNESS_EVIDENCE_KEY="{key}"', file=sys.stderr)
        print("# (CI: store as a secret; never commit the value)", file=sys.stderr)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
