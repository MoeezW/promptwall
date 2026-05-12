"""promptwall command line interface.

Currently exposes:

- ``promptwall bench`` — run the benchmark harness against the local
  detector pipeline. Writes results to ``benchmarks/results.md`` (or
  ``--output``) with 95% bootstrap confidence intervals.
"""

import argparse
import asyncio
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Dispatch the requested CLI subcommand."""
    parser = argparse.ArgumentParser(prog="promptwall")
    sub = parser.add_subparsers(dest="cmd", required=True)

    bench = sub.add_parser("bench", help="Run the benchmark harness")
    bench.add_argument("--n", type=int, default=1000, help="Examples per dataset")
    bench.add_argument(
        "--with-ml",
        action="store_true",
        help="Include the ONNX DeBERTa-v3 injection detector",
    )
    bench.add_argument("--output", type=Path, default=None, help="Write results.md to this path")

    args = parser.parse_args(argv)

    if args.cmd == "bench":
        # Imported here so the CLI's --help is fast and doesn't trigger heavy loads.
        from benchmarks.runner import run as run_bench

        asyncio.run(run_bench(n=args.n, with_ml=args.with_ml, output=args.output))
        return 0

    print(f"unknown command: {args.cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
