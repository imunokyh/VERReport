from pathlib import Path

import pytest

from verreport.cli import main
from verreport.config import Config, ConfigError, load_config

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
ALL = [
    "--gtest", str(SAMPLES / "gtest.xml"),
    "--llvm-cov", str(SAMPLES / "llvm-cov.json"),
    "--cppcheck", str(SAMPLES / "cppcheck.xml"),
    "--lizard", str(SAMPLES / "lizard.csv"),
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for n in ("BUILD_NUMBER", "GITHUB_RUN_NUMBER", "GIT_COMMIT", "GITHUB_SHA", "GIT_BRANCH", "GITHUB_REF_NAME"):
        monkeypatch.delenv(n, raising=False)


def run(tmp_path, *args):
    return main(["generate", "-o", str(tmp_path / "out"), *args])


def pages(tmp_path):
    return {p.name for p in (tmp_path / "out").glob("*.html")}


# --- generate --------------------------------------------------------------

def test_generate_all_tools(tmp_path, capsys):
    rc = run(tmp_path, *ALL, "--build-number", "128", "--build-time", "2026-11-27T09:12:03",
             "--commit", "abcdef1234567", "--branch", "main", "--project", "Demo")
    assert rc == 0  # verification FAIL does not fail the command by default
    assert pages(tmp_path) == {"index.html", "gtest.html", "coverage.html", "cppcheck.html", "lizard.html"}
    html = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert "Demo" in html and "128" in html and "2026-11-27 09:12:03" in html and "abcdef1234" in html
    out = capsys.readouterr().out
    assert "[FAIL] Google Test: 5/8 passed, 2 failed, 1 skipped" in out
    assert "line coverage 77.3%" in out and "Overall: FAIL" in out


def test_fail_on_violation(tmp_path):
    assert run(tmp_path, *ALL, "--fail-on-violation") == 1


def test_passing_build_returns_zero_with_fail_on_violation(tmp_path, capsys):
    ok = tmp_path / "ok.xml"
    ok.write_text('<testsuites><testsuite name="S"><testcase name="a" classname="S"/></testsuite></testsuites>',
                  encoding="utf-8")
    assert run(tmp_path, "--gtest", str(ok), "--fail-on-violation") == 0
    assert "Overall: PASS" in capsys.readouterr().out


def test_partial_inputs(tmp_path):
    assert run(tmp_path, "--gtest", str(SAMPLES / "gtest.xml")) == 0
    assert pages(tmp_path) == {"index.html", "gtest.html"}


def test_threshold_overrides(tmp_path, capsys):
    run(tmp_path, *ALL, "--coverage-target", "70", "--ccn-limit", "20", "--length-limit", "100")
    out = capsys.readouterr().out
    assert "[PASS] Coverage" in out
    assert "1 violating functions (CCN>20: 1, length>100: 1)" in out


def test_build_info_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILD_NUMBER", "77")
    monkeypatch.setenv("GIT_COMMIT", "feedface00112233")
    run(tmp_path, "--gtest", str(SAMPLES / "gtest.xml"))
    html = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert "77" in html and "feedface00" in html


# --- errors ----------------------------------------------------------------

def test_no_inputs_is_error(tmp_path, capsys):
    assert run(tmp_path) == 2
    assert "no tool results" in capsys.readouterr().err
    assert pages(tmp_path) == set()


def test_all_inputs_unreadable_generates_nothing(tmp_path, capsys):
    assert run(tmp_path, "--gtest", str(tmp_path / "nope.xml")) == 2
    err = capsys.readouterr().err
    assert "Google Test" in err and "no report generated" in err
    assert pages(tmp_path) == set()


def test_one_broken_input_still_generates_rest_but_returns_2(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    rc = run(tmp_path, "--gtest", str(SAMPLES / "gtest.xml"), "--llvm-cov", str(bad))
    assert rc == 2
    assert pages(tmp_path) == {"index.html", "gtest.html"}
    assert "skipping Coverage" in capsys.readouterr().err


def test_invalid_build_time_is_usage_error(tmp_path):
    with pytest.raises(SystemExit) as e:
        run(tmp_path, *ALL, "--build-time", "yesterday")
    assert e.value.code == 2


def test_no_subcommand_is_usage_error():
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2


# --- config file -----------------------------------------------------------

def test_config_file_inputs_relative_to_config(tmp_path, capsys):
    rc = run(tmp_path, "-c", str(SAMPLES / "verreport.yml"))
    assert rc == 0
    assert pages(tmp_path) == {"index.html", "gtest.html", "coverage.html", "cppcheck.html", "lizard.html"}
    assert "Demo" in (tmp_path / "out" / "index.html").read_text(encoding="utf-8")


def test_cli_overrides_config(tmp_path, capsys):
    only = tmp_path / "c.xml"
    only.write_text('<testsuites><testsuite name="S"><testcase name="a" classname="S"/></testsuite></testsuites>',
                    encoding="utf-8")
    run(tmp_path, "-c", str(SAMPLES / "verreport.yml"), "--gtest", str(only), "--project", "Override")
    out = capsys.readouterr().out
    assert "[PASS] Google Test: 1/1 passed" in out  # CLI file replaced the config's gtest
    assert "Override" in (tmp_path / "out" / "index.html").read_text(encoding="utf-8")


def test_config_error_returns_2(tmp_path, capsys):
    cfg = tmp_path / "bad.yml"
    cfg.write_text("thresholds:\n  lizard_ccn: lots\n", encoding="utf-8")
    assert run(tmp_path, "-c", str(cfg), *ALL) == 2
    assert "lizard_ccn" in capsys.readouterr().err
    assert run(tmp_path, "-c", str(tmp_path / "missing.yml"), *ALL) == 2


# --- load_config -----------------------------------------------------------

def test_load_config_full(tmp_path):
    p = tmp_path / "c.yml"
    p.write_text(
        "project: P\nmodule_depth: 3\nsource_root: /w\n"
        "thresholds: {lizard_ccn: 15, coverage_line: 85}\n"
        "module_map: {src/core: Core}\ninputs: {gtest: r/g.xml}\n",
        encoding="utf-8",
    )
    c = load_config(p)
    assert (c.project, c.module_depth, c.source_root) == ("P", 3, "/w")
    assert (c.thresholds.lizard_ccn, c.thresholds.lizard_length, c.thresholds.coverage_line) == (15, 80, 85.0)
    assert c.module_map == {"src/core": "Core"}
    assert [Path(p) for p in c.inputs["gtest"]] == [(tmp_path / "r" / "g.xml").resolve()]


def test_load_config_empty_file_gives_defaults(tmp_path):
    p = tmp_path / "e.yml"
    p.write_text("", encoding="utf-8")
    assert load_config(p) == Config()


@pytest.mark.parametrize("text", [
    "bogus: 1\n",                       # unknown top-level key
    "thresholds: {nope: 1}\n",          # unknown threshold
    "inputs: {sonar: x}\n",             # unknown input
    "module_depth: 0\n",                # out of range
    "thresholds: {lizard_ccn: true}\n", # bool is not a number
    "- a\n- b\n",                       # not a mapping
    "a: [unclosed\n",                   # invalid YAML
])
def test_load_config_rejects(tmp_path, text):
    p = tmp_path / "bad.yml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)


# --- multiple gtest files / globs / MC/DC ---------------------------------

def _gtest_file(path, suite, failed=False):
    body = '<failure message="x"/>' if failed else ""
    path.write_text(
        f'<testsuites><testsuite name="{suite}"><testcase name="t" classname="{suite}">{body}</testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )


def test_multiple_gtest_files_are_merged(tmp_path, capsys):
    _gtest_file(tmp_path / "a.xml", "A")
    _gtest_file(tmp_path / "b.xml", "B", failed=True)
    run(tmp_path, "--gtest", str(tmp_path / "a.xml"), str(tmp_path / "b.xml"))
    assert "1/2 passed, 1 failed" in capsys.readouterr().out


def test_gtest_glob_pattern(tmp_path, capsys):
    for n in "abc":
        _gtest_file(tmp_path / f"r_{n}.xml", n.upper())
    run(tmp_path, "--gtest", str(tmp_path / "r_*.xml"))
    assert "3/3 passed" in capsys.readouterr().out


def test_gtest_glob_without_match_is_input_error(tmp_path, capsys):
    assert run(tmp_path, "--gtest", str(tmp_path / "none_*.xml")) == 2
    assert "no files match" in capsys.readouterr().err


def test_config_gtest_list_and_glob(tmp_path, capsys):
    _gtest_file(tmp_path / "x1.xml", "X1")
    _gtest_file(tmp_path / "x2.xml", "X2")
    cfg = tmp_path / "c.yml"
    cfg.write_text("inputs:\n  gtest: [x1.xml, 'x2*.xml']\n", encoding="utf-8")
    run(tmp_path, "-c", str(cfg))
    assert "2/2 passed" in capsys.readouterr().out


def test_config_rejects_multiple_files_for_non_gtest(tmp_path):
    cfg = tmp_path / "c.yml"
    cfg.write_text("inputs:\n  lizard: [a.csv, b.csv]\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(cfg)
