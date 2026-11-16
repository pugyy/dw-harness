"""Pre-execution guards: shell commands (Bash/PowerShell) and file writes.

Policy outcomes are deny / ask / allow with reasons. Decisions are logged to
``.claude/dw/guard_log.jsonl`` keyed by a truncated input hash. Exceptions are
bounded by expiry date, approver, environment, object and operation.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import HarnessConfig
from .rules import lint_sql
from .sqlsplit import scan_sql

# Registered database clients whose commands may embed SQL.
DB_CLIENTS = {
    "odpscmd", "maxc", "beeline", "hive", "spark-sql", "spark3-beeline",
    "mysql", "psql", "sqlplus", "trino", "duckdb", "sqlite3",
}

SQL_KEYWORD_HINT = re.compile(
    r"\b(insert\s+|delete\s+from|drop\s+table|drop\s+database|truncate|alter\s+table|update\s+\w+\s+set|merge\s+into)\b",
    re.I,
)
_FILE_ARGS = {"-f", "--file", "-sql-file"}
_EXEC_ARGS = {"-e", "--execute", "--exec", "-q", "--query"}

PII_PATTERNS = {
    "cn_phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "cn_id_card": re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)"),
    "bank_card": re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
}


@dataclass
class GuardDecision:
    decision: str  # deny | ask | allow
    reasons: List[str] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "decision": self.decision,
            "reasons": self.reasons,
            "exceptions": self.exceptions,
            "details": self.details,
        }


def _hash12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]


def mask_value(sample: str) -> str:
    if len(sample) <= 6:
        return sample[:1] + "***"
    return sample[:3] + "***" + sample[-2:]


def scan_pii(text: str, patterns: List[str]) -> List[Dict]:
    hits: List[Dict] = []
    lines = re.split(r"\r\n|\r|\n", text)
    for name in patterns:
        rx = PII_PATTERNS.get(name)
        if not rx:
            continue
        for lineno, line in enumerate(lines, start=1):
            for m in rx.finditer(line):
                hits.append({
                    "pattern": name,
                    "line": lineno,
                    "sample": mask_value(m.group(0)),
                })
    return hits


class GuardEngine:
    def __init__(self, config: HarnessConfig, env: Optional[Dict[str, str]] = None,
                 today: Optional[date] = None):
        self.config = config
        self.env = env
        self.today = today or date.today()
        self.prod = config.is_prod(self.env)

    # ------------------------------------------------------------------ #
    # shell commands                                                      #
    # ------------------------------------------------------------------ #
    def evaluate_command(self, command: str, cwd: Optional[Path] = None) -> GuardDecision:
        sql_sources = []
        client = ""
        # Separate commands without interpreting shell expansions or separators in quotes.
        for segment in re.findall(r"""(?:[^"';&|\n]|"(?:\\.|[^"\\])*"|'[^']*')+""", command):
            segment = segment.strip()
            if not segment:
                continue
            change_dir = re.fullmatch(r"(?:cd|set-location)\s+(.+)", segment, re.I)
            if change_dir:
                dest = Path(change_dir[1].strip("\"'"))
                cwd = dest if dest.is_absolute() else (cwd or Path.cwd()) / dest
                continue
            name, sources = self._collect_sql(segment, cwd)
            if name:
                client = name
                sql_sources.extend(sources or [(name, None)])
        if not client:
            return self._finish("PreToolUse:Bash", command,
                                GuardDecision("allow",
                                              reasons=["not a registered database client; SQL guard not applicable"]))
        reasons: List[str] = []
        exceptions_hit: List[str] = []
        worst = "allow"
        statements_total: List[Dict] = []
        for origin, sql in sql_sources:
            if sql is None:
                decision = self._unknown_write_policy(
                    f"'{client}' SQL source {origin} is missing or unreadable")
                reasons.extend(decision.reasons)
                worst = _worst(worst, decision.decision)
                continue
            statements, problems = scan_sql(sql)
            if problems:
                decision = self._unknown_write_policy(f"SQL could not be parsed: {origin}")
                reasons.extend(decision.reasons)
                worst = _worst(worst, decision.decision)
            for st_index, statement in enumerate(statements):
                info = self._classify(statement.code, statement.text)
                info["origin"] = origin
                info["statement_index"] = st_index
                info["line"] = statement.start_line
                statements_total.append(info)
                obj = info["table"]
                for pol_key in ("destructive", "overwrite_without_partition",
                                "future_partition", "overwrite", "unknown_write"):
                    if not info["flags"].get(pol_key):
                        continue
                    if pol_key == "overwrite":
                        # scoped INSERT OVERWRITE: fine in dev, needs a human in prod
                        if self.prod:
                            exc = self._match_exception("overwrite", obj)
                            if exc:
                                exceptions_hit.append(exc["id"])
                                continue
                            reasons.append(f"[{obj or 'unknown'}] overwrite: production env; "
                                           f"confirm scope or use the release pipeline")
                            worst = _worst(worst, "deny")
                        continue
                    exc = self._match_exception(pol_key, obj)
                    if exc:
                        exceptions_hit.append(exc["id"])
                        continue
                    level = self.config.data["guard"].get(pol_key, "ask")
                    if self.prod and pol_key in ("destructive", "unknown_write") and level == "ask":
                        level = "deny"
                        reasons.append(f"[{obj or 'unknown'}] {pol_key}: {info['flags'][pol_key]}; "
                                       f"production env escalates 'ask' to 'deny'; use the release pipeline")
                    else:
                        reasons.append(f"[{obj or 'unknown'}] {pol_key}: {info['flags'][pol_key]}")
                    worst = _worst(worst, level)
        if not statements_total:
            return self._finish("PreToolUse:Bash", command,
                                GuardDecision(worst, reasons=reasons or ["no SQL statements detected in command"]))
        decision = GuardDecision(worst if worst != "allow" else "allow",
                                 reasons=reasons or ["all statements covered by active policy exceptions"],
                                 exceptions=exceptions_hit,
                                 details={"client": client, "statements": statements_total})
        return self._finish("PreToolUse:Bash", command, decision)

    def _finish(self, event: str, input_text: str, decision: GuardDecision) -> GuardDecision:
        self.log(event, {"input": input_text[:120]}, decision, input_text)
        return decision

    def _collect_sql(self, command: str, cwd: Optional[Path]) -> Tuple[str, List[Tuple[str, str]]]:
        def unquote(token: str) -> str:
            for quote in ('"', "'"):
                if len(token) >= 2 and token.startswith(quote) and token.endswith(quote):
                    return token[1:-1]
            return token

        # Preserve Windows backslashes and quoted values in --file=... .
        argv = [unquote(t) for t in re.findall(r"""(?:[^\s"\x27]+|"[^"]*"|\x27[^\x27]*\x27)+""", command)]
        if not argv:
            return "", []
        raw_exe = argv[0]
        exe = raw_exe.replace("\\", "/").rsplit("/", 1)[-1].lower()
        stem = Path(exe).stem
        # Windows wrappers: odpscmd.exe / beeline.cmd / hive.bat all count
        if exe not in DB_CLIENTS and stem not in DB_CLIENTS:
            return "", []
        sources: List[Tuple[str, str]] = []
        i = 1
        while i < len(argv):
            arg = argv[i]
            option, eq, attached = arg.partition("=")
            if option.lower() in _FILE_ARGS | _EXEC_ARGS:
                value = unquote(attached) if eq else argv[i + 1] if i + 1 < len(argv) else ""
                i += 1 if eq or i + 1 == len(argv) else 2
                if not value:
                    sources.append((option, None))
                elif option.lower() in _FILE_ARGS:
                    script = Path(value)
                    if not script.is_absolute():
                        script = (cwd or Path.cwd()) / script
                    try:
                        sql = script.read_text(encoding="utf-8-sig")
                    except (OSError, UnicodeError):
                        sql = None
                    sources.append((f"file:{script.name}", sql))
                else:
                    sources.append((f"inline:{option}", value))
                continue
            if SQL_KEYWORD_HINT.search(arg):
                sources.append(("inline:arg", arg))
                i += 1
                continue
            i += 1
        return exe, sources

    def _classify(self, code: str, text: Optional[str] = None) -> Dict:
        """Keyword checks run on blanked *code*; literal checks on *text*."""
        flags: Dict[str, str] = {}
        table = _target_table(code)
        low = code.lstrip().lower()
        if re.search(r"\bdrop\s+(table|database)\b", code, re.I) or re.search(r"\btruncate\s+table\b", code, re.I) \
                or re.search(r"\balter\s+table\b[\s\S]*?\bdrop\s+(column|partition)\b", code, re.I):
            flags["destructive"] = "destructive DDL detected"
        elif re.match(r"(?:delete\s+from|update\s+)\b", low):
            depth = 0
            for token in re.findall(r"\(|\)|\bwhere\b", low):
                if token == "(":
                    depth += 1
                elif token == ")":
                    depth -= 1
                elif depth == 0:
                    break
            else:
                flags["destructive"] = f"{low.split()[0].upper()} without a top-level WHERE"
        if re.search(r"\binsert\s+overwrite\b", code, re.I):
            flags["overwrite"] = "INSERT OVERWRITE with confirmed partition scope"
            literal_source = text if text is not None else code
            head = re.split(r"\b(?:select|values)\b", code, maxsplit=1, flags=re.I)[0]
            part = re.search(r"\bpartition\s*\(([^)]*)\)", head, re.I)
            if not part:
                flags["overwrite_without_partition"] = "INSERT OVERWRITE without explicit PARTITION clause"
            else:
                assignment = literal_source[part.start(1):part.end(1)]
                literal = re.fullmatch(
                    rf"\s*`?{re.escape(self.config.partition_column)}`?\s*=\s*'([^']*)'\s*",
                    assignment, re.I)
                if not literal:
                    flags["overwrite_without_partition"] = "partition value is not a literal (dynamic/expression)"
                else:
                    value = literal.group(1).strip()
                    if not re.fullmatch(r"\d{8}", value):
                        flags["future_partition"] = f"partition literal '{value}' is not yyyyMMdd"
                    else:
                        try:
                            part_date = datetime.strptime(value, "%Y%m%d").date()
                            if part_date > self.today:
                                flags["future_partition"] = f"partition {value} is in the future"
                        except ValueError:
                            flags["future_partition"] = f"partition literal '{value}' is not a valid date"
        elif low.startswith(("insert", "update", "merge")) and not table:
            flags["unknown_write"] = "write statement but target table could not be determined"
        if table in self.config.protected_objects and low.startswith(("insert", "update", "merge",
                                                                      "delete", "drop", "truncate", "alter")):
            flags["destructive"] = (flags.get("destructive", "") + f"; target {table} is a protected object").strip("; ")
        return {"flags": flags, "table": table, "verb": low.split()[0] if low.split() else ""}

    def _unknown_write_policy(self, reason: str) -> GuardDecision:
        level = self.config.data["guard"]["unknown_write"]
        if self.prod and level == "ask":
            level = "deny"
        return GuardDecision(level, reasons=[reason +
                           ("; production env escalates to deny" if self.prod and level == "deny" else "")])

    # ------------------------------------------------------------------ #
    # writes (Write/Edit tool payloads)                                   #
    # ------------------------------------------------------------------ #
    def evaluate_write(self, file_path: str, content: str) -> GuardDecision:
        reasons: List[str] = []
        worst = "allow"
        pii_conf = self.config.data.get("pii", {})
        posix = Path(file_path).as_posix() if file_path else ""
        if pii_conf.get("enabled"):
            import fnmatch
            for glob in pii_conf.get("scan_globs", []):
                if posix and fnmatch.fnmatch(posix.lower(), glob.lower()):
                    hits = scan_pii(content, [str(p) for p in pii_conf.get("patterns", [])])
                    if hits:
                        action = str(pii_conf.get("action", "warn"))
                        sample = ", ".join(f"{h['pattern']}@line{h['line']}({h['sample']})" for h in hits[:5])
                        msg = f"possible PII in {Path(file_path).name}: {sample}; consider masking or moving data out"
                        if action == "deny":
                            reasons.append(msg)
                            worst = _worst(worst, "deny")
                        else:
                            reasons.append(msg)
                    break
        if content and len(content) > 5 * 1024 * 1024:
            reasons.append("file larger than 5MB; likely wrong target for AI write")
            worst = _worst(worst, "deny")
        if content and file_path.lower().endswith(".sql"):
            for statement in scan_sql(content)[0]:
                info = self._classify(statement.code)
                if info["table"] in self.config.protected_objects and info["flags"]:
                    exc = self._match_exception("destructive", info["table"])
                    if exc:
                        continue
                    reasons.append(f"[{info['table']}] protected object: {info['flags'].get('destructive', 'write')}")
                    worst = _worst(worst, "deny")
        return GuardDecision(worst, reasons=reasons)

    # ------------------------------------------------------------------ #
    # exceptions                                                          #
    # ------------------------------------------------------------------ #
    def _exceptions(self) -> List[Dict]:
        path = self.config.dw_dir() / "policy_exceptions.json"
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, list) else data.get("exceptions", [])
        except (json.JSONDecodeError, OSError):
            return []

    def _match_exception(self, operation: str, obj: Optional[str]) -> Optional[Dict]:
        env_name = "prod" if self.prod else "dev"
        for exc in self._exceptions():
            if operation not in exc.get("operations", []) and "*" not in exc.get("operations", []):
                continue
            if exc.get("environment") not in (env_name, "*"):
                continue
            objects = exc.get("objects", [])
            if objects and obj not in objects and "*" not in objects:
                continue
            try:
                not_after = datetime.strptime(str(exc.get("not_after", "")), "%Y-%m-%d").date()
            except ValueError:
                continue  # malformed expiry never grants
            if self.today > not_after:
                continue  # expired: treated as absent
            return exc
        return None

    # ------------------------------------------------------------------ #
    # logging                                                             #
    # ------------------------------------------------------------------ #
    def log(self, event: str, payload: Dict, decision: GuardDecision, input_text: str) -> None:
        try:
            log_dir = self.config.dw_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "event": event,
                "input_sha256_12": _hash12(input_text),
                "decision": decision.decision,
                "reasons": decision.reasons,
                "exceptions": decision.exceptions,
            }
            with (log_dir / "guard_log.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass


def _worst(current: str, candidate: str) -> str:
    rank = {"allow": 0, "ask": 1, "deny": 2}
    return candidate if rank[candidate] > rank[current] else current


def _target_table(code: str) -> str:
    m = re.search(r"\b(?:insert\s+(?:overwrite\s+)?into|insert\s+overwrite|update|delete\s+from|drop\s+table|truncate\s+table|alter\s+table|merge\s+into)\s+(?:table\s+)?([\w.`\[\]\"']+)", code, re.I)
    if not m:
        return ""
    return m.group(1).strip("`[]\"'")


def lint_for_guard(sql: str, dialect: str, config: HarnessConfig):
    """Shared rule evaluation used by both the CLI and hook adapters."""
    return lint_sql(sql, dialect, config)
