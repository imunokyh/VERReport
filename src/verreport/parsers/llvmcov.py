"""llvm-cov JSON export (llvm-cov export -format=text) parser."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import (
    CoverageCounter,
    CoverageResult,
    FileCoverage,
    FunctionCoverage,
)
from ._util import ParseError, normalize_path


def _counter(d: dict | None) -> CoverageCounter:
    d = d or {}
    return CoverageCounter(count=int(d.get("count", 0)), covered=int(d.get("covered", 0)))


def parse_llvmcov(path: str | Path) -> CoverageResult:
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError as e:
        raise ParseError(f"file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise ParseError(f"malformed JSON in {path}: {e}") from e

    if not isinstance(doc, dict) or "data" not in doc:
        raise ParseError(f"{path}: not an llvm-cov export (missing 'data')")

    files: dict[str, FileCoverage] = {}
    for export in doc["data"]:
        for f in export.get("files", []):
            name = normalize_path(f["filename"])
            s = f.get("summary", {})
            files[name] = FileCoverage(
                path=name,
                lines=_counter(s.get("lines")),
                functions=_counter(s.get("functions")),
                regions=_counter(s.get("regions")),
                branches=_counter(s.get("branches")),
                mcdc=_counter(s.get("mcdc")),
            )
        for fn in export.get("functions", []):
            filenames = fn.get("filenames") or []
            if not filenames:
                continue
            target = files.get(normalize_path(filenames[0]))
            if target is None:
                continue
            regions = fn.get("regions", [])
            # region = [LineStart, ColStart, LineEnd, ColEnd, ExecCount, FileID, ExpandedFileID, Kind]
            # Kind 0 = code region. Skipped/gap/branch/expansion regions are not
            # counted by llvm-cov's region summary, so they are excluded here too.
            code = [r for r in regions if len(r) <= 7 or r[7] == 0]
            target.function_details.append(
                FunctionCoverage(
                    name=fn.get("name", ""),
                    execution_count=int(fn.get("count", 0)),
                    line=int(regions[0][0]) if regions else 0,
                    regions=CoverageCounter(
                        count=len(code),
                        covered=sum(1 for r in code if r[4] > 0),
                    ),
                )
            )
    return CoverageResult(files=list(files.values()))
