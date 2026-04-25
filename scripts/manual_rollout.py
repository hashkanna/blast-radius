from __future__ import annotations

import argparse
import json

from blast_radius.rollouts import run_competent_rollout


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic BlastRadius rollout.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()

    print(json.dumps(run_competent_rollout(args.seed), indent=args.indent, sort_keys=True))


if __name__ == "__main__":
    main()
