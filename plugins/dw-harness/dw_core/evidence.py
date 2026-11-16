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
                   artifacts: Optional[List[str]] = None,
                   producer: str = "manual",
                   binding_paths: Optional[Dict[str, str]] = None) -> Dict:
    ts = datetime.now(timezone.utc)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "name": name,
        "producer": producer,  # dw-reconcile | dw-check | ci | manual
        "tool_version": __version__,
        "timestamp": ts.isoformat(timespec="seconds"),
        "commit": git_commit(root),
        "inputs": inputs,  # {role: digest}; canonical roles: contract, ddl:<name>, sql:<name>, reconcile:spec
        "binding_paths": binding_paths or {},  # {role: path} so verifiers recompute the same digests
        "policy_digest": inputs.get("policy", ""),
        "result_summary": result_summary,
        "environments": environments or {},
        "artifacts": artifacts or [],
        "hand_edited": False,
    }
    evidence["signature"] = _sign(evidence)
    return evidence


def _sign(evidence: Dict) -> str:
    """Optional HMAC (key from DW_HARNESS_EVIDENCE_KEY env only)."""
    import hmac as _hmac
    key = os.environ.get("DW_HARNESS_EVIDENCE_KEY", "")
    if not key:
        return ""
    basis = json.dumps({k: v for k, v in evidence.items() if k != "signature"},
                       sort_keys=True, ensure_ascii=False)
    return _hmac.new(key.encode("utf-8"), basis.encode("utf-8"),
                     "sha256").hexdigest()


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
                    freshness_hours: int = 72, strict: bool = False) -> Dict:
    """Stale when any input digest differs, is missing, or TTL expired.

    Strict mode additionally rejects evidence without a trusted producer:
    hand-written PASS files (producer=manual / hand_edited) are display-only
    and can never gate a strict CI check. When an HMAC key is configured,
    a bad or absent signature is untrusted regardless of mode.
    """
    if not evidence:
        return {"state": "missing", "reason": "no evidence recorded"}
    problems: List[str] = []
    if evidence.get("hand_edited"):
        return {"state": "untrusted", "reason": workspace_edited_warning(evidence) or
                "evidence flagged as hand-edited"}
    key = os.environ.get("DW_HARNESS_EVIDENCE_KEY", "")
    if key:
        expected = _sign({k: v for k, v in evidence.items() if k != "signature"})
        if evidence.get("signature", "") != expected:
            return {"state": "untrusted",
                    "reason": "HMAC signature mismatch (key configured, signature invalid/absent)"}
    if strict:
        producer = str(evidence.get("producer", "manual"))
        if producer == "manual":
            return {"state": "untrusted",
                    "reason": "producer=manual: strict mode only accepts evidence from "
                              "deterministic producers; re-run the producing command"}
        if not key:
            # producer is a plain JSON field: without an HMAC key anyone can
            # write producer="dw-reconcile". Strict mode refuses unsigned
            # producer claims (audit R2). Local closed loop: export the same
            # DW_HARNESS_EVIDENCE_KEY while producing and checking; CI: secret.
            return {"state": "untrusted",
                    "reason": "strict mode requires DW_HARNESS_EVIDENCE_KEY to "
                              "authenticate producer claims; an unsigned "
                              f"producer={producer!r} field can be forged"}
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
