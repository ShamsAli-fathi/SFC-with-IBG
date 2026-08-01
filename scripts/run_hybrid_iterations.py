#!/usr/bin/env python3
"""Run successive pure-Python IBG-Hybrid slots with compact live output."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from IBG_Hybrid import (  # noqa: E402
    format_hybrid_slot_metrics,
    make_default_hybrid_slot_input,
    run_hybrid_slot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the default 20x3x10 pure IBG-Hybrid simulation until "
            "equilibrium or a slot limit."
        )
    )
    parser.add_argument(
        "--max-slots",
        type=int,
        default=100,
        help="maximum completed slots to run (default: 100)",
    )
    parser.add_argument(
        "--root-seed",
        type=int,
        default=2050,
        help="nonnegative root seed (default: 2050)",
    )
    parser.add_argument(
        "--slot-id",
        type=int,
        default=1,
        help="positive initial slot ID (default: 1)",
    )
    args = parser.parse_args()
    if args.max_slots < 1:
        parser.error("--max-slots must be positive")
    if args.root_seed < 0:
        parser.error("--root-seed must not be negative")
    if args.slot_id < 1:
        parser.error("--slot-id must be positive")
    return args


def main() -> int:
    args = parse_args()
    slot_input = make_default_hybrid_slot_input(
        root_seed=args.root_seed,
        slot_id=args.slot_id,
    )

    for iteration in range(1, args.max_slots + 1):
        result = run_hybrid_slot(slot_input)
        print(
            f"iteration={iteration} {format_hybrid_slot_metrics(result)}",
            flush=True,
        )
        if result.metrics.equilibrium:
            print(f"equilibrium reached after {iteration} iteration(s)")
            return 0
        slot_input = slot_input.with_beliefs(result.beliefs_after_mapping)

    print(f"stopped after {args.max_slots} iteration(s) without equilibrium")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
