import json
import xml.etree.ElementTree as ET
from pathlib import Path

from verreport.config import Config
from verreport.models import (
    CoverageCounter,
    GTestResult,
    TestCase,
    TestStatus,
    VerificationData,
)

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_coverage_counter_percent():
    assert CoverageCounter(count=4, covered=3).percent == 75.0
    assert CoverageCounter().percent == 100.0  # nothing to cover


def test_gtest_result_counts():
    r = GTestResult(
        cases=[
            TestCase("S", "a", TestStatus.PASSED),
            TestCase("S", "b", TestStatus.FAILED),
        ]
    )
    assert r.total == 2
    assert r.count(TestStatus.FAILED) == 1


def test_verification_data_defaults_allow_missing_tools():
    d = VerificationData()
    assert d.gtest is None and d.coverage is None
    assert d.cppcheck is None and d.lizard is None


def test_default_thresholds():
    t = Config().thresholds
    assert (t.lizard_ccn, t.lizard_length) == (10, 80)


def test_sample_files_are_well_formed():
    assert ET.parse(SAMPLES / "gtest.xml").getroot().tag == "testsuites"
    assert ET.parse(SAMPLES / "cppcheck.xml").getroot().tag == "results"
    cov = json.loads((SAMPLES / "llvm-cov.json").read_text(encoding="utf-8"))
    assert cov["type"] == "llvm.coverage.json.export"
    assert len((SAMPLES / "lizard.csv").read_text(encoding="utf-8").splitlines()) == 11
