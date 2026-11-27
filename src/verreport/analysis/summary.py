"""Per-tool aggregation and overall verdict."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..config import Config
from ..models import (
    BuildInfo,
    CoverageCounter,
    CoverageResult,
    CppcheckResult,
    FileCoverage,
    GTestResult,
    LizardResult,
    TestStatus,
    VerificationData,
)
from .grouping import ModuleGroup, group_by_module

SEVERITY_ORDER = ["error", "warning", "style", "performance", "portability", "information"]


# --- GTest -----------------------------------------------------------------

@dataclass
class SuiteSummary:
    name: str
    total: int
    passed: int
    failed: int
    skipped: int
    time_sec: float


@dataclass
class GTestSummary:
    total: int
    passed: int
    failed: int
    skipped: int
    time_sec: float
    suites: list[SuiteSummary]
    modules: list[ModuleGroup]  # grouped by test source file; items = TestCase
    passed_ok: bool  # no failed tests

    @property
    def pass_rate(self) -> float:
        run = self.total - self.skipped
        return (self.passed / run * 100.0) if run else 100.0


def _gtest_stats(cases) -> dict:
    return {
        "total": len(cases),
        "passed": sum(1 for c in cases if c.status == TestStatus.PASSED),
        "failed": sum(1 for c in cases if c.status == TestStatus.FAILED),
        "skipped": sum(1 for c in cases if c.status == TestStatus.SKIPPED),
        "time_sec": sum(c.time_sec for c in cases),
    }


def summarize_gtest(r: GTestResult, config: Config) -> GTestSummary:
    suites: dict[str, list] = {}
    for c in r.cases:
        suites.setdefault(c.suite, []).append(c)
    suite_rows = [SuiteSummary(name=n, **_gtest_stats(cs)) for n, cs in sorted(suites.items())]

    modules = group_by_module(r.cases, lambda c: c.file, config)
    for m in modules:
        for f in m.files:
            f.stats = _gtest_stats(f.items)
        m.stats = _gtest_stats(m.items)

    s = _gtest_stats(r.cases)
    return GTestSummary(suites=suite_rows, modules=modules, passed_ok=s["failed"] == 0, **s)


# --- Coverage --------------------------------------------------------------

METRICS = ("lines", "functions", "regions", "branches", "mcdc")


@dataclass
class CoverageSummary:
    lines: CoverageCounter
    functions: CoverageCounter
    regions: CoverageCounter
    branches: CoverageCounter
    mcdc: CoverageCounter  # count == 0 when MC/DC was not measured
    modules: list[ModuleGroup]  # files grouped; items = FunctionCoverage
    target: float
    passed_ok: bool  # line coverage >= target


def _sum_counters(files: list[FileCoverage]) -> dict[str, CoverageCounter]:
    out = {}
    for m in METRICS:
        out[m] = CoverageCounter(
            count=sum(getattr(f, m).count for f in files),
            covered=sum(getattr(f, m).covered for f in files),
        )
    return out


def summarize_coverage(r: CoverageResult, config: Config) -> CoverageSummary:
    by_path = {f.path: f for f in r.files}
    modules = group_by_module(r.files, lambda f: f.path, config)
    for m in modules:
        files = [by_path[fg.path] for fg in m.files]
        # group_by_module put FileCoverage objects as items; replace with functions
        for fg, fc in zip(m.files, files):
            fg.items = list(fc.function_details)
            fg.stats = {k: getattr(fc, k) for k in METRICS}
        m.stats = _sum_counters(files)

    totals = _sum_counters(r.files)
    target = config.thresholds.coverage_line
    return CoverageSummary(
        modules=modules,
        target=target,
        passed_ok=totals["lines"].percent >= target,
        **totals,
    )


# --- CPPCheck --------------------------------------------------------------

@dataclass
class CppcheckSummary:
    total: int
    by_severity: dict[str, int]
    top_rules: list[tuple[str, int]]
    modules: list[ModuleGroup]  # items = Violation
    passed_ok: bool  # no 'error' severity violations


def _severity_counts(vs) -> dict[str, int]:
    c = Counter(v.severity for v in vs)
    ordered = {s: c[s] for s in SEVERITY_ORDER if s in c}
    ordered.update({s: n for s, n in c.items() if s not in ordered})
    return ordered


def summarize_cppcheck(r: CppcheckResult, config: Config) -> CppcheckSummary:
    modules = group_by_module(r.violations, lambda v: v.file, config)
    for m in modules:
        for f in m.files:
            f.items.sort(key=lambda v: v.line)
            f.stats = {"total": len(f.items), "by_severity": _severity_counts(f.items)}
        m.stats = {"total": len(m.items), "by_severity": _severity_counts(m.items)}

    by_sev = _severity_counts(r.violations)
    rules = Counter(v.rule_id for v in r.violations).most_common()
    return CppcheckSummary(
        total=len(r.violations),
        by_severity=by_sev,
        top_rules=rules,
        modules=modules,
        passed_ok=by_sev.get("error", 0) == 0,
    )


# --- Lizard ----------------------------------------------------------------

@dataclass
class LizardSummary:
    total_functions: int
    ccn_violations: int
    length_violations: int
    violations: int  # functions violating at least one rule
    ccn_limit: int
    length_limit: int
    modules: list[ModuleGroup]  # items = FunctionMetric (all functions)
    worst: list = field(default_factory=list)  # violating functions, worst CCN first
    passed_ok: bool = True


def summarize_lizard(r: LizardResult, config: Config) -> LizardSummary:
    ccn_max = config.thresholds.lizard_ccn
    len_max = config.thresholds.lizard_length

    def stats(fns) -> dict:
        ccn_v = sum(1 for f in fns if f.ccn > ccn_max)
        len_v = sum(1 for f in fns if f.length > len_max)
        return {
            "functions": len(fns),
            "ccn_violations": ccn_v,
            "length_violations": len_v,
            "violations": sum(1 for f in fns if f.ccn > ccn_max or f.length > len_max),
            "max_ccn": max((f.ccn for f in fns), default=0),
            "max_length": max((f.length for f in fns), default=0),
        }

    modules = group_by_module(r.functions, lambda f: f.file, config)
    for m in modules:
        for f in m.files:
            f.items.sort(key=lambda fn: fn.start_line)
            f.stats = stats(f.items)
        m.stats = stats(m.items)

    s = stats(r.functions)
    worst = sorted(
        (f for f in r.functions if f.ccn > ccn_max or f.length > len_max),
        key=lambda f: (f.ccn, f.length),
        reverse=True,
    )
    return LizardSummary(
        total_functions=s["functions"],
        ccn_violations=s["ccn_violations"],
        length_violations=s["length_violations"],
        violations=s["violations"],
        ccn_limit=ccn_max,
        length_limit=len_max,
        modules=modules,
        worst=worst,
        passed_ok=s["violations"] == 0,
    )


# --- Overall ---------------------------------------------------------------

@dataclass
class ReportSummary:
    build: BuildInfo
    config: Config
    gtest: GTestSummary | None
    coverage: CoverageSummary | None
    cppcheck: CppcheckSummary | None
    lizard: LizardSummary | None

    @property
    def tool_results(self) -> dict[str, bool]:
        """tool name -> passed, only for tools that have results."""
        out = {}
        for name in ("gtest", "coverage", "cppcheck", "lizard"):
            s = getattr(self, name)
            if s is not None:
                out[name] = s.passed_ok
        return out

    @property
    def passed(self) -> bool:
        res = self.tool_results
        return bool(res) and all(res.values())


def summarize(data: VerificationData, config: Config | None = None) -> ReportSummary:
    config = config or Config()
    return ReportSummary(
        build=data.build,
        config=config,
        gtest=summarize_gtest(data.gtest, config) if data.gtest else None,
        coverage=summarize_coverage(data.coverage, config) if data.coverage else None,
        cppcheck=summarize_cppcheck(data.cppcheck, config) if data.cppcheck else None,
        lizard=summarize_lizard(data.lizard, config) if data.lizard else None,
    )
