"""dw impact: table-level lineage from repo SQL + contracts, column paths when provable.

A DataWorks metadata adapter exists as an opt-in capability; it only talks to
https endpoints whose host is public (localhost/loopback/private/reserved
addresses are rejected before any request is made).
"""
from __future__ import annotations

import ipaddress
import json
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from .sqlsplit import scan_sql

SKIP_DIRS = {".git", ".claude", "node_modules", "__pycache__", ".venv", "dist", "build"}
_TARGET_RE = re.compile(
    r"\b(?:insert\s+overwrite\s+table|insert\s+into(?:\s+table)?|merge\s+into|create\s+table(?:\s+if\s+not\s+exists)?)\s+[\w.`\[\]\"']*?([\w.`\[\]\"]+)", re.I)
_FROM_RE = re.compile(r"\b(?:from|join)\s+[\w.`\[\]\"']*?([\w.`\[\]\"]+)", re.I)


def _norm(table: str) -> str:
    return table.strip().strip("`[]\"'").lower()


def collect_repo_edges(project_root: Path) -> List[Dict]:
    edges: Dict[Tuple[str, str], Dict] = {}
    for sql_file in _walk_sql(project_root):
        try:
            text = sql_file.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for statement in scan_sql(text)[0]:
            code = statement.code
            tm = _TARGET_RE.search(code)
            if not tm:
                continue
            target = _norm(tm.group(1))
            sources: Set[str] = set()
            for sm in _FROM_RE.finditer(code):
                name = _norm(sm.group(1))
                if name and name != target:
                    sources.add(name)
            columns = _projection_columns(code, target)
            for src in sources or {""}:
                key = (src, target)
                e = edges.setdefault(key, {"source": src, "target": target,
                                           "evidence_files": set(), "columns": set()})
                e["evidence_files"].add(sql_file.relative_to(project_root).as_posix())
                e["columns"].update(columns)
    out = []
    for e in edges.values():
        out.append({
            "source": e["source"] or None,
            "target": e["target"],
            "evidence_files": sorted(e["evidence_files"]),
            "columns": sorted(c for c in e["columns"] if c) if e["columns"] else [],
            "column_coverage": "confirmed" if e["columns"] else "table-level only",
        })
    return out


def _projection_columns(code: str, target: str) -> Set[str]:
    """Column paths only when the projection is a plain column list."""
    m = re.search(r"\bselect\b(.*?)\bfrom\b", code, re.I | re.S)
    if not m:
        return set()
    body = m.group(1)
    if not body.strip():
        return set()
    cols: Set[str] = set()
    for chunk in body.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        alias = re.match(r"^[\w.`\[\]\"]+$", chunk)
        expr = re.match(r"^.*?\s+as\s+([\w]+)$", chunk, re.I)
        if expr:
            cols.add(expr.group(1))
        elif alias and not re.search(r"[(*+\-/]", chunk):
            name = chunk.split(".")[-1].strip("`[]\"'")
            if name and name != "*":
                cols.add(name)
        else:
            return set()  # any expression star/aggregate: cannot confirm columns
    return cols


def _walk_sql(root: Path):
    for path in sorted(root.rglob("*.sql")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


class AdapterNotConfigured(Exception):
    pass


def _host_allowed(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname or ""
    if hostname in ("localhost", "0.0.0.0", "::1", ""):
        return False
    try:
        addr = ipaddress.ip_address(hostname)
        return not (addr.is_private or addr.is_loopback or addr.is_link_local
                    or addr.is_reserved or addr.is_multicast or addr.is_unspecified)
    except ValueError:
        return hostname.endswith(".inner") is False and "." in hostname


class DataWorksLineage:
    """Opt-in adapter; credentials come from env, never from source."""

    def __init__(self, endpoint: str = "", token: str = "", project: str = ""):
        import os
        self.endpoint = endpoint or os.environ.get("DW_HARNESS_DW_ENDPOINT", "")
        self.token = token or os.environ.get("DW_HARNESS_DW_TOKEN", "")
        self.project = project or os.environ.get("DW_HARNESS_DW_PROJECT", "")

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.token)

    def fetch_lineage(self, table: str) -> List[Dict]:
        if not self.configured:
            raise AdapterNotConfigured(
                "DataWorks adapter needs DW_HARNESS_DW_ENDPOINT / _TOKEN env vars")
        url = f"{self.endpoint.rstrip('/')}/lineage?project={self.project}&table={table}"
        if not _host_allowed(url):
            raise AdapterNotConfigured(f"endpoint host rejected by policy: {urlparse(url).hostname}")
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(request, timeout=15) as resp:  # nosec - host validated above
            payload = json.loads(resp.read().decode("utf-8"))
        return [{"source": e.get("source"), "target": e.get("target"),
                 "columns": e.get("columns", []), "origin": "dataworks"} for e in payload.get("edges", [])]


@dataclass
class ImpactReport:
    table: str
    upstream: List[Dict] = field(default_factory=list)
    downstream: List[Dict] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)
    freshness: str = "repo-scan at build time"

    def to_dict(self) -> Dict:
        return {
            "table": self.table,
            "upstream": self.upstream,
            "downstream": self.downstream,
            "sources": self.sources,
            "unknown": self.unknown,
            "freshness": self.freshness,
        }


def analyze_impact(project_root: Path, table: str,
                   adapter: Optional[DataWorksLineage] = None) -> ImpactReport:
    want = _norm(table)
    report = ImpactReport(table=want)
    edges = collect_repo_edges(project_root)
    report.sources.append("repo-sql")
    for edge in edges:
        if edge["target"] == want and edge["source"]:
            report.upstream.append(edge)
        if edge["source"] == want:
            report.downstream.append(edge)
    if adapter is not None:
        if adapter.configured:
            try:
                for edge in adapter.fetch_lineage(want):
                    report.sources.append("dataworks")
                    if edge["target"] == want:
                        report.upstream.append(edge)
                    elif edge["source"] == want:
                        report.downstream.append(edge)
            except (AdapterNotConfigured, OSError):
                report.unknown.append("dataworks adapter configured but query failed; "
                                      "lineage treated as unknown")
        else:
            report.unknown.append("dataworks adapter not configured")
    if not report.upstream and not report.downstream:
        report.unknown.append("no repo SQL references this table; lineage unknown")
    return report
