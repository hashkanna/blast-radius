from __future__ import annotations

import argparse

from blast_radius.ors_env import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the BlastRadius ORS server.")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    run_server(port=args.port)


if __name__ == "__main__":
    main()
