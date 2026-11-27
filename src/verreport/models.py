"""Common data models shared by parsers, analysis and renderers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TestStatus(str, Enum):
    __test__ = False  # not a pytest class

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


# --- Build -----------------------------------------------------------------

@dataclass
class BuildInfo:
    project: str = "VERReport"
    build_number: str = ""
    build_time: datetime | None = None
    commit: str = ""
    branch: str = ""


# --- Google Test -----------------------------------------------------------

@dataclass
class TestCase:
    __test__ = False

    suite: str
    name: str
    status: TestStatus
    time_sec: float = 0.0
    file: str = ""
    line: int = 0
    message: str = ""  # failure message, if any


@dataclass
class GTestResult:
    cases: list[TestCase] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    def count(self, status: TestStatus) -> int:
        return sum(1 for c in self.cases if c.status == status)


# --- Coverage (llvm-cov) ---------------------------------------------------

@dataclass
class CoverageCounter:
    """covered / count pair for one metric (lines, functions, ...)."""

    count: int = 0
    covered: int = 0

    @property
    def percent(self) -> float:
        return (self.covered / self.count * 100.0) if self.count else 100.0


@dataclass
class FunctionCoverage:
    name: str
    execution_count: int = 0
    line: int = 0
    regions: CoverageCounter = field(default_factory=CoverageCounter)


@dataclass
class FileCoverage:
    path: str
    lines: CoverageCounter = field(default_factory=CoverageCounter)
    functions: CoverageCounter = field(default_factory=CoverageCounter)
    regions: CoverageCounter = field(default_factory=CoverageCounter)
    branches: CoverageCounter = field(default_factory=CoverageCounter)
    mcdc: CoverageCounter = field(default_factory=CoverageCounter)  # count == 0 when not measured
    function_details: list[FunctionCoverage] = field(default_factory=list)


@dataclass
class CoverageResult:
    files: list[FileCoverage] = field(default_factory=list)


# --- CPPCheck --------------------------------------------------------------

@dataclass
class Violation:
    rule_id: str
    severity: str  # error / warning / style / performance / portability / information
    message: str
    file: str = ""
    line: int = 0
    column: int = 0


@dataclass
class CppcheckResult:
    version: str = ""
    violations: list[Violation] = field(default_factory=list)


# --- Lizard ----------------------------------------------------------------

@dataclass
class FunctionMetric:
    name: str
    file: str
    start_line: int
    end_line: int
    nloc: int
    ccn: int
    params: int
    length: int  # function line count (end - start + 1)


@dataclass
class LizardResult:
    functions: list[FunctionMetric] = field(default_factory=list)


# --- Aggregate -------------------------------------------------------------

@dataclass
class VerificationData:
    """Everything the report needs. Any tool result may be absent (None)."""

    build: BuildInfo = field(default_factory=BuildInfo)
    gtest: GTestResult | None = None
    coverage: CoverageResult | None = None
    cppcheck: CppcheckResult | None = None
    lizard: LizardResult | None = None
