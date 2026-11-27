"""Lizard CSV (lizard --csv) parser.

Columns: NLOC, CCN, token, PARAM, length, location, file, function,
long_name, start, end  (no header row).
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..models import FunctionMetric, LizardResult
from ._util import ParseError, normalize_path


def parse_lizard(path: str | Path) -> LizardResult:
    result = LizardResult()
    try:
        f = open(path, newline="", encoding="utf-8")
    except FileNotFoundError as e:
        raise ParseError(f"file not found: {path}") from e

    with f:
        for lineno, row in enumerate(csv.reader(f), start=1):
            if not row:
                continue
            if lineno == 1 and not row[0].strip().isdigit():
                continue  # tolerate a header row
            if len(row) < 11:
                raise ParseError(f"{path}:{lineno}: expected 11 columns, got {len(row)}")
            try:
                result.functions.append(
                    FunctionMetric(
                        name=row[7],
                        file=normalize_path(row[6]),
                        start_line=int(row[9]),
                        end_line=int(row[10]),
                        nloc=int(row[0]),
                        ccn=int(row[1]),
                        params=int(row[3]),
                        length=int(row[4]),
                    )
                )
            except ValueError as e:
                raise ParseError(f"{path}:{lineno}: invalid numeric field: {e}") from e
    return result
