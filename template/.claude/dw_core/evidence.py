"""Evidence bundles: what was verified, against which inputs, when."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from . import EVIDENCE_SCHEMA, __version__


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def git_commit(root: Path) -> Optional[str]:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root),
                             capture_output=True, text=True, timeout=10, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def build_evidence(name: str, inputs: Dict[str, str], result_summary: Dict,
                   root: Path, environments: Optional[Dict] = None,
                   artifacts: Optional[List[str]] = None) -> Dict:
    ts = datetime.now(timezone.utc)
    return {
        "schema": EVIDENCE_SCHEMA,
        "name": name,
        "tool_version": __version__,
        "timestamp": ts.isoformat(timespec="seconds"),
        "commit": git_commit(root),
        "inputs": inputs,  # {role: digest}
        "policy_digest": inputs.get("policy", ""),
        "result_summary": result_summary,
        "environments": environments or {},
        "artifacts": artifacts or [],
    }


def save_evidence(evidence: Dict, root: Path, name: str) -> Path:
    folder = root / ".claude" / "dw" / "evidence"
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.-]", "_", name)
    path = folder / f"{safe}.json"
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_evidence(root: Path, name: str) -> Optional[Dict]:
    safe = re.sub(r"[^\w.-]", "_", name)
    path = root / ".claude" / "dw" / "evidence" / f"{safe}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None


def verify_evidence(evidence: Optional[Dict], current_inputs: Dict[str, str],
                    freshness_hours: int = 72) -> Dict:
    """Stale when any input digest differs, is missing, or TTL expired."""
    if not evidence:
        return {"state": "missing", "reason": "no evidence recorded"}
    problems: List[str] = []
    for role, digest in current_inputs.items():
        recorded = (evidence.get("inputs") or {}).get(role)
        if not recorded:
            problems.append(f"input '{role}' not covered by evidence")
        elif recorded != digest:
            problems.append(f"input '{role}' changed since evidence was recorded")
    try:
        recorded_at = datetime.fromisoformat(evidence["timestamp"])
        age_hours = (datetime.now(timezone.utc) - recorded_at).total_seconds() / 3600
        if age_hours > freshness_hours:
            problems.append(f"evidence older than {freshness_hours}h ({age_hours:.1f}h)")
    except (KeyError, ValueError):
        problems.append("evidence timestamp unreadable")
    if problems:
        return {"state": "stale", "reason": "; ".join(problems)}
    return {"state": "valid", "reason": "inputs unchanged and within freshness window"}


def workspace_edited_warning(evidence: Dict) -> Optional[str]:
    """A PASS file edited by hand is display/diagnostic material only."""
    if evidence.get("hand_edited"):
        return "evidence flagged as hand-edited; not acceptable for CI gating"
    return None
