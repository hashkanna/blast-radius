from __future__ import annotations

import argparse
import json

from blast_radius.rollouts import compare_policies


def _print_table(report: dict) -> None:
    rows = []
    for policy in ("naive_baseline", "competent"):
        summary = report["summary"][policy]
        rows.append(
            [
                policy,
                f"{summary['score_total']:.4f}",
                str(summary["tool_calls"]),
                str(summary["final_tick"]),
                ",".join(summary["resolved_incidents"]) or "-",
            ]
        )

    headers = ["policy", "score", "tools", "final_tick", "resolved"]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    print(f"\nscore_delta={report['summary']['score_delta']:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare a naive baseline against the competent BlastRadius path."
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="Print full JSON traces.")
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()

    report = compare_policies(args.seed)
    if args.json:
        print(json.dumps(report, indent=args.indent, sort_keys=True))
    else:
        _print_table(report)


if __name__ == "__main__":
    main()
