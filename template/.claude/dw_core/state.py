"""Iteration state (.claude/dw/state.json) and step inference from deliverables."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

STEPS = [
    (1, "requirement-analysis", ["**/01_requirement*.md", "**/requirement*.md"]),
    (2, "technical-design", ["**/02_design*.md", "**/design*.md"]),
    (3, "etl", ["**/ddl_*.sql", "**/insert_*.sql"]),
    (4, "self-test", ["**/04_self_test*.md", "**/self_test*.md"]),
    (5, "data-comparison", ["**/.claude/dw/evidence/reconcile-*.json"]),
    (6, "sr", ["**/ddl_sr_*.sql"]),
    (7, "performance-optimization", ["**/07_perf*.md", "**/perf*.md"]),
    (8, "dqc", ["**/dqc_*.json"]),
]


def state_path(root: Path) -> Path:
    return root / ".claude" / "dw" / "state.json"


def load_state(root: Path) -> Dict:
    path = state_path(root)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(root: Path, state: Dict) -> Path:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _matches(root: Path, patterns: List[str]) -> List[str]:
    found: List[str] = []
    for pattern in patterns:
        for path in root.glob(pattern):
            if ".git" in path.parts:
                continue
            found.append(path.relative_to(root).as_posix())
    return sorted(set(found))


def infer_step(root: Path) -> Dict:
    """Progress inferred from verified deliverables, not from chat memory."""
    completed: List[Dict] = []
    next_step = None
    for number, name, patterns in STEPS:
        deliverables = _matches(root, patterns)
        if deliverables and next_step is None:
            completed.append({"step": number, "name": name, "deliverables": deliverables[:3]})
        elif not deliverables and next_step is None:
            next_step = {"step": number, "name": name, "missing": patterns[:2]}
    return {"completed": completed, "next": next_step}


def session_card(root: Path, max_chars: int = 2000) -> str:
    """Short task summary injected at SessionStart (startup/resume/clear/compact)."""
    state = load_state(root)
    progress = infer_step(root)
    lines: List[str] = ["[dw-harness] 会话状态卡（SessionStart 注入）"]
    table = state.get("table")
    if table:
        lines.append(f"- 当前表: {table}  版本: {state.get('version', '-')}  "
                     f"Step: {state.get('step', '-')}")
    constraints = state.get("constraints") or []
    for c in constraints[:5]:
        lines.append(f"- 约束: {c}")
    nxt = progress.get("next")
    if nxt:
        lines.append(f"- 下一步: Step {nxt['step']}/8 {nxt['name']}（按已验证交付物推断）")
    else:
        lines.append("- 八步流程交付物齐全或尚未初始化；用 /dw-next 查看详情")
    lines.append("- 完整规范: AGENTS.md（CLAUDE.md 引用）；契约: contracts/")
    card = "\n".join(lines)
    return card[:max_chars]
