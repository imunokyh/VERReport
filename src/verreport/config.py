"""Report configuration (thresholds, module mapping) and YAML loading."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(Exception):
    """Raised for an unreadable or invalid configuration file."""


@dataclass
class Thresholds:
    lizard_ccn: int = 10      # violation if CCN > this
    lizard_length: int = 80   # violation if function length > this
    coverage_line: float = 80.0  # target percent (used for judging)


@dataclass
class Config:
    project: str = "VERReport"
    thresholds: Thresholds = field(default_factory=Thresholds)
    # Module = first N path components of a source file (relative to source_root).
    module_depth: int = 2
    source_root: str = ""
    # Optional explicit mapping: path prefix -> module name (takes precedence).
    module_map: dict[str, str] = field(default_factory=dict)
    # Tool result files: gtest / llvm_cov / cppcheck / lizard -> list of paths or globs.
    # Only gtest may list more than one file (results are merged).
    inputs: dict[str, list[str]] = field(default_factory=dict)


INPUT_KEYS = ("gtest", "llvm_cov", "cppcheck", "lizard")
_TOP_KEYS = {"project", "thresholds", "module_depth", "source_root", "module_map", "inputs"}
_THRESHOLD_KEYS = {"lizard_ccn": int, "lizard_length": int, "coverage_line": float}


def _check_keys(section: str, given: dict, allowed) -> None:
    unknown = sorted(set(given) - set(allowed))
    if unknown:
        raise ConfigError(f"unknown key(s) in {section}: {', '.join(map(str, unknown))}")


def _number(name: str, value, typ):
    # bool is a subclass of int; reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number, got {value!r}")
    return typ(value)


def load_config(path: str | Path) -> Config:
    """Load a YAML config. Relative input paths resolve against the file's directory."""
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"config file not found: {path}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML in {path}: {e}") from e

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    _check_keys("config", raw, _TOP_KEYS)

    cfg = Config()
    if "project" in raw:
        cfg.project = str(raw["project"])
    if "module_depth" in raw:
        cfg.module_depth = _number("module_depth", raw["module_depth"], int)
        if cfg.module_depth < 1:
            raise ConfigError("module_depth must be >= 1")
    if "source_root" in raw:
        cfg.source_root = str(raw["source_root"])

    th = raw.get("thresholds") or {}
    if not isinstance(th, dict):
        raise ConfigError("thresholds must be a mapping")
    _check_keys("thresholds", th, _THRESHOLD_KEYS)
    for key, typ in _THRESHOLD_KEYS.items():
        if key in th:
            setattr(cfg.thresholds, key, _number(f"thresholds.{key}", th[key], typ))

    mm = raw.get("module_map") or {}
    if not isinstance(mm, dict):
        raise ConfigError("module_map must be a mapping of path prefix -> module name")
    cfg.module_map = {str(k): str(v) for k, v in mm.items()}

    inputs = raw.get("inputs") or {}
    if not isinstance(inputs, dict):
        raise ConfigError("inputs must be a mapping")
    _check_keys("inputs", inputs, INPUT_KEYS)
    for key, value in inputs.items():
        items = value if isinstance(value, list) else [value]
        items = [str(v) for v in items if v]
        if len(items) > 1 and key != "gtest":
            raise ConfigError(f"inputs.{key} accepts a single file; only gtest may list several")
        if items:
            cfg.inputs[key] = [
                v if os.path.isabs(v) else os.path.abspath(os.path.join(path.parent, v)) for v in items
            ]
    return cfg
