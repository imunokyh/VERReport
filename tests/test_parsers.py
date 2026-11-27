from pathlib import Path

import pytest

from verreport.models import TestStatus
from verreport.parsers import (
    ParseError,
    parse_cppcheck,
    parse_gtest,
    parse_lizard,
    parse_llvmcov,
)

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


# --- gtest -----------------------------------------------------------------

def test_gtest_sample():
    r = parse_gtest(SAMPLES / "gtest.xml")
    assert r.total == 8
    assert r.count(TestStatus.PASSED) == 5
    assert r.count(TestStatus.FAILED) == 2
    assert r.count(TestStatus.SKIPPED) == 1
    failed = next(c for c in r.cases if c.name == "RejectsMalformedHeader")
    assert failed.suite == "ParserTest"
    assert failed.file == "tests/core/parser_test.cc" and failed.line == 41
    assert "ERR_BAD_HEADER" in failed.message


def test_gtest_single_testsuite_root(tmp_path):
    p = tmp_path / "g.xml"
    p.write_text(
        '<testsuite name="S"><testcase name="a" classname="S" time="0.1"/>'
        '<testcase name="b" classname="S"><skipped/></testcase></testsuite>',
        encoding="utf-8",
    )
    r = parse_gtest(p)
    assert [c.status for c in r.cases] == [TestStatus.PASSED, TestStatus.SKIPPED]


def test_gtest_empty_suites(tmp_path):
    p = tmp_path / "g.xml"
    p.write_text("<testsuites/>", encoding="utf-8")
    assert parse_gtest(p).total == 0


def test_gtest_errors(tmp_path):
    with pytest.raises(ParseError):
        parse_gtest(tmp_path / "missing.xml")
    bad = tmp_path / "bad.xml"
    bad.write_text("<testsuites>", encoding="utf-8")
    with pytest.raises(ParseError):
        parse_gtest(bad)
    wrong = tmp_path / "wrong.xml"
    wrong.write_text("<results/>", encoding="utf-8")
    with pytest.raises(ParseError):
        parse_gtest(wrong)


# --- llvm-cov --------------------------------------------------------------

def test_llvmcov_sample():
    r = parse_llvmcov(SAMPLES / "llvm-cov.json")
    assert len(r.files) == 4
    client = next(f for f in r.files if f.path == "src/net/client.cc")
    assert (client.lines.count, client.lines.covered) == (150, 90)
    assert client.lines.percent == 60.0
    assert len(client.function_details) == 4
    reset = next(f for f in client.function_details if f.name == "Client::HandleReset")
    assert reset.execution_count == 0 and reset.line == 128
    poll = next(f for f in client.function_details if f.name == "Client::Poll")
    assert (poll.regions.count, poll.regions.covered) == (2, 1)


def test_llvmcov_errors(tmp_path):
    with pytest.raises(ParseError):
        parse_llvmcov(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ParseError):
        parse_llvmcov(bad)
    wrong = tmp_path / "wrong.json"
    wrong.write_text("{}", encoding="utf-8")
    with pytest.raises(ParseError):
        parse_llvmcov(wrong)


# --- cppcheck --------------------------------------------------------------

def test_cppcheck_sample():
    r = parse_cppcheck(SAMPLES / "cppcheck.xml")
    assert r.version == "2.13.0"
    assert len(r.violations) == 10
    by_sev = {}
    for v in r.violations:
        by_sev[v.severity] = by_sev.get(v.severity, 0) + 1
    assert by_sev == {"error": 3, "style": 4, "performance": 1, "information": 1, "warning": 1}
    npd = next(v for v in r.violations if v.rule_id == "nullPointer")
    assert (npd.file, npd.line, npd.column) == ("src/core/parser.cc", 87, 12)
    # XML entities are decoded
    assert any("<sys/epoll.h>" in v.message for v in r.violations)


def test_cppcheck_error_without_location(tmp_path):
    p = tmp_path / "c.xml"
    p.write_text(
        '<results version="2"><errors><error id="x" severity="information" msg="m"/></errors></results>',
        encoding="utf-8",
    )
    v = parse_cppcheck(p).violations[0]
    assert v.file == "" and v.line == 0


def test_cppcheck_errors(tmp_path):
    with pytest.raises(ParseError):
        parse_cppcheck(tmp_path / "missing.xml")
    wrong = tmp_path / "wrong.xml"
    wrong.write_text("<testsuites/>", encoding="utf-8")
    with pytest.raises(ParseError):
        parse_cppcheck(wrong)


# --- lizard ----------------------------------------------------------------

def test_lizard_sample():
    r = parse_lizard(SAMPLES / "lizard.csv")
    assert len(r.functions) == 11
    h = next(f for f in r.functions if f.name == "Parser::ParseHeader")
    assert (h.ccn, h.length, h.nloc, h.params) == (24, 121, 96, 3)
    assert (h.start_line, h.end_line) == (70, 190)
    assert h.file == "src/core/parser.cc"
    assert sum(1 for f in r.functions if f.ccn > 10) == 3
    assert sum(1 for f in r.functions if f.length > 80) == 2


def test_lizard_header_and_backslash_paths(tmp_path):
    p = tmp_path / "l.csv"
    p.write_text(
        "NLOC,CCN,token,PARAM,length,location,file,function,long_name,start,end\n"
        '5,1,20,0,6,"f@1-6@a\\b.cc","a\\b.cc","f","f( )",1,6\n',
        encoding="utf-8",
    )
    fn = parse_lizard(p).functions[0]
    assert fn.file == "a/b.cc" and fn.name == "f"


def test_lizard_errors(tmp_path):
    with pytest.raises(ParseError):
        parse_lizard(tmp_path / "missing.csv")
    short = tmp_path / "short.csv"
    short.write_text("1,2,3\n", encoding="utf-8")
    with pytest.raises(ParseError):
        parse_lizard(short)
    nonnum = tmp_path / "nonnum.csv"
    nonnum.write_text('1,x,3,4,5,"l","f.cc","n","n",1,2\n', encoding="utf-8")
    with pytest.raises(ParseError):
        parse_lizard(nonnum)


def test_llvmcov_mcdc_and_code_regions_only(tmp_path):
    import json

    doc = {"data": [{
        "files": [{"filename": "/w/a.c", "summary": {
            "lines": {"count": 2, "covered": 2}, "mcdc": {"count": 4, "covered": 3}}}],
        "functions": [{"name": "f", "count": 1, "filenames": ["/w/a.c"], "regions": [
            [1, 1, 9, 2, 5, 0, 0, 0],   # code, covered
            [2, 1, 2, 5, 0, 0, 0, 0],   # code, not covered
            [3, 1, 3, 1, 0, 0, 0, 2],   # skipped -> ignored
            [4, 1, 4, 9, 0, 0, 0, 4],   # branch  -> ignored
        ]}]}]}
    p = tmp_path / "c.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    f = parse_llvmcov(p).files[0]
    assert (f.mcdc.count, f.mcdc.covered) == (4, 3)
    fn = f.function_details[0]
    assert (fn.regions.count, fn.regions.covered) == (2, 1)


def test_llvmcov_without_mcdc_gives_empty_counter():
    f = parse_llvmcov(SAMPLES / "llvm-cov.json").files[0]
    assert f.mcdc.count == 0
