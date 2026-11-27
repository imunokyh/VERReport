"""Render a ReportSummary into a static HTML report directory."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from importlib import resources
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from ..analysis.summary import ReportSummary

TOOLS = {
    "gtest": "Google Test",
    "coverage": "Coverage (LLVM)",
    "cppcheck": "CPPCheck",
    "lizard": "Lizard",
}


def _pct(counter) -> float:
    return round(counter.percent, 1)


def chart_data(s: ReportSummary) -> dict:
    """JSON-serializable data consumed by static/dashboard.js."""
    d: dict = {}
    if s.gtest:
        d["gtest"] = {"passed": s.gtest.passed, "failed": s.gtest.failed, "skipped": s.gtest.skipped}
    if s.coverage:
        c = s.coverage
        d["coverage"] = {
            "labels": ["Lines", "Functions", "Regions", "Branches"],
            "values": [_pct(c.lines), _pct(c.functions), _pct(c.regions), _pct(c.branches)],
            "target": c.target,
        }
        if c.mcdc.count:  # only when MC/DC was measured
            d["coverage"]["labels"].append("MC/DC")
            d["coverage"]["values"].append(_pct(c.mcdc))
    if s.cppcheck:
        d["cppcheck"] = {
            "labels": list(s.cppcheck.by_severity),
            "values": list(s.cppcheck.by_severity.values()),
        }
    if s.lizard:
        z = s.lizard
        d["lizard"] = {
            "labels": [f"CCN > {z.ccn_limit}", f"Length > {z.length_limit}"],
            "values": [z.ccn_violations, z.length_violations],
            "total": z.total_functions,
        }
    return d


_PRE = re.compile(r"(<pre>.*?</pre>)", re.S)
_INDENT = re.compile(r"\n[ \t]+")


def minify(html: str) -> str:
    """Drop line-leading indentation (about 20% smaller on big reports).

    Whitespace inside <pre> is preserved; other leading whitespace is
    insignificant in HTML.
    """
    return "".join(
        part if part.startswith("<pre>") else _INDENT.sub("\n", part)
        for part in _PRE.split(html)
    )


def make_env() -> Environment:
    return Environment(
        loader=PackageLoader("verreport.render", "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def build_report(summary: ReportSummary, out_dir: str | Path) -> Path:
    """Write the report into out_dir and return the path of index.html."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    static_src = resources.files("verreport") / "static"
    static_dst = out / "static"
    if static_dst.exists():
        shutil.rmtree(static_dst)
    with resources.as_file(static_src) as src:
        shutil.copytree(src, static_dst)

    env = make_env()
    build_time = summary.build.build_time
    ctx = {
        "s": summary,
        "tools": TOOLS,
        "chart_data": chart_data(summary),
        "build_time": build_time.strftime("%Y-%m-%d %H:%M:%S") if build_time else "-",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    index = out / "index.html"
    index.write_text(minify(env.get_template("dashboard.html").render(page="index", **ctx)), encoding="utf-8")
    for key in summary.tool_results:  # detail pages only for tools with results
        html = env.get_template(f"{key}.html").render(page=key, **ctx)
        (out / f"{key}.html").write_text(minify(html), encoding="utf-8")
    return index
