"""Guarded Phase 1 command-line configuration boundary."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .backend import detect_scipy_highs
from .contracts import MILPConfiguration
from .phase0_contract import (
    DEFAULT_MILP_DIMENSIONS,
    MILP_ACTION_CARDINALITY,
    MILPContractError,
)


def _positive_integer(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _stage_count(text: str) -> int:
    value = _positive_integer(text)
    if value < MILP_ACTION_CARDINALITY:
        raise argparse.ArgumentTypeError(
            f"must be at least L={MILP_ACTION_CARDINALITY}"
        )
    return value


def _positive_finite_cutoff(text: str) -> float:
    try:
        value = float(text)
        return MILPConfiguration.uniform(cutoff_seconds=value).cutoff_seconds
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("must be a finite positive number") from exc
    except MILPContractError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m MILP",
        description="Configure the coupled/budgeted MILP baseline (Phase 1).",
    )
    parser.add_argument(
        "--flow",
        type=_positive_integer,
        default=DEFAULT_MILP_DIMENSIONS.flow_count,
        help="number of flows (default: 15)",
    )
    parser.add_argument(
        "--stage",
        type=_stage_count,
        default=DEFAULT_MILP_DIMENSIONS.stage_count,
        help="number of stages, at least 2 (default: 3)",
    )
    parser.add_argument(
        "--replica",
        type=_positive_integer,
        default=DEFAULT_MILP_DIMENSIONS.replicas_per_stage[0],
        help="uniform replicas per stage (default: 10)",
    )
    parser.add_argument(
        "--cutoff",
        type=_positive_finite_cutoff,
        required=True,
        metavar="SECONDS",
        help="finite positive solver time limit in seconds",
    )
    return parser


def parse_configuration(argv: Sequence[str] | None = None) -> MILPConfiguration:
    arguments = build_parser().parse_args(argv)
    return MILPConfiguration.uniform(
        flow_count=arguments.flow,
        stage_count=arguments.stage,
        replicas_per_stage=arguments.replica,
        cutoff_seconds=arguments.cutoff,
    )


def main(argv: Sequence[str] | None = None) -> int:
    configuration = parse_configuration(argv)
    backend = detect_scipy_highs()
    dimensions = configuration.dimensions
    print(
        "MILP Phase 1 configuration accepted: "
        f"flows={dimensions.flow_count} stages={dimensions.stage_count} "
        f"replicas-per-stage={dimensions.replicas_per_stage[0]} "
        f"L={configuration.action_cardinality} "
        f"cutoff={configuration.cutoff_seconds:g}s; "
        f"backend={backend.detail}; solver API ready; "
        "Phase 3 slot API ready for a fully supplied MILPSlotInput; "
        "CLI does not fabricate planner or simulation profiles"
    )
    return 0
