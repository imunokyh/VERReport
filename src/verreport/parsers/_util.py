"""Shared helpers for parsers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


class ParseError(Exception):
    """Raised when a tool result file is missing or malformed."""


def normalize_path(p: str) -> str:
    """Use forward slashes and drop a leading './'."""
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def load_xml(path: str | Path) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except FileNotFoundError as e:
        raise ParseError(f"file not found: {path}") from e
    except ET.ParseError as e:
        raise ParseError(f"malformed XML in {path}: {e}") from e


def to_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


def to_float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except ValueError:
        return default
