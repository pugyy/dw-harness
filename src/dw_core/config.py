"""Project configuration (harness.json) and dialect resolution.

Resolution order for dialects (documented contract, see docs/configuration.md):
    1. explicit argument (--dialect / API parameter)
    2. project path mapping  (dialect.by_path)
    3. legacy env variable   (DW_HARNESS_DIALECT)
    4. configured default    (dialect.default, fallback "odps")
"""
from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

SUPPORTED_DIALECTS = ("odps", "hive", "spark", "starrocks")
DIALECT_ENV = "DW_HARNESS_DIALECT"

DEFAULT_CONFIG: Dict[str, Any] = {
    "version": 2,
    "dialect": {
        "default": "odps",
        "by_path": {
            "**/sr/**": "starrocks",
            "**/*_sr_*.sql": "starrocks",
            "**/spark/**": "spark",
            "**/*_spark*.sql": "spark",
            "**/hive/**": "hive",
            "**/*_hive*.sql": "hive",
        },
    },
    "rules": {},
    "money_fields": "amount|amt|price|fee|cost|money|pay|revenue|gmv|refund|tax|balance|net_amount",
    "partition_column": "partition_dt",
    "protected_objects": [],
    "pii": {
        "enabled": True,
        "scan_globs": ["**/*.sql", "**/*.csv", "**/data/**"],
        "patterns": ["cn_phone", "cn_id_card", "bank_card"],
        "action": "warn",
    },
    "guard": {
        "destructive": "deny",
        "overwrite_without_partition": "ask",
        "future_partition": "ask",
        "unknown_write": "ask",
    },
    "reconcile": {"sample_rows": 20, "max_rows": 1000000, "query_timeout_seconds": 60},
    "evidence": {"freshness_hours": 72},
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def normalize_dialect(value: Optional[str]) -> str:
    value = (value or "").strip().lower()
    if value == "maxcompute":
        return "odps"
    if value == "sr":
        return "starrocks"
    return value if value in SUPPORTED_DIALECTS else ""


def find_project_root(start: Optional[Path] = None) -> Path:
    """Walk up looking for the harness config marker (.claude/dw or .git)."""
    cur = Path(start or os.getcwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / ".claude" / "dw").is_dir():
            return candidate
        if (candidate / ".git").exists():
            return candidate
    return cur


class HarnessConfig:
    def __init__(self, data: Dict[str, Any], root: Path, path: Optional[Path],
                 dialect_dir: Optional[Path] = None):
        self.data = data
        self.root = root
        self.path = path
        # dialect packs ship INSIDE the dw_core package (wheel-safe); an
        # explicit dialect_dir wins (tests / custom packs)
        self.dialect_dir = dialect_dir or _bundled_dialect_dir()
        self._dialect_packs: Dict[str, Dict[str, Any]] = {}

    # -- loading ---------------------------------------------------------
    @classmethod
    def load(cls, root: Optional[Path] = None, start: Optional[Path] = None) -> "HarnessConfig":
        project = Path(root) if root else find_project_root(start)
        cfg_path = project / ".claude" / "dw" / "harness.json"
        data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        if cfg_path.is_file():
            try:
                user = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as exc:
                raise ConfigError(f"harness.json is not valid JSON: {exc}") from exc
            data = _deep_merge(data, user)
        return cls(data, project, cfg_path if cfg_path.is_file() else None)

    @property
    def exists(self) -> bool:
        return self.path is not None

    # -- dialect packs ----------------------------------------------------
    def dialect_pack(self, dialect: str) -> Dict[str, Any]:
        if dialect in self._dialect_packs:
            return self._dialect_packs[dialect]
        pack: Dict[str, Any] = {}
        path = self.dialect_dir / f"{dialect}.json"
        if path.is_file():
            try:
                pack = json.loads(path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, OSError):
                pack = {}
        self._dialect_packs[dialect] = pack
        return pack

    # -- dialect ---------------------------------------------------------
    def resolve_dialect(
        self,
        file_path: Optional[str] = None,
        explicit: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> str:
        dialect = normalize_dialect(explicit)
        if dialect:
            return dialect
        posix = Path(file_path).as_posix() if file_path else ""
        for pattern, value in (self.data.get("dialect", {}).get("by_path") or {}).items():
            if posix and fnmatch.fnmatch(posix.lower(), pattern.lower()):
                dialect = normalize_dialect(value)
                if dialect:
                    return dialect
        env_map = env if env is not None else dict(os.environ)
        dialect = normalize_dialect(env_map.get(DIALECT_ENV, ""))
        if dialect:
            return dialect
        return normalize_dialect(self.data.get("dialect", {}).get("default")) or "odps"

    # -- rules -----------------------------------------------------------
    def rule_level(self, rule_id: str, default_level: str, dialect: Optional[str] = None) -> str:
        overrides = dict(self.data.get("rules") or {})
        if dialect:
            # project config first, then the shipped dialect pack
            overrides.update((self.data.get("dialect_rules") or {}).get(dialect) or {})
            overrides.update((self.dialect_pack(dialect) or {}).get("rule_levels") or {})
        level = str(overrides.get(rule_id, default_level)).lower()
        return level if level in ("error", "warn", "off") else default_level

    # -- helpers ---------------------------------------------------------
    @property
    def money_fields_pattern(self) -> str:
        return str(self.data.get("money_fields") or DEFAULT_CONFIG["money_fields"])

    @property
    def partition_column(self) -> str:
        return str(self.data.get("partition_column") or "partition_dt")

    @property
    def protected_objects(self) -> List[str]:
        return [str(o) for o in (self.data.get("protected_objects") or [])]

    def dw_dir(self) -> Path:
        return self.root / ".claude" / "dw"

    def is_prod(self, env: Optional[Dict[str, str]] = None) -> bool:
        env_map = env if env is not None else dict(os.environ)
        markers = ["DW_HARNESS_PROD"]
        for marker in markers:
            if env_map.get(marker, "") not in ("", "0", "false", "False"):
                return True
        return False


class ConfigError(Exception):
    pass


def _bundled_dialect_dir() -> Path:
    """dw_core/data/dialects via importlib.resources (works in editable,
    wheel and plugin/template copies alike)."""
    try:
        import importlib.resources as _res
        return Path(str(_res.files("dw_core") / "data" / "dialects"))
    except Exception:  # pragma: no cover - very old importlib
        return Path(__file__).resolve().parent / "data" / "dialects"
