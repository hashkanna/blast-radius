from __future__ import annotations

import argparse
import json

from blast_radius.trace_analysis import analyze_trace_file


def _print_text(report: dict) -> None:
    if report.get("kind") == "comparison":
        for name, policy_report in report["policies"].items():
            print(f"{name}:")
            _print_single(policy_report, prefix="  ")
        score_delta = report.get("summary", {}).get("score_delta")
        if score_delta is not None:
            print(f"score_delta: {score_delta:.4f}")
        return
    _print_single(report)


def _print_single(report: dict, prefix: str = "") -> None:
    fields = [
        ("kind", report.get("kind")),
        ("score", _fmt_float(report.get("score_total"))),
        ("tool_calls", report.get("tool_calls")),
        ("final_tick", report.get("final_tick")),
        ("finished", report.get("finished")),
        ("missing", ",".join(report.get("missing_incidents", [])) or "-"),
        ("first_failure", report.get("first_failure") or "-"),
    ]
    for key, value in fields:
        if value is not None:
            print(f"{prefix}{key}: {value}")
    recommendations = report.get("recommendations", [])
    if recommendations:
        print(f"{prefix}recommendations:")
        for item in recommendations:
            print(f"{prefix}- {item}")


def _fmt_float(value):
    return f"{value:.4f}" if isinstance(value, float) else value


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a BlastRadius trace artifact.")
    parser.add_argument("path")
    parser.add_argument("--json", action="store_true", help="Print full JSON analysis.")
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()

    report = analyze_trace_file(args.path)
    if args.json:
        print(json.dumps(report, indent=args.indent, sort_keys=True))
    else:
        _print_text(report)


if __name__ == "__main__":
    main()
