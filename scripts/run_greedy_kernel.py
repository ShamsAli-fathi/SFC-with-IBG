#!/usr/bin/env python3
"""Operate only the persistent, two-node Greedy Kernel environment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Greedy.contracts import GreedyConfiguration
from Greedy.kernel_lifecycle import (
    GreedyLaunchConfiguration,
    GreedyLifecycleError,
    cleanup,
    preflight,
    resolve_root_seed,
)
from Greedy.kernel_reporting import run_greedy_evidenced_lifecycle
from Greedy.kernel_profile_reconciliation import GreedyProfileReconciliationError
from Greedy.kernel_rollout import GreedyKernelRolloutError


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _stage_count(value: str) -> int:
    parsed = _positive_integer(value)
    if parsed < 2:
        raise argparse.ArgumentTypeError("value must be at least 2")
    return parsed


def _nonnegative_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be a nonnegative integer")
    return parsed


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Operate only cluster greedy/context kind-greedy/namespace "
            "greedy-testbed; no other baseline is a mutation target."
        )
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    run_parser = subparsers.add_parser(
        "run", help="reconcile serving state and create one finite controller Job"
    )
    run_parser.add_argument(
        "--flow",
        dest="requested_flows",
        type=_positive_integer,
        required=True,
        help="explicit positive logical-flow count",
    )
    run_parser.add_argument(
        "--stage",
        dest="requested_stages",
        type=_stage_count,
        required=True,
        help="explicit contiguous configured-stage count (at least two)",
    )
    run_parser.add_argument(
        "--replica",
        dest="requested_replicas",
        type=_positive_integer,
        required=True,
        help="explicit positive replica count per stage",
    )
    run_parser.add_argument(
        "--max-iterations",
        type=_positive_integer,
        required=True,
        help="positive finite slot bound",
    )
    run_parser.add_argument(
        "--profile-seed",
        type=_nonnegative_integer,
        required=True,
        help="nonnegative deterministic processor-private profile seed",
    )
    run_parser.add_argument(
        "--rollout-batch-size",
        type=_positive_integer,
        default=1,
        help="maximum missing replica ordinals added per Ready-gated batch",
    )
    run_parser.add_argument(
        "--skip-build",
        action="store_true",
        help=(
            "reuse validated existing node-local Greedy images without "
            "wheelhouse validation, build, load, or forced serving restart"
        ),
    )
    run_parser.add_argument(
        "--csv",
        type=int,
        choices=(0, 1),
        default=0,
        help="export the validated v2 host trace to figures/Greedy/v2 when set to 1",
    )
    run_parser.add_argument(
        "--parity-replay",
        type=int,
        choices=(0, 1),
        default=0,
        help="run captured-input Pure/Kernel validation for every slot when set to 1",
    )
    subparsers.add_parser("preflight", help="read-only dedicated-cluster validation")
    subparsers.add_parser("cleanup", help="explicitly delete only an owned Greedy cluster")
    return parser.parse_args(arguments)


def launch_configuration_from_args(
    args: argparse.Namespace,
    *,
    root_seed: int | None = None,
) -> GreedyLaunchConfiguration:
    if args.action != "run":
        raise ValueError("launch configuration requires the run action")
    resolved_root_seed = resolve_root_seed() if root_seed is None else root_seed
    return GreedyLaunchConfiguration(
        configuration=GreedyConfiguration(
            args.requested_flows,
            args.requested_stages,
            args.requested_replicas,
        ),
        max_iterations=args.max_iterations,
        profile_seed=args.profile_seed,
        root_seed=resolved_root_seed,
        rollout_batch_size=args.rollout_batch_size,
        skip_build=args.skip_build,
        csv=args.csv,
        parity_replay=args.parity_replay,
    )


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        if args.action == "run":
            run_greedy_evidenced_lifecycle(launch_configuration_from_args(args))
        elif args.action == "preflight":
            preflight()
        else:
            cleanup()
    except (
        GreedyKernelRolloutError,
        GreedyLifecycleError,
        GreedyProfileReconciliationError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
        TypeError,
        ValueError,
    ) as error:
        print(f"Greedy cluster isolation failure: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
