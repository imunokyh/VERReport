from pathlib import Path

from verreport.analysis import module_of, summarize
from verreport.config import Config
from verreport.models import VerificationData
from verreport.parsers import parse_cppcheck, parse_gtest, parse_lizard, parse_llvmcov

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def sample_data() -> VerificationData:
    return VerificationData(
        gtest=parse_gtest(SAMPLES / "gtest.xml"),
        coverage=parse_llvmcov(SAMPLES / "llvm-cov.json"),
        cppcheck=parse_cppcheck(SAMPLES / "cppcheck.xml"),
        lizard=parse_lizard(SAMPLES / "lizard.csv"),
    )


# --- module_of -------------------------------------------------------------

def test_module_of_depth():
    c = Config(module_depth=2)
    assert module_of("src/core/parser.cc", c) == "src/core"
    assert module_of("src/core/deep/x.cc", c) == "src/core"
    assert module_of("src/x.cc", c) == "src"
    assert module_of("x.cc", c) == "(root)"
    assert module_of("", c) == "(unknown)"
    assert module_of("src\\core\\p.cc", c) == "src/core"


def test_module_of_source_root_and_map():
    c = Config(module_depth=1, source_root="/work/proj")
    assert module_of("/work/proj/core/a.cc", c) == "core"
    c = Config(module_map={"src/core": "Core", "src": "Other"})
    assert module_of("src/core/a.cc", c) == "Core"  # longest prefix wins
    assert module_of("src/net/a.cc", c) == "Other"
    assert module_of("srcx/a.cc", c) == "srcx"  # not a prefix match


# --- per-tool summaries ----------------------------------------------------

def test_gtest_summary():
    s = summarize(sample_data()).gtest
    assert (s.total, s.passed, s.failed, s.skipped) == (8, 5, 2, 1)
    assert not s.passed_ok
    assert round(s.pass_rate, 1) == round(5 / 7 * 100, 1)
    assert {x.name: x.failed for x in s.suites} == {
        "NetClientTest": 1, "ParserTest": 1, "UtilStringTest": 0,
    }
    mods = {m.name: m for m in s.modules}
    assert set(mods) == {"tests/core", "tests/net", "tests/util"}
    assert mods["tests/net"].stats["failed"] == 1
    assert mods["tests/net"].files[0].path == "tests/net/client_test.cc"


def test_coverage_summary():
    s = summarize(sample_data()).coverage
    assert (s.lines.count, s.lines.covered) == (410, 317)
    assert round(s.lines.percent, 2) == 77.32
    assert s.target == 80.0 and not s.passed_ok
    mods = {m.name: m for m in s.modules}
    assert set(mods) == {"src/core", "src/net", "src/util"}
    assert mods["src/net"].stats["lines"].percent == 60.0
    # util = string_utils + log
    assert (mods["src/util"].stats["lines"].count, mods["src/util"].stats["lines"].covered) == (80, 77)
    net_file = mods["src/net"].files[0]
    assert len(net_file.items) == 4  # function details


def test_cppcheck_summary():
    s = summarize(sample_data()).cppcheck
    assert s.total == 10
    assert list(s.by_severity) == ["error", "warning", "style", "performance", "information"]
    assert s.by_severity["error"] == 3 and not s.passed_ok
    assert s.top_rules[0][1] == 1  # all rules unique in sample
    core = next(m for m in s.modules if m.name == "src/core")
    assert core.stats["total"] == 3
    parser_file = core.files[0]
    assert [v.line for v in parser_file.items] == sorted(v.line for v in parser_file.items)


def test_lizard_summary():
    s = summarize(sample_data()).lizard
    assert s.total_functions == 11
    assert (s.ccn_violations, s.length_violations, s.violations) == (3, 2, 3)
    assert not s.passed_ok
    assert [f.name for f in s.worst] == ["Parser::ParseHeader", "Client::Poll", "Client::HandleReset"]
    core = next(m for m in s.modules if m.name == "src/core")
    assert core.stats["violations"] == 1 and core.stats["max_ccn"] == 24


def test_lizard_boundaries_are_strict():
    from verreport.models import FunctionMetric, LizardResult

    fn = FunctionMetric("f", "a/b.cc", 1, 80, 70, 10, 0, 80)  # exactly at limits
    s = summarize(VerificationData(lizard=LizardResult([fn]))).lizard
    assert s.violations == 0 and s.passed_ok


# --- overall ---------------------------------------------------------------

def test_overall_fails_with_sample_data():
    r = summarize(sample_data())
    assert r.tool_results == {
        "gtest": False, "coverage": False, "cppcheck": False, "lizard": False,
    }
    assert not r.passed


def test_overall_with_missing_tools():
    r = summarize(VerificationData())
    assert r.tool_results == {} and not r.passed  # nothing to judge -> not passed
    assert r.gtest is None and r.lizard is None

    from verreport.models import GTestResult
    r = summarize(VerificationData(gtest=GTestResult()))
    assert r.passed  # only tool present, and it has no failures
