"""Google Test XML (--gtest_output=xml:...) parser."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..models import GTestResult, TestCase, TestStatus
from ._util import ParseError, load_xml, normalize_path, to_float, to_int


def parse_gtest(path: str | Path) -> GTestResult:
    root = load_xml(path)
    if root.tag == "testsuites":
        suites = root.findall("testsuite")
    elif root.tag == "testsuite":
        suites = [root]
    else:
        raise ParseError(f"{path}: unexpected root element <{root.tag}>")

    result = GTestResult()
    for suite in suites:
        suite_name = suite.get("name", "")
        for tc in suite.findall("testcase"):
            result.cases.append(_parse_case(tc, suite_name))
    return result


def _parse_case(tc: ET.Element, suite_name: str) -> TestCase:
    messages: list[str] = []
    for tag in ("failure", "error"):
        for f in tc.findall(tag):
            text = (f.text or "").strip() or f.get("message", "")
            messages.append(text)

    if messages:
        status = TestStatus.FAILED
    elif (
        tc.find("skipped") is not None
        or tc.get("status") == "notrun"
        or tc.get("result") in ("skipped", "suppressed")
    ):
        status = TestStatus.SKIPPED
    else:
        status = TestStatus.PASSED

    return TestCase(
        suite=tc.get("classname") or suite_name,
        name=tc.get("name", ""),
        status=status,
        time_sec=to_float(tc.get("time")),
        file=normalize_path(tc.get("file", "")),
        line=to_int(tc.get("line")),
        message="\n".join(messages),
    )
