"""CPPCheck XML (--xml --xml-version=2) parser."""

from __future__ import annotations

from pathlib import Path

from ..models import CppcheckResult, Violation
from ._util import ParseError, load_xml, normalize_path, to_int


def parse_cppcheck(path: str | Path) -> CppcheckResult:
    root = load_xml(path)
    if root.tag != "results":
        raise ParseError(f"{path}: unexpected root element <{root.tag}>")

    version_el = root.find("cppcheck")
    result = CppcheckResult(version=version_el.get("version", "") if version_el is not None else "")

    for err in root.findall("./errors/error"):
        loc = err.find("location")  # first location is the primary one
        result.violations.append(
            Violation(
                rule_id=err.get("id", ""),
                severity=err.get("severity", ""),
                message=err.get("msg") or err.get("verbose", ""),
                file=normalize_path(loc.get("file", "")) if loc is not None else "",
                line=to_int(loc.get("line")) if loc is not None else 0,
                column=to_int(loc.get("column")) if loc is not None else 0,
            )
        )
    return result
