"""Guarded pure execution of the canonical MILP experiment profile."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from dataclasses import dataclass
from pathlib import Path

from .cli import _positive_finite_cutoff, _positive_integer, _stage_count
from .contracts import MILPConfiguration
from .experiment_profile import (
    MILPExperimentProfile,
    build_experiment_profile_from_runtime_states,
)
from .phase0_contract import DEFAULT_MILP_DIMENSIONS
from .runner import run_milp_slot
from .runtime_profiles import (
    expand_milp_runtime_profiles,
    load_milp_runtime_profiles,
)
from .scaling import (
    build_synthetic_scale_experiment_profile,
    make_scale_case,
)
from .slot_contracts import MILPSlotInput, MILPSlotResult
from .solver import solve_coupled_milp, solve_scipy_highs


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_PROFILE_PATH = ROOT / "deploy/milp-kubernetes/profiles.json"
RUNTIME_PLANNER_PROFILE = "runtime"
SYNTHETIC_SCALE_PLANNER_PROFILE = "synthetic-scale"


@dataclass(frozen=True)
class MILPExperimentRunResult:
    """Structured same-input provenance alongside the ordinary slot result."""

    profile: MILPExperimentProfile
    slot_result: MILPSlotResult

    @property
    def profile_fingerprint(self) -> str:
        return self.profile.fingerprint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m MILP.experiment",
        description=(
            "Run one pure coupled-MILP slot using the same canonical input "
            "profile as the Kernel launcher."
        ),
    )
    parser.add_argument("--flow", type=_positive_integer, default=DEFAULT_MILP_DIMENSIONS.flow_count)
    parser.add_argument("--stage", type=_stage_count, default=DEFAULT_MILP_DIMENSIONS.stage_count)
    parser.add_argument("--replica", type=_positive_integer, default=DEFAULT_MILP_DIMENSIONS.replicas_per_stage[0])
    parser.add_argument("--cutoff", type=_positive_finite_cutoff, required=True, metavar="SECONDS")
    parser.add_argument(
        "--planner-profile",
        choices=(RUNTIME_PLANNER_PROFILE, SYNTHETIC_SCALE_PLANNER_PROFILE),
        default=RUNTIME_PLANNER_PROFILE,
        help=(
            "runtime uses deployed replica states plus a supplied planning-link "
            "input; synthetic-scale temporarily reuses the Phase 4 benchmark's "
            "complete planner input"
        ),
    )
    parser.add_argument(
        "--profile-seed",
        type=_nonnegative_integer,
        default=20260801,
        help="Phase 4 synthetic-scale profile seed (default: 20260801)",
    )
    planning = parser.add_mutually_exclusive_group(required=False)
    planning.add_argument(
        "--planning-link-ms",
        type=float,
        help=(
            "uniform planning coefficient; for exact L=2 it contributes a "
            "constant deduction once per flow"
        ),
    )
    planning.add_argument(
        "--planning-links",
        type=Path,
        help="complete versioned explicit directed planning-link JSON document",
    )
    parser.add_argument(
        "--assigned-flow-capacity",
        type=_positive_integer,
        default=None,
        metavar="FLOWS",
        help="MILP capacity per replica in assigned flows per slot (default: --flow)",
    )
    parser.add_argument("--root-seed", type=int, default=20260802)
    parser.add_argument("--slot-id", type=_positive_integer, default=1)
    parser.add_argument("--verbose", action="store_true")
    return parser


def _nonnegative_integer(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return value


def _validate_profile_arguments(arguments) -> None:
    has_planning_input = (
        arguments.planning_link_ms is not None or arguments.planning_links is not None
    )
    if arguments.planner_profile == RUNTIME_PLANNER_PROFILE:
        if not has_planning_input:
            raise ValueError(
                "runtime planner profile requires exactly one of "
                "--planning-link-ms or --planning-links"
            )
        return
    if has_planning_input:
        raise ValueError(
            "synthetic-scale planner profile already supplies its complete "
            "planning-link table; do not pass --planning-link-ms or --planning-links"
        )


def _planning_document(arguments) -> object:
    if arguments.planning_links is not None:
        return json.loads(arguments.planning_links.read_text(encoding="utf-8"))
    return {
        "contract_version": "milp-planning-links-v1",
        "source": "cli-uniform",
        "uniform_cost_ms": arguments.planning_link_ms,
    }


def build_pure_experiment_profile(arguments) -> MILPExperimentProfile:
    _validate_profile_arguments(arguments)
    configuration = MILPConfiguration.uniform(
        flow_count=arguments.flow,
        stage_count=arguments.stage,
        replicas_per_stage=arguments.replica,
        cutoff_seconds=arguments.cutoff,
    )
    if arguments.planner_profile == SYNTHETIC_SCALE_PLANNER_PROFILE:
        return build_synthetic_scale_experiment_profile(
            make_scale_case(
                flow_count=arguments.flow,
                stage_count=arguments.stage,
                replicas_per_stage=arguments.replica,
                cutoff_seconds=arguments.cutoff,
                profile_seed=arguments.profile_seed,
                root_seed=arguments.root_seed,
                slot_id=arguments.slot_id,
            )
        )
    profiles = expand_milp_runtime_profiles(
        load_milp_runtime_profiles(DEFAULT_RUNTIME_PROFILE_PATH),
        arguments.stage,
        arguments.replica,
    )
    return build_experiment_profile_from_runtime_states(
        configuration,
        runtime_profiles=profiles,
        assigned_flow_capacity_per_replica=arguments.assigned_flow_capacity,
        planning_link_document=_planning_document(arguments),
        source_identity="deploy/milp-kubernetes/profiles.json:state-only-v1",
    )


def _solver(verbose: bool):
    if not verbose:
        return solve_coupled_milp

    def solve(problem):
        return solve_coupled_milp(
            problem,
            backend_solve=lambda model, cutoff: solve_scipy_highs(
                model, cutoff, display=True
            ),
        )

    return solve


def run_experiment_profile(
    profile: MILPExperimentProfile,
    *,
    root_seed: int,
    slot_id: int,
    verbose: bool = False,
) -> MILPExperimentRunResult:
    slot_input = MILPSlotInput(
        problem=profile.problem_input(),
        root_seed=root_seed,
        slot_id=slot_id,
        measured_pair_profiles=profile.measured_pair_profiles,
    )
    return MILPExperimentRunResult(
        profile=profile,
        slot_result=run_milp_slot(slot_input, solver=_solver(verbose)),
    )


def format_experiment_result(result: MILPExperimentRunResult) -> str:
    profile = result.profile
    slot = result.slot_result
    dimensions = profile.configuration.dimensions
    metrics = slot.metrics
    return (
        f"MILP-Pure scale={dimensions.flow_count}x{dimensions.stage_count}x"
        f"{dimensions.replicas_per_stage[0]} slot={slot.slot_id} "
        f"cutoff={profile.configuration.cutoff_seconds:g}s "
        f"status={metrics.solver_status.value} "
        f"optimal={int(slot.solver_result.provenance.optimality_proven)} "
        f"incumbent={metrics.incumbent_objective_utility:.6g} "
        f"bound={metrics.best_bound_utility:.6g} gap={metrics.relative_gap:.6g} "
        f"expected-stage={metrics.solver_expected_stage_welfare_utility:.3f} "
        f"planning={metrics.solver_configured_planning_link_cost_ms:.3f} "
        f"social={metrics.solver_total_social_welfare_utility:.3f} "
        f"realized={metrics.physical_realized_utility:.3f} "
        f"sla={metrics.physical_only_sla_violations} "
        f"jain={metrics.jain_fairness:.6f} "
        f"solve={metrics.solver_seconds:.6f}s total={metrics.total_slot_seconds:.6f}s "
        f"profile={profile.source_identity} fingerprint={profile.fingerprint} "
        f"profile-contract={profile.contract_version} "
        f"link-contract={profile.planning_link_contract_version} "
        f"link-source={profile.planning_link_source} "
        f"link-mode={profile.planning_link_mode}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.root_seed < 0:
        raise ValueError("root-seed must be a nonnegative integer")
    profile = build_pure_experiment_profile(arguments)
    if arguments.verbose:
        print(
            "MILP pure starting: "
            f"scale={arguments.flow}x{arguments.stage}x{arguments.replica} "
            f"cutoff={arguments.cutoff:g}s profile={profile.source_identity} "
            f"fingerprint={profile.fingerprint} "
            f"profile-contract={profile.contract_version} "
            f"link-contract={profile.planning_link_contract_version} "
            f"link-source={profile.planning_link_source} "
            f"link-mode={profile.planning_link_mode} HiGHS-progress=enabled",
            flush=True,
        )
    result = run_experiment_profile(
        profile,
        root_seed=arguments.root_seed,
        slot_id=arguments.slot_id,
        verbose=arguments.verbose,
    )
    print(format_experiment_result(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
