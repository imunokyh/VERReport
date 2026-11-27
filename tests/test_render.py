import json
import re
from datetime import datetime
from pathlib import Path

from test_analysis import sample_data
from verreport.analysis import summarize
from verreport.models import BuildInfo, VerificationData
from verreport.render import build_report
from verreport.render.builder import chart_data


def _build(tmp_path, data=None):
    data = data or sample_data()
    data.build = BuildInfo(
        project="Demo", build_number="#128", build_time=datetime(2026, 11, 27, 9, 12, 3),
        commit="a348ddc1234567", branch="main",
    )
    return build_report(summarize(data), tmp_path / "out")


def test_dashboard_generated(tmp_path):
    index = _build(tmp_path)
    html = index.read_text(encoding="utf-8")
    out = index.parent
    assert (out / "static" / "chart.umd.min.js").exists()
    assert (out / "static" / "report.css").exists()
    assert (out / "static" / "dashboard.js").exists()

    # build info
    assert "#128" in html and "2026-11-27 09:12:03" in html and "a348ddc123" in html
    assert 'class="verdict fail"' in html
    # all four cards with detail buttons
    for page in ("gtest", "coverage", "cppcheck", "lizard"):
        assert f'href="{page}.html"' in html
        assert f'id="chart-{page}"' in html
    assert html.count("상세 결과 보기") == 4
    # tables render data
    assert "ParserTest" in html and "src/net" in html and "Parser::ParseHeader" in html


def test_embedded_chart_data_is_valid_json(tmp_path):
    html = _build(tmp_path).read_text(encoding="utf-8")
    m = re.search(r'<script id="report-data" type="application/json">(.*?)</script>', html, re.S)
    d = json.loads(m.group(1))
    assert d["gtest"] == {"passed": 5, "failed": 2, "skipped": 1}
    assert d["coverage"]["values"][0] == 77.3
    assert d["cppcheck"]["labels"][0] == "error"
    assert d["lizard"]["values"] == [3, 2]


def test_missing_tools_render_no_data_cards(tmp_path):
    data = VerificationData(gtest=sample_data().gtest)
    html = _build(tmp_path, data).read_text(encoding="utf-8")
    assert html.count("NO DATA") == 3
    assert html.count("상세 결과 보기") == 1
    assert 'id="chart-coverage"' not in html


def test_html_is_escaped(tmp_path):
    data = sample_data()
    data.gtest.cases[0].suite = "<script>alert(1)</script>"
    html = _build(tmp_path, data).read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_chart_data_empty_for_no_results():
    assert chart_data(summarize(VerificationData())) == {}


# --- detail pages (M5) -----------------------------------------------------

def _pages(tmp_path, data=None):
    out = _build(tmp_path, data).parent
    return {p: (out / f"{p}.html").read_text(encoding="utf-8")
            for p in ("gtest", "coverage", "cppcheck", "lizard") if (out / f"{p}.html").exists()}


def test_detail_pages_generated_with_module_file_function(tmp_path):
    pages = _pages(tmp_path)
    assert set(pages) == {"gtest", "coverage", "cppcheck", "lizard"}

    g = pages["gtest"]
    assert "tests/core" in g and "tests/core/parser_test.cc" in g  # module, file
    assert "RejectsMalformedHeader" in g and "ERR_BAD_HEADER" in g  # test case + failure message
    assert 'data-flag="failed"' in g and 'data-flag="skipped"' in g

    c = pages["coverage"]
    assert "src/net" in c and "src/net/client.cc" in c and "Client::HandleReset" in c
    assert 'data-flag="uncovered partial"' in c  # HandleReset never executed
    assert 'data-flag="partial"' in c            # Poll has one uncovered region

    cc = pages["cppcheck"]
    assert "nullPointer" in cc and "src/core/parser.cc" in cc
    assert '<option value="error">error (3)</option>' in cc
    assert "&lt;sys/epoll.h&gt;" in cc  # message escaped

    lz = pages["lizard"]
    assert "Parser::ParseHeader" in lz
    assert 'data-flag="violation ccn length"' in lz     # ParseHeader: both
    assert 'data-flag="violation ccn"' in lz            # HandleReset: CCN only
    assert 'data-flag=""' in lz                         # compliant functions


def test_detail_pages_have_nav_and_scripts(tmp_path):
    for html in _pages(tmp_path).values():
        assert 'href="index.html"' in html and 'static/detail.js' in html
        for p in ("gtest", "coverage", "cppcheck", "lizard"):
            assert f'href="{p}.html"' in html
        assert 'id="q"' in html and 'id="flag"' in html and 'id="tree"' in html


def test_detail_pages_only_for_tools_with_results(tmp_path):
    pages = _pages(tmp_path, VerificationData(gtest=sample_data().gtest))
    assert set(pages) == {"gtest"}
    assert 'href="coverage.html"' not in pages["gtest"]  # nav hides absent tools


def test_detail_page_escaping(tmp_path):
    data = sample_data()
    data.gtest.cases[2].message = "<img src=x onerror=alert(1)>"
    g = _pages(tmp_path, data)["gtest"]
    assert "<img src=x" not in g and "&lt;img src=x" in g


def test_minify_preserves_pre_and_drops_indentation():
    from verreport.render.builder import minify

    src = "<div>\n    <p>a</p>\n\t<pre>x\n    y\n  z</pre>\n   <p>b</p>\n</div>"
    assert minify(src) == "<div>\n<p>a</p>\n<pre>x\n    y\n  z</pre>\n<p>b</p>\n</div>"


def test_failure_message_whitespace_survives_in_output(tmp_path):
    g = _pages(tmp_path)["gtest"]
    assert "Which is: 2\n  ERR_BAD_HEADER" in g  # indentation inside <pre> intact


def test_dashboard_clean_state_when_no_violations(tmp_path):
    from verreport.models import CppcheckResult, FunctionMetric, LizardResult

    data = VerificationData(
        cppcheck=CppcheckResult(),
        lizard=LizardResult([FunctionMetric("f", "a/b.c", 1, 9, 8, 3, 0, 9)]),
    )
    html = _build(tmp_path, data).read_text(encoding="utf-8")
    assert "위반 사항이 없습니다" in html
    assert "1개 함수 모두 기준 이내" in html and "최대 CCN 3" in html and "최대 길이 9라인" in html
    assert 'id="chart-cppcheck"' not in html and 'id="chart-lizard"' not in html
    assert 'href="cppcheck.html"' in html and 'href="lizard.html"' in html  # detail still reachable
