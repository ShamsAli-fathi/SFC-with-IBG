"""Guarded in-cluster controller for one centralized MILP Kernel slot."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path

from .cli import _positive_finite_cutoff, _positive_integer, _stage_count
from .contracts import MILPConfiguration
from .experiment_profile import MILPExperimentProfile, load_experiment_profile
from .kernel_adapter import (
    MILPKernelDiscovery,
    MILPKubernetesReplicaDiscovery,
    MILPKubernetesTrafficAdapter,
    wait_for_milp_flow_generator,
    wait_for_milp_ready_replicas,
)
from .kubernetes_api import MILPKubernetesApi
from .kernel_contracts import MILPKernelSlotInput, MILPKernelSlotResult
from .kernel_profiles import build_kernel_problem_input
from .kernel_runner import format_milp_kernel_metrics, run_milp_kernel_slot
from .phase0_contract import DEFAULT_MILP_DIMENSIONS
from .runtime_profiles import MILPRuntimeReplicaProfile
from .replay import replay_milp_trace
from .solver import solve_coupled_milp, solve_scipy_highs
from .trace_contracts import build_milp_trace


@dataclass(frozen=True)
class MILPKernelExperimentRunResult:
    """Kernel slot result paired with its canonical input provenance."""

    profile: MILPExperimentProfile
    slot_result: MILPKernelSlotResult

    def __post_init__(self) -> None:
        if self.profile.configuration != self.slot_result.configuration:
            raise RuntimeError("Kernel experiment profile/result configuration mismatch")

    @property
    def profile_fingerprint(self) -> str:
        return self.profile.fingerprint


def build_parser() -> argparse.ArgumentParser:
    namespace = os.environ.get("POD_NAMESPACE", "milp-testbed")
    parser = argparse.ArgumentParser(
        prog="python -m MILP.kernel_controller",
        description="Run one coupled/budgeted MILP slot over the Kernel testbed.",
    )
    parser.add_argument("--flow", type=_positive_integer, default=DEFAULT_MILP_DIMENSIONS.flow_count)
    parser.add_argument("--stage", type=_stage_count, default=DEFAULT_MILP_DIMENSIONS.stage_count)
    parser.add_argument("--replica", type=_positive_integer, default=DEFAULT_MILP_DIMENSIONS.replicas_per_stage[0])
    parser.add_argument("--cutoff", type=_positive_finite_cutoff, required=True, metavar="SECONDS")
    parser.add_argument("--slot-id", type=_positive_integer, default=1)
    parser.add_argument("--namespace", default=namespace)
    parser.add_argument(
        "--flow-generator-url",
        default=f"http://milp-flow-generator.{namespace}.svc.cluster.local.:8080",
    )
    parser.add_argument(
        "--experiment-profile",
        default=os.environ.get(
            "MILP_EXPERIMENT_PROFILE_PATH",
            "/etc/milp/experiment.json",
        ),
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def _solver(verbose: bool):
    if not verbose:
        return solve_coupled_milp

    def solve(problem):
        return solve_coupled_milp(
            problem,
            backend_solve=lambda model, cutoff: solve_scipy_highs(
                model,
                cutoff,
                display=True,
            ),
        )

    return solve


def execute_milp_kernel_controller(
    configuration: MILPConfiguration,
    *,
    slot_id: int,
    experiment_profile: MILPExperimentProfile | None = None,
    profiles: Mapping[tuple[int, int], MILPRuntimeReplicaProfile] | None = None,
    planning_link_document: object | None = None,
    assigned_flow_capacity_per_replica: int | None = None,
    discovery: MILPKernelDiscovery,
    traffic_adapter: MILPKubernetesTrafficAdapter,
    solver=solve_coupled_milp,
    verify_replay: bool = False,
) -> MILPKernelSlotResult:
    """Discover first, construct the model second, and solve exactly once."""

    endpoints = discovery.discover_all(configuration.dimensions)
    problem = build_kernel_problem_input(
        configuration,
        endpoints=endpoints,
        experiment_profile=experiment_profile,
        profiles=profiles,
        planning_link_document=planning_link_document,
        assigned_flow_capacity_per_replica=assigned_flow_capacity_per_replica,
    )
    result = run_milp_kernel_slot(
        MILPKernelSlotInput(
            problem=problem,
            slot_id=slot_id,
            endpoints=endpoints,
        ),
        solver=solver,
        traffic_adapter=traffic_adapter,
    )
    if verify_replay:
        replay_milp_trace(build_milp_trace(problem, result))
    return result


def execute_milp_kernel_experiment(
    profile: MILPExperimentProfile,
    *,
    slot_id: int,
    discovery: MILPKernelDiscovery,
    traffic_adapter: MILPKubernetesTrafficAdapter,
    solver=solve_coupled_milp,
    verify_replay: bool = False,
) -> MILPKernelExperimentRunResult:
    return MILPKernelExperimentRunResult(
        profile=profile,
        slot_result=execute_milp_kernel_controller(
            profile.configuration,
            slot_id=slot_id,
            experiment_profile=profile,
            discovery=discovery,
            traffic_adapter=traffic_adapter,
            solver=solver,
            verify_replay=verify_replay,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    configuration = MILPConfiguration.uniform(
        flow_count=arguments.flow,
        stage_count=arguments.stage,
        replicas_per_stage=arguments.replica,
        cutoff_seconds=arguments.cutoff,
    )
    profile = load_experiment_profile(Path(arguments.experiment_profile))
    if profile.configuration != configuration:
        raise RuntimeError(
            "controller dimensions/cutoff do not match the mounted MILP experiment profile"
        )
    api = MILPKubernetesApi(arguments.namespace)
    discovery = MILPKubernetesReplicaDiscovery(api, arguments.namespace)
    wait_for_milp_flow_generator(arguments.flow_generator_url)
    endpoints = wait_for_milp_ready_replicas(
        discovery,
        configuration.dimensions,
    )

    class ReadySnapshotDiscovery:
        def discover_all(self, dimensions):
            if dimensions != configuration.dimensions:
                raise RuntimeError("Ready snapshot dimensions changed")
            return endpoints

    if arguments.verbose:
        print(
            "MILP Kernel starting: "
            f"scale={arguments.flow}x{arguments.stage}x{arguments.replica} "
            f"cutoff={arguments.cutoff:g}s profile={profile.source} "
            f"fingerprint={profile.fingerprint} "
            f"profile-contract={profile.contract_version} "
            f"link-contract={profile.planning_link_contract_version} "
            f"link-source={profile.planning_link_source} "
            f"link-mode={profile.planning_link_mode} HiGHS-progress=enabled",
            flush=True,
        )
    execution = execute_milp_kernel_experiment(
        profile,
        slot_id=arguments.slot_id,
        discovery=ReadySnapshotDiscovery(),
        traffic_adapter=MILPKubernetesTrafficAdapter(arguments.flow_generator_url),
        solver=_solver(arguments.verbose),
        verify_replay=True,
    )
    result = execution.slot_result
    print(
        f"{format_milp_kernel_metrics(result)} profile={profile.source} "
        f"fingerprint={profile.fingerprint} "
        f"profile-contract={profile.contract_version} "
        f"link-contract={profile.planning_link_contract_version} "
        f"link-source={profile.planning_link_source} "
        f"link-mode={profile.planning_link_mode} replay=ok",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
