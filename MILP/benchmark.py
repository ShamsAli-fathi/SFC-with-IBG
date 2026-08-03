"""Guarded command for one explicit Phase 4 synthetic scale case."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .cli import _positive_finite_cutoff, _positive_integer, _stage_count
from .phase0_contract import DEFAULT_MILP_DIMENSIONS, SolverResultStatus
from .scaling import format_scale_evidence, make_scale_case, run_scale_case
from .solver import solve_coupled_milp, solve_scipy_highs


def _nonnegative_integer(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m MILP.benchmark",
        description="Run one deterministic coupled-MILP Phase 4 scale case.",
    )
    parser.add_argument(
        "--flow",
        type=_positive_integer,
        default=DEFAULT_MILP_DIMENSIONS.flow_count,
    )
    parser.add_argument(
        "--stage",
        type=_stage_count,
        default=DEFAULT_MILP_DIMENSIONS.stage_count,
    )
    parser.add_argument(
        "--replica",
        type=_positive_integer,
        default=DEFAULT_MILP_DIMENSIONS.replicas_per_stage[0],
    )
    parser.add_argument(
        "--cutoff",
        type=_positive_finite_cutoff,
        required=True,
        metavar="SECONDS",
    )
    parser.add_argument("--profile-seed", type=_nonnegative_integer, default=20260801)
    parser.add_argument("--root-seed", type=_nonnegative_integer, default=20260802)
    parser.add_argument("--slot-id", type=_positive_integer, default=1)
    parser.add_argument(
        "--verify-oracle",
        action="store_true",
        help="verify only a deliberately tiny case against the exhaustive oracle",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print a start banner and enable native HiGHS progress output",
    )
    return parser


def _solve_for_benchmark(problem, *, verbose: bool):
    if not verbose:
        return solve_coupled_milp(problem)

    def verbose_backend(model, cutoff):
        return solve_scipy_highs(model, cutoff, display=True)

    return solve_coupled_milp(problem, backend_solve=verbose_backend)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    case = make_scale_case(
        flow_count=arguments.flow,
        stage_count=arguments.stage,
        replicas_per_stage=arguments.replica,
        cutoff_seconds=arguments.cutoff,
        profile_seed=arguments.profile_seed,
        root_seed=arguments.root_seed,
        slot_id=arguments.slot_id,
    )
    if arguments.verbose:
        print(
            "MILP benchmark starting: "
            f"scale={case.name} cutoff={case.configuration.cutoff_seconds:g}s "
            "HiGHS-progress=enabled",
            flush=True,
        )
    result = run_scale_case(
        case,
        verify_oracle=arguments.verify_oracle,
        solver=lambda problem: _solve_for_benchmark(
            problem,
            verbose=arguments.verbose,
        ),
    )
    print(format_scale_evidence(result.evidence))
    return int(
        result.evidence.solver_status
        is SolverResultStatus.SOLVER_OR_CONFIGURATION_ERROR
    )


if __name__ == "__main__":
    raise SystemExit(main())
