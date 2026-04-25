from __future__ import annotations

import argparse
import json
import os

from blast_radius.openai_agent import run_openai_agent, write_trace


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an OpenAI Responses API agent against a BlastRadius ORS server."
    )
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--env-name", default="blastradiusenv")
    parser.add_argument("--split", default="train")
    parser.add_argument("--task-index", type=int, default=0)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL"))
    parser.add_argument("--max-turns", type=int, default=80)
    parser.add_argument("--output", help="Optional path for the full JSON trace.")
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()

    if not args.model:
        parser.error("Pass --model or set OPENAI_MODEL.")

    trace = run_openai_agent(
        base_url=args.base_url,
        env_name=args.env_name,
        split=args.split,
        task_index=args.task_index,
        model=args.model,
        max_turns=args.max_turns,
    )
    if args.output:
        write_trace(trace, args.output)
        print(json.dumps(trace["summary"], indent=args.indent, sort_keys=True))
    else:
        print(json.dumps(trace, indent=args.indent, sort_keys=True))


if __name__ == "__main__":
    main()
