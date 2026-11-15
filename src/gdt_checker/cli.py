"""Command line: gdt-check SPEC.toml MEASUREMENTS.csv --report report.md --plot plot.png"""

from __future__ import annotations

import argparse
import sys

from .checker import SpecError, check_files
from .report import write_markdown, write_plot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gdt-check", description="Pass/fail GD&T check of measured points.")
    parser.add_argument("spec", help="part spec (TOML)")
    parser.add_argument("measurements", help="measured points (CSV: feature,x,y,z)")
    parser.add_argument("--report", help="write a Markdown report to this path")
    parser.add_argument("--plot", help="write a PNG plot to this path")
    args = parser.parse_args(argv)
    try:
        spec, results, frame, points = check_files(args.spec, args.measurements)
    except (SpecError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for r in results:
        print(f"{r.feature_id:<14} {r.fcf_type:<16} measured {r.measured:8.4f}  limit {r.limit:8.4f}  {'PASS' if r.passed else 'FAIL'}")
    if args.report:
        write_markdown(spec, results, args.report)
    if args.plot:
        write_plot(spec, results, frame, points, args.plot)
    failed = [r.feature_id for r in results if not r.passed]
    print(f"\n{len(results) - len(failed)} of {len(results)} features pass" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0
