from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

import pytest

from IBG import latency_model
from Greedy.comparison import (
    CANONICAL_MATCHED_COMPARISON,
    GREEDY_PHASE3_HYBRID_SOURCE_AUDIT,
    GREEDY_PHASE4_HYBRID_SOURCE_AUDIT,
    GREEDY_PHASE5_HYBRID_SOURCE_AUDIT,
    GREEDY_PHASE6_HYBRID_SOURCE_AUDIT,
    GREEDY_PHASE7_HYBRID_AUDIT_HEAD,
    GREEDY_PHASE7_HYBRID_SOURCE_AUDIT,
    GREEDY_PHASE81_HYBRID_AUDIT_HEAD,
    GREEDY_PHASE81_HYBRID_SOURCE_AUDIT,
    INTENTIONAL_POLICY_DIFFERENCE_FIELDS,
    REQUIRED_MATCHED_FIELDS,
)
from Greedy.contracts import (
    GreedyConfiguration,
    PublicReplicaState,
    ReplicaIdentity,
)
from Greedy.csv_export import _read
from Greedy.kernel_contracts import (
    DEFAULT_GREEDY_KERNEL_OWNERSHIP,
    GreedyKernelControllerConfiguration,
    GreedyKernelDiscoveredReplica,
    GreedyKernelDiscoverySnapshot,
)
from Greedy.kernel_controller import GreedyKernelController
from Greedy.kernel_infrastructure import (
    GreedyServingReadiness,
    GreedyStaticDeploymentInput,
    parse_resource_documents,
    render_controller_job,
    render_kind_configuration,
    render_long_running_resources,
    render_resource_documents,
    validate_long_running_resources,
)
from Greedy.kernel_profile_reconciliation import materialize_runtime_profiles
from Greedy.kernel_route_contracts import (
    GreedyKernelFlowTelemetry,
    GreedyKernelHopTelemetry,
    GreedyKernelMeasuredPairTelemetry,
    GreedyKernelRunSlotResponse,
)
from Greedy.policy import GreedyPolicy
from Greedy.runtime_resources import GreedyControllerResourceSnapshot


ROOT = Path(__file__).resolve().parents[1]
UNIFORM = (0.25, 0.25, 0.25, 0.25)


def _identities(configuration: GreedyConfiguration) -> tuple[ReplicaIdentity, ...]:
    return tuple(
        ReplicaIdentity(stage, replica)
        for stage in configuration.stages
        for replica in configuration.replica_ids
    )


def _public_states(
    configuration: GreedyConfiguration,
) -> tuple[PublicReplicaState, ...]:
    return tuple(
        PublicReplicaState(
            identity=identity,
            ready=True,
            belief=UNIFORM,
        )
        for identity in _identities(configuration)
    )


def _deployment(configuration: GreedyConfiguration) -> GreedyStaticDeploymentInput:
    return GreedyStaticDeploymentInput(
        runtime_profiles=materialize_runtime_profiles(configuration, profile_seed=17),
        experiment_id=1,
        root_seed=2050,
        profile_seed=17,
        max_iterations=2,
        first_slot_id=1,
        source_identity=(
            f"greedy-phase7-{configuration.num_flows}x"
            f"{configuration.num_stages}x{configuration.num_replicas}"
        ),
    )


def _snapshot(
    configuration: GreedyConfiguration,
) -> GreedyKernelDiscoverySnapshot:
    ownership = DEFAULT_GREEDY_KERNEL_OWNERSHIP
    return GreedyKernelDiscoverySnapshot(
        configuration=configuration,
        replicas=tuple(
            GreedyKernelDiscoveredReplica(
                identity=identity,
                namespace=ownership.namespace,
                pod_name=f"{ownership.stage_name(identity.stage)}-{identity.replica - 1}",
                pod_uid=f"uid-{identity.stage}-{identity.replica}",
                node_name="greedy-worker",
                endpoint=(
                    f"http://{ownership.stage_name(identity.stage)}-"
                    f"{identity.replica - 1}.{ownership.stage_name(identity.stage)}."
                    f"{ownership.namespace}.svc.cluster.local.:8080"
                ),
                phase="Running",
                ready=True,
                labels=ownership.replica_labels(identity.stage),
            )
            for identity in _identities(configuration)
        ),
    )


def _response(request) -> GreedyKernelRunSlotResponse:
    flows = []
    for route in request.routes:
        hops = []
        for target in route.hops:
            physical_ms = 20.0
            observation_ms = 2.0
            signal = physical_ms + observation_ms
            likelihood = latency_model.learning_signal_likelihood(
                signal, target.assigned_load
            )
            hops.append(
                GreedyKernelHopTelemetry(
                    slot_id=request.slot_id,
                    flow_id=route.flow_id,
                    stage=target.stage,
                    replica_id=target.replica_id,
                    route_position=target.route_position,
                    next_stage=target.next_stage,
                    next_replica_id=target.next_replica_id,
                    pod_name=urlparse(str(target.url)).hostname.split(".")[0],
                    endpoint=str(target.url),
                    concurrency=1,
                    assigned_load=target.assigned_load,
                    modeled_processing_latency_ms=19.0,
                    physical_processing_latency_ms=physical_ms,
                    observation_jitter_ms=observation_ms,
                    learning_signal_ms=signal,
                    request_latency_ms=10.0,
                    transport_overhead_ms=1.0,
                    estimated_state=latency_model.estimate_state(likelihood),
                    likelihood=likelihood,
                )
            )
        first, second = route.hops
        pair = GreedyKernelMeasuredPairTelemetry(
            slot_id=request.slot_id,
            flow_id=route.flow_id,
            source_stage=first.stage,
            source_replica_id=first.replica_id,
            source_pod_name=hops[0].pod_name,
            target_stage=second.stage,
            target_replica_id=second.replica_id,
            target_pod_name=hops[1].pod_name,
            target_endpoint=str(second.url),
            request_latency_ms=15.0,
            callee_elapsed_ms=10.0,
            measured_pair_latency_ms=5.0,
        )
        flows.append(
            GreedyKernelFlowTelemetry(
                flow_id=route.flow_id,
                bypassed_stages=route.bypassed_stages,
                hops=tuple(hops),
                measured_pair=pair,
                ingress_request_latency_ms=20.0,
                ingress_overhead_ms=2.0,
            )
        )
    return GreedyKernelRunSlotResponse(
        slot_id=request.slot_id,
        elapsed_ms=1.0,
        flows=tuple(flows),
    )


class _Discovery:
    def __init__(self, snapshot: GreedyKernelDiscoverySnapshot) -> None:
        self.snapshot = snapshot
        self.close_calls = 0

    def wait_for_complete_ready(self, **_kwargs):
        return self.snapshot

    def close(self) -> None:
        self.close_calls += 1


class _Generator:
    def __init__(self) -> None:
        self.requests = 0
        self.close_calls = 0

    def run_slot(self, request):
        self.requests += 1
        return _response(request)

    def close(self) -> None:
        self.close_calls += 1


def _run_controller_experiment(*, measured: bool):
    configuration = GreedyConfiguration(2, 3, 2)
    discovery = _Discovery(_snapshot(configuration))
    generator = _Generator()
    ticks = iter(float(value) for value in range(12))
    samples = iter(
        (
            GreedyControllerResourceSnapshot(1.0, 10, 2, 20),
            GreedyControllerResourceSnapshot(1.25, 12, 5, 29),
            GreedyControllerResourceSnapshot(2.0, 14, 6, 32),
            GreedyControllerResourceSnapshot(2.5, 16, 8, 37),
        )
    )
    controller = GreedyKernelController(
        controller_configuration=GreedyKernelControllerConfiguration(
            configuration=configuration,
            experiment_id=1,
            root_seed=2050,
            profile_seed=17,
            runtime_profile_fingerprint="phase7-public-fingerprint",
            max_iterations=2,
        ),
        discovery=discovery,
        flow_generator=generator,
        initial_beliefs={identity: UNIFORM for identity in _identities(configuration)},
        clock=lambda: next(ticks),
        resource_sampler=(lambda: next(samples)) if measured else None,
    )
    result = controller.run_experiment(
        flow_orders_by_slot={1: (2, 1), 2: (1, 2)}
    )
    return result, discovery, generator


def _audit_paths(record):
    locations = tuple(item.strip() for item in record.source_location.split(";"))
    blobs = tuple(record.git_blob.split("/"))
    assert len(locations) == len(blobs)
    return tuple(
        (location.split(":", 1)[0], blob)
        for location, blob in zip(locations, blobs, strict=True)
    )


def test_phase7_comparison_envelope_matches_current_active_hybrid_sources():
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert len(head) == len(GREEDY_PHASE7_HYBRID_AUDIT_HEAD) == 40
    assert GREEDY_PHASE81_HYBRID_AUDIT_HEAD == (
        "ae95e74497339b6ce49d96a709409489ef287fd5"
    )

    audits = (
        *GREEDY_PHASE3_HYBRID_SOURCE_AUDIT,
        *GREEDY_PHASE4_HYBRID_SOURCE_AUDIT,
        *GREEDY_PHASE5_HYBRID_SOURCE_AUDIT,
        *GREEDY_PHASE6_HYBRID_SOURCE_AUDIT,
        *GREEDY_PHASE7_HYBRID_SOURCE_AUDIT,
        *GREEDY_PHASE81_HYBRID_SOURCE_AUDIT,
    )
    assert {item.disposition for item in audits} <= {"reuse", "adapt", "exclude"}
    for audit in audits:
        for source_path, expected_blob in _audit_paths(audit):
            actual_blob = subprocess.run(
                ["git", "hash-object", source_path],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            assert actual_blob == expected_blob, source_path

    comparison = CANONICAL_MATCHED_COMPARISON
    assert tuple(item.name for item in comparison.required_matches) == REQUIRED_MATCHED_FIELDS
    assert all(item.greedy_value == item.hybrid_value for item in comparison.required_matches)
    assert tuple(
        item.name for item in comparison.intentional_policy_differences
    ) == INTENTIONAL_POLICY_DIFFERENCE_FIELDS
    assert all(
        item.greedy_value != item.hybrid_value
        for item in comparison.intentional_policy_differences
    )
    assert len(comparison.unresolved_mismatches) == 1
    assert comparison.unresolved_mismatches[0].name == "assigned_flow_admission"


@pytest.mark.parametrize("dimensions", ((3, 2, 1), (5, 2, 2), (5, 4, 3)))
def test_arbitrary_shapes_are_policy_complete_and_offline_renderable(dimensions):
    configuration = GreedyConfiguration(*dimensions)
    policy = GreedyPolicy(configuration, utility_cache_max_entries=2)
    flow_order = tuple(range(configuration.num_flows, 0, -1))
    cached = policy.place(
        flow_order=flow_order,
        replica_states=_public_states(configuration),
    )
    uncached = GreedyPolicy(configuration).place(
        flow_order=flow_order,
        replica_states=_public_states(configuration),
        use_cache=False,
    )
    assert cached == uncached
    assert len(cached.decisions) == configuration.num_flows
    assert cached.final_loads.total_assignments == 2 * configuration.num_flows
    assert all(0 <= load <= configuration.num_flows for _, load in cached.final_loads.entries)
    assert all(
        len(decision.action.choices) == 2
        and len(decision.bypassed_stages) == configuration.num_stages - 2
        for decision in cached.decisions
    )
    assert policy.utility_cache_info.size <= policy.utility_cache_info.max_entries == 2

    deployment = _deployment(configuration)
    resources = render_long_running_resources(deployment)
    rendered = render_resource_documents(resources)
    parsed = parse_resource_documents(rendered)
    validate_long_running_resources(deployment, parsed)
    readiness = GreedyServingReadiness(
        configuration=configuration,
        ready_identities=_identities(configuration),
        flow_generator_ready=True,
    )
    job = render_controller_job(deployment, readiness)
    assert parse_resource_documents(render_resource_documents((*parsed, job)))[-1] == job
    assert len(tuple(item for item in parsed if item["kind"] == "StatefulSet")) == configuration.num_stages
    assert all(
        item["spec"]["replicas"] == configuration.num_replicas
        for item in parsed
        if item["kind"] == "StatefulSet"
    )
    assert render_kind_configuration()["nodes"] == [
        {"role": "control-plane"},
        {"role": "worker", "labels": {"greedy.workload-node": "true"}},
    ]


def test_controller_resource_measurement_is_semantically_neutral():
    plain, plain_discovery, plain_generator = _run_controller_experiment(
        measured=False
    )
    measured, measured_discovery, measured_generator = _run_controller_experiment(
        measured=True
    )
    assert measured.pure_experiment == plain.pure_experiment
    assert tuple(replace(slot, controller_resources=None) for slot in measured.slots) == plain.slots
    assert all(slot.controller_resources is None for slot in plain.slots)
    assert all(slot.controller_resources is not None for slot in measured.slots)
    assert plain_generator.requests == measured_generator.requests == len(plain.slots)
    assert plain_discovery.close_calls == measured_discovery.close_calls == 1
    assert plain_generator.close_calls == measured_generator.close_calls == 1


def test_csv_retained_file_reader_refuses_duplicate_and_overwide_rows(tmp_path):
    duplicate = tmp_path / "duplicate.csv"
    duplicate.write_text("run,run\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid headers"):
        _read(duplicate)

    overwide = tmp_path / "overwide.csv"
    overwide.write_text("run\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds its headers"):
        _read(overwide)


def test_all_phase0_to_phase6_owned_imports_are_silent_rng_neutral_and_file_free(
    tmp_path,
):
    modules = (
        "Greedy.phase0_contract",
        "Greedy.legacy_characterization",
        "Greedy.contracts",
        "Greedy.expected_utility",
        "Greedy.policy",
        "Greedy.comparison",
        "Greedy.slot_contracts",
        "Greedy.simulation",
        "Greedy.learning",
        "Greedy.metrics",
        "Greedy.runner",
        "Greedy.oracle",
        "Greedy.kernel_contracts",
        "Greedy.kernel_controller_config",
        "Greedy.kernel_kubernetes_discovery",
        "Greedy.kernel_route_contracts",
        "Greedy.kernel_route_execution",
        "Greedy.kernel_controller",
        "Greedy.kernel_oracle",
        "Greedy.kernel_processor_service",
        "Greedy.kernel_route_forwarder",
        "Greedy.kernel_route_forwarder_service",
        "Greedy.kernel_flow_generator",
        "Greedy.kernel_runtime_profiles",
        "Greedy.kernel_infrastructure",
        "Greedy.kernel_profile_reconciliation",
        "Greedy.kernel_rollout",
        "Greedy.kernel_lifecycle",
        "Greedy.console_output",
        "Greedy.control_plane_footprint",
        "Greedy.runtime_resources",
        "Greedy.evidence_replay",
        "Greedy.evidence",
        "Greedy.persistence",
        "Greedy.csv_export",
        "Greedy.kernel_reporting",
        "Greedy.kernel_controller_service",
        "scripts.greedy_offline_wheelhouse",
        "scripts.render_greedy_kubernetes",
        "scripts.run_greedy_kernel",
    )
    code = (
        "import importlib, pathlib, random; import numpy as np; "
        "random.seed(7301); np.random.seed(7301); "
        "py_before=random.getstate(); np_before=np.random.get_state(); "
        + "; ".join(f"importlib.import_module({module!r})" for module in modules)
        + "; assert random.getstate() == py_before; "
        "np_after=np.random.get_state(); "
        "assert np_before[0] == np_after[0] and "
        "np.array_equal(np_before[1], np_after[1]) and "
        "np_before[2:] == np_after[2:]"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        check=True,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.stdout == completed.stderr == ""
    assert list(tmp_path.iterdir()) == []
