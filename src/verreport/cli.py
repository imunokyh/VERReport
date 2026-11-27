"""Command line interface: ``verreport generate``.

Exit codes:
  0  report generated (and, with --fail-on-violation, verification passed)
  1  report generated but verification failed (only with --fail-on-violation)
  2  usage, configuration or input error (a report is still written when at
     least one tool result could be parsed)
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .analysis import summarize
from .config import INPUT_KEYS, Config, ConfigError, load_config
from .models import BuildInfo, GTestResult, VerificationData
from .parsers import ParseError, parse_cppcheck, parse_gtest, parse_lizard, parse_llvmcov
from .render import build_report

# input key -> (VerificationData field, parser, display name)
TOOLS = {
    "gtest": ("gtest", parse_gtest, "Google Test"),
    "llvm_cov": ("coverage", parse_llvmcov, "Coverage"),
    "cppcheck": ("cppcheck", parse_cppcheck, "CPPCheck"),
    "lizard": ("lizard", parse_lizard, "Lizard"),
}
SUMMARY_FIELDS = {"gtest": "gtest", "llvm_cov": "coverage", "cppcheck": "cppcheck", "lizard": "lizard"}


def _env(*names: str) -> str:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return ""


def _expand(patterns: list[str]) -> list[str]:
    """Expand glob patterns (needed on shells that do not, e.g. cmd.exe); keep order."""
    out: list[str] = []
    for p in patterns:
        if any(ch in p for ch in "*?["):
            matches = sorted(glob.glob(p))
            if not matches:
                raise ParseError(f"no files match {p}")
            out.extend(matches)
        else:
            out.append(p)
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="verreport", description="Verification result dashboard generator.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="generate the HTML report")
    inp = g.add_argument_group("tool results (any subset)")
    inp.add_argument("--gtest", metavar="XML", nargs="+",
                     help="Google Test XML(s) (--gtest_output=xml:...); several files or globs are merged")
    inp.add_argument("--llvm-cov", metavar="JSON", help="llvm-cov export JSON (llvm-cov export -format=text)")
    inp.add_argument("--cppcheck", metavar="XML", help="CPPCheck XML (--xml --xml-version=2)")
    inp.add_argument("--lizard", metavar="CSV", help="Lizard CSV (lizard --csv)")

    g.add_argument("-o", "--out", default="report", metavar="DIR", help="output directory (default: report)")
    g.add_argument("-c", "--config", metavar="YAML", help="configuration file")

    b = g.add_argument_group("build information")
    b.add_argument("--project", help="project name")
    b.add_argument("--build-number", help="build number (env: BUILD_NUMBER, GITHUB_RUN_NUMBER)")
    b.add_argument("--build-time", metavar="ISO8601", help="build date/time, e.g. 2026-11-27T09:12:03 (default: now)")
    b.add_argument("--commit", help="commit hash (env: GIT_COMMIT, GITHUB_SHA)")
    b.add_argument("--branch", help="branch name (env: GIT_BRANCH, GITHUB_REF_NAME)")

    t = g.add_argument_group("threshold overrides")
    t.add_argument("--ccn-limit", type=int, metavar="N", help="Lizard: CCN above N is a violation (default 10)")
    t.add_argument("--length-limit", type=int, metavar="N", help="Lizard: function lines above N is a violation (default 80)")
    t.add_argument("--coverage-target", type=float, metavar="PCT", help="line coverage target percent (default 80)")

    g.add_argument("--fail-on-violation", action="store_true",
                   help="exit with code 1 when the overall verdict is FAIL")
    g.set_defaults(func=cmd_generate)
    return p


def _parse_time(value: str | None, parser: argparse.ArgumentParser) -> datetime:
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        parser.error(f"invalid --build-time {value!r} (expected ISO 8601, e.g. 2026-11-27T09:12:03)")


def cmd_generate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    # --- configuration: CLI > config file > environment > defaults
    try:
        config = load_config(args.config) if args.config else Config()
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.ccn_limit is not None:
        config.thresholds.lizard_ccn = args.ccn_limit
    if args.length_limit is not None:
        config.thresholds.lizard_length = args.length_limit
    if args.coverage_target is not None:
        config.thresholds.coverage_line = args.coverage_target

    cli_inputs = {
        "gtest": args.gtest,  # list or None
        "llvm_cov": [args.llvm_cov] if args.llvm_cov else None,
        "cppcheck": [args.cppcheck] if args.cppcheck else None,
        "lizard": [args.lizard] if args.lizard else None,
    }
    inputs = {**config.inputs, **{k: v for k, v in cli_inputs.items() if v}}

    build = BuildInfo(
        project=args.project or config.project,
        build_number=args.build_number or _env("BUILD_NUMBER", "GITHUB_RUN_NUMBER"),
        build_time=_parse_time(args.build_time, parser),
        commit=args.commit or _env("GIT_COMMIT", "GITHUB_SHA"),
        branch=args.branch or _env("GIT_BRANCH", "GITHUB_REF_NAME"),
    )

    # --- parse inputs; a broken file is reported but does not stop the others
    data = VerificationData(build=build)
    errors: list[str] = []
    for key in INPUT_KEYS:
        patterns = inputs.get(key)
        if not patterns:
            continue
        attr, parse, label = TOOLS[key]
        try:
            paths = _expand(patterns)
            if key == "gtest":
                merged = GTestResult()
                for p in paths:
                    merged.cases.extend(parse(p).cases)
                setattr(data, attr, merged)
            else:
                setattr(data, attr, parse(paths[0]))
        except ParseError as e:
            errors.append(f"{label}: {e}")
            print(f"warning: skipping {label}: {e}", file=sys.stderr)

    if not any(getattr(data, TOOLS[k][0]) is not None for k in INPUT_KEYS):
        if not inputs:
            print("error: no tool results given (use --gtest/--llvm-cov/--cppcheck/--lizard or inputs: in the config)",
                  file=sys.stderr)
        else:
            print("error: none of the given tool results could be read; no report generated", file=sys.stderr)
        return 2

    # --- generate
    summary = summarize(data, config)
    index = build_report(summary, args.out)

    print(f"Report: {Path(index).resolve()}")
    for key in INPUT_KEYS:
        s = getattr(summary, SUMMARY_FIELDS[key])
        if s is None:
            continue
        print(f"  [{'PASS' if s.passed_ok else 'FAIL'}] {TOOLS[key][2]}: {_describe(key, s)}")
    print(f"Overall: {'PASS' if summary.passed else 'FAIL'}")

    if errors:
        return 2
    if args.fail_on_violation and not summary.passed:
        return 1
    return 0


def _describe(key: str, s) -> str:
    if key == "gtest":
        return f"{s.passed}/{s.total} passed, {s.failed} failed, {s.skipped} skipped"
    if key == "llvm_cov":
        return f"line coverage {s.lines.percent:.1f}% (target {s.target:g}%)"
    if key == "cppcheck":
        return f"{s.total} violations ({s.by_severity.get('error', 0)} errors)"
    return f"{s.violations} violating functions (CCN>{s.ccn_limit}: {s.ccn_violations}, length>{s.length_limit}: {s.length_violations})"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args, parser)


if __name__ == "__main__":
    sys.exit(main())
