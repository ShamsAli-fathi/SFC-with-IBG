"""Greedy Phase 8.3: clamped end-to-end Jain fairness and its evidence gate."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from IBG import latency_model
from Greedy.console_output import format_greedy_slot_metrics
from Greedy.contracts import GreedyConfiguration, ReplicaIdentity
from Greedy.csv_export import export_greedy_csv
from Greedy.evidence import (
    GREEDY_SLOT_EVIDENCE_VERSION,
    LEGACY_GREEDY_SLOT_EVIDENCE_VERSION,
    PREDICTED_FAIRNESS_GREEDY_SLOT_EVIDENCE_VERSION,
    build_greedy_slot_evidence,
    validate_greedy_slot_evidence,
)
from Greedy.kernel_contracts import (
    DEFAULT_GREEDY_KERNEL_OWNERSHIP,
    GreedyKernelControllerConfiguration,
    GreedyKernelDiscoveredReplica,
    GreedyKernelDiscoverySnapshot,
)
from Greedy.kernel_controller import GreedyKernelController
from Greedy.kernel_lifecycle import (
    GreedyLaunchConfiguration,
    GreedyLifecycleResult,
)
from Greedy.kernel_profile_reconciliation import materialize_runtime_profiles
from Greedy.kernel_route_contracts import (
    GreedyKernelFlowTelemetry,
    GreedyKernelHopTelemetry,
    GreedyKernelMeasuredPairTelemetry,
    GreedyKernelRunSlotResponse,
)
from Greedy.metrics import (
    GREEDY_METRIC_ASSEMBLY_VERSION,
    LEGACY_GREEDY_METRIC_ASSEMBLY_VERSION,
    clamped_end_to_end_fairness,
    jain_fairness,
)
from Greedy.runtime_resources import GreedyControllerResourceDelta
from Greedy.persistence import (
    GREEDY_TRACE_CONTRACT_VERSION,
    PREDICTED_FAIRNESS_GREEDY_TRACE_CONTRACT_VERSION,
    persist_greedy_trace,
)


UNIFORM = (0.25, 0.25, 0.25, 0.25)
CONFIGURATION = GreedyConfiguration(2, 3, 2)
PROFILE_FINGERPRINT = materialize_runtime_profiles(
    CONFIGURATION, profile_seed=17
).fingerprint


def _identities(configuration):
    return tuple(
        ReplicaIdentity(stage, replica)
        for stage in configuration.stages
        for replica in configuration.replica_ids
    )


def _snapshot(configuration):
    ownership = DEFAULT_GREEDY_KERNEL_OWNERSHIP
    return GreedyKernelDiscoverySnapshot(
        configuration=configuration,
        replicas=tuple(
            GreedyKernelDiscoveredReplica(
                identity=identity,
                namespace=ownership.namespace,
                pod_name=(
                    f"{ownership.stage_name(identity.stage)}-{identity.replica - 1}"
                ),
                pod_uid=f"uid-{identity.stage}-{identity.replica}",
                node_name="greedy-worker",
                endpoint=(
                    f"http://{ownership.stage_name(identity.stage)}"
                    f"-{identity.replica - 1}"
                ),
                phase="Running",
                ready=True,
                labels=ownership.replica_labels(identity.stage),
            )
            for identity in _identities(configuration)
        ),
    )


class _Discovery:
    def __init__(self, value):
        self.value = value

    def wait_for_complete_ready(self, **_kwargs):
        return self.value

    def close(self):
        return None


class _Generator:
    """Emit one controllable physical/pair latency pair per selected hop."""

    def __init__(self, *, physical_ms=20.0, pair_ms=5.0):
        self.physical_ms = physical_ms
        self.pair_ms = pair_ms

    def run_slot(self, request):
        flows = []
        for route in request.routes:
            hops = []
            for target in route.hops:
                signal = self.physical_ms + 2.0
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
                        modeled_processing_latency_ms=self.physical_ms - 1.0,
                        physical_processing_latency_ms=self.physical_ms,
                        observation_jitter_ms=2.0,
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
                request_latency_ms=10.0 + self.pair_ms,
                callee_elapsed_ms=10.0,
                measured_pair_latency_ms=self.pair_ms,
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
            slot_id=request.slot_id, elapsed_ms=1.0, flows=tuple(flows)
        )

    def close(self):
        return None


def _outcome(*, physical_ms=20.0, pair_ms=5.0):
    ticks = iter(float(value) for value in range(6))
    controller = GreedyKernelController(
        controller_configuration=GreedyKernelControllerConfiguration(
            configuration=CONFIGURATION,
            experiment_id=1,
            root_seed=2050,
            profile_seed=17,
            runtime_profile_fingerprint=PROFILE_FINGERPRINT,
            max_iterations=1,
        ),
        discovery=_Discovery(_snapshot(CONFIGURATION)),
        flow_generator=_Generator(physical_ms=physical_ms, pair_ms=pair_ms),
        initial_beliefs={
            identity: UNIFORM for identity in _identities(CONFIGURATION)
        },
        clock=lambda: next(ticks),
    )
    try:
        return controller.run_slot(1, flow_order=(2, 1))
    finally:
        controller.close()


def _control_plane():
    return {
        "schema": "greedy-control-plane-wall-time-v1",
        "timing_ms": {
            "discovery": 1.0,
            "admission": 3.0,
            "feedback": 1.0,
            "active": 4.0,
            "data_plane_wait": 2.0,
        },
        "payload_bytes": {
            "kubernetes_discovery_tx": 7,
            "kubernetes_discovery_rx": 31,
            "route_command_tx": 101,
            "selected_telemetry_rx": 211,
            "belief_tx": 0,
            "belief_rx": 0,
            "total": 350,
        },
        "messages": {
            "kubernetes_discovery_tx": 1,
            "kubernetes_discovery_rx": 1,
            "route_command_tx": 1,
            "selected_telemetry_rx": 1,
            "belief_tx": 0,
            "belief_rx": 0,
            "total": 4,
        },
    }


def _resources():
    return GreedyControllerResourceDelta(
        process_cpu_seconds=0.125,
        process_rss_bytes=32 * 1024 * 1024,
        cgroup_cpu_nr_throttled=2,
        cgroup_cpu_throttled_usec=17,
    )


def _launch(*, csv=0):
    return GreedyLaunchConfiguration(
        configuration=CONFIGURATION,
        max_iterations=1,
        profile_seed=17,
        root_seed=2050,
        rollout_batch_size=1,
        skip_build=True,
        csv=csv,
        parity_replay=0,
    )


def _lifecycle():
    return GreedyLifecycleResult(
        configuration=CONFIGURATION,
        profile_fingerprint=PROFILE_FINGERPRINT,
        root_seed=2050,
        cluster_created=False,
        built_images=(),
        loaded_images=(),
        serving_changed=False,
        controller_jobs_created=1,
        service_source_fingerprint="c" * 64,
        controller_source_fingerprint="d" * 64,
        service_image_id="a" * 64,
        controller_image_id="b" * 64,
        worker_allocatable_cpu_millicores=8000,
        worker_allocatable_memory_mib=16384,
    )


# --- the pure fairness kernel ------------------------------------------------


def test_contract_versions_record_the_phase83_metric_generation():
    assert LEGACY_GREEDY_METRIC_ASSEMBLY_VERSION == "greedy-active-slot-metrics-v1"
    assert GREEDY_METRIC_ASSEMBLY_VERSION == "greedy-active-slot-metrics-v2"
    assert GREEDY_SLOT_EVIDENCE_VERSION == "greedy-kernel-slot-evidence-v3"
    assert GREEDY_TRACE_CONTRACT_VERSION == "greedy-experiment-jsonl-v3"


def test_all_positive_end_to_end_utility_matches_the_unclamped_index():
    values = {1: 150.0, 2: 120.0, 3: 90.0, 4: 60.0}
    fairness, domain_valid = clamped_end_to_end_fairness(values)
    assert domain_valid is True
    assert fairness == pytest.approx(jain_fairness(dict(values), sum(values.values())))
    assert fairness == pytest.approx(420.0**2 / (4 * 48600.0))


def test_equal_positive_flows_are_perfectly_fair():
    fairness, domain_valid = clamped_end_to_end_fairness(
        {flow: 100.0 for flow in range(1, 5)}
    )
    assert domain_valid is True
    assert fairness == pytest.approx(1.0)


def test_a_negative_flow_is_floored_and_flagged_rather_than_squared():
    values = {1: 150.0, 2: 120.0, 3: 90.0, 4: -200.0}
    fairness, domain_valid = clamped_end_to_end_fairness(values)
    assert domain_valid is False
    # Squaring the raw mixed signs would report near-total unfairness even
    # though three of four flows were served normally.
    raw = jain_fairness(dict(values), sum(values.values()))
    assert raw < 0.1
    assert fairness == pytest.approx(360.0**2 / (4 * 45000.0))
    assert fairness > 0.7


def test_every_flow_negative_returns_the_documented_zero_convention():
    fairness, domain_valid = clamped_end_to_end_fairness(
        {1: -100.0, 2: -300.0, 3: -500.0}
    )
    assert (fairness, domain_valid) == (0.0, False)


def test_an_exactly_zero_flow_is_outside_the_strictly_positive_domain():
    fairness, domain_valid = clamped_end_to_end_fairness({1: 100.0, 2: 0.0})
    assert domain_valid is False
    assert fairness == pytest.approx(100.0**2 / (2 * 10000.0))


def test_fairness_requires_at_least_one_flow_and_never_mutates_the_caller():
    with pytest.raises(ValueError, match="at least one flow"):
        clamped_end_to_end_fairness({})
    values = {1: 150.0, 2: -200.0}
    clamped_end_to_end_fairness(values)
    assert values == {1: 150.0, 2: -200.0}


# --- slot assembly -----------------------------------------------------------


def test_slot_fairness_reads_end_to_end_utility_not_the_link_free_prediction():
    metrics = _outcome().slot.metrics
    reference = dict(metrics.raw_end_to_end_reference_utility_per_flow)
    predicted = dict(metrics.predicted_utility_per_flow)
    expected, domain_valid = clamped_end_to_end_fairness(reference)

    assert metrics.jain_fairness == pytest.approx(expected)
    assert metrics.fairness_domain_valid is domain_valid
    # The retired input remains recorded but must no longer drive the index.
    assert metrics.jain_fairness != pytest.approx(
        jain_fairness(dict(predicted), metrics.predicted_aggregate_utility)
    )


def test_uniform_beliefs_no_longer_force_a_degenerate_perfect_index():
    metrics = _outcome().slot.metrics
    predicted = tuple(value for _flow, value in metrics.predicted_utility_per_flow)
    # Every flow shares one predicted value under uniform slot-start beliefs,
    # which is exactly the degeneracy Phase 8.3 removes from the reported index.
    assert len(set(round(value, 9) for value in predicted)) == 1
    assert jain_fairness(
        dict(metrics.predicted_utility_per_flow),
        metrics.predicted_aggregate_utility,
    ) == pytest.approx(1.0, abs=1e-4)


def test_a_swamped_slot_is_flagged_instead_of_reporting_a_fake_index():
    # A pair cost far above the earned stage utility drives every flow's
    # end-to-end utility negative.
    metrics = _outcome(physical_ms=20.0, pair_ms=400.0).slot.metrics
    reference = tuple(
        value for _flow, value in metrics.raw_end_to_end_reference_utility_per_flow
    )
    assert all(value < 0.0 for value in reference)
    assert metrics.fairness_domain_valid is False
    assert metrics.jain_fairness == 0.0


def test_console_labels_the_index_end_to_end_and_marks_clamped_slots():
    healthy = format_greedy_slot_metrics(_outcome().slot, iteration=1)
    assert "end-to-end fairness=" in healthy
    assert "(clamped)" not in healthy

    swamped = format_greedy_slot_metrics(
        _outcome(pair_ms=400.0).slot, iteration=1
    )
    assert "end-to-end fairness=0.000000 (clamped)" in swamped


# --- evidence -----------------------------------------------------------------


def test_v3_evidence_round_trips_with_its_domain_flag():
    evidence = build_greedy_slot_evidence(
        replace(_outcome(), control_plane=None), parity_replay_enabled=False
    )
    assert evidence["contract_version"] == GREEDY_SLOT_EVIDENCE_VERSION
    assert "fairness_domain_valid" in evidence["metrics"]
    assert validate_greedy_slot_evidence(evidence) == evidence


def test_v3_evidence_rejects_a_tampered_fairness_value():
    evidence = build_greedy_slot_evidence(
        replace(_outcome(), control_plane=None), parity_replay_enabled=False
    )
    tampered = deepcopy(evidence)
    tampered["metrics"]["jain_fairness"] = 0.999994
    with pytest.raises(ValueError, match="fairness is inconsistent"):
        validate_greedy_slot_evidence(tampered)


def test_v3_evidence_rejects_a_tampered_or_missing_domain_flag():
    evidence = build_greedy_slot_evidence(
        replace(_outcome(), control_plane=None), parity_replay_enabled=False
    )
    flipped = deepcopy(evidence)
    flipped["metrics"]["fairness_domain_valid"] = not flipped["metrics"][
        "fairness_domain_valid"
    ]
    with pytest.raises(ValueError, match="fairness domain flag is inconsistent"):
        validate_greedy_slot_evidence(flipped)

    wrong_type = deepcopy(evidence)
    wrong_type["metrics"]["fairness_domain_valid"] = "true"
    with pytest.raises(ValueError, match="fairness domain flag must be boolean"):
        validate_greedy_slot_evidence(wrong_type)

    dropped = deepcopy(evidence)
    del dropped["metrics"]["fairness_domain_valid"]
    with pytest.raises(ValueError, match="metric fields are incomplete"):
        validate_greedy_slot_evidence(dropped)


def test_v2_evidence_keeps_the_retired_predicted_index_and_rejects_the_flag():
    evidence = build_greedy_slot_evidence(
        replace(_outcome(), control_plane=None), parity_replay_enabled=False
    )
    predicted = dict(
        (flow, value) for flow, value in evidence["metrics"]["predicted_utility_per_flow"]
    )
    legacy = deepcopy(evidence)
    legacy["contract_version"] = PREDICTED_FAIRNESS_GREEDY_SLOT_EVIDENCE_VERSION
    del legacy["metrics"]["fairness_domain_valid"]
    legacy["metrics"]["jain_fairness"] = (
        float(legacy["metrics"]["predicted_aggregate_utility"]) ** 2
        / (len(predicted) * sum(round(value, 3) ** 2 for value in predicted.values()))
    )
    assert validate_greedy_slot_evidence(legacy) == legacy

    # A v2 document must not carry the Phase 8.3 field.
    backfilled = deepcopy(legacy)
    backfilled["metrics"]["fairness_domain_valid"] = True
    with pytest.raises(ValueError, match="metric fields are incomplete"):
        validate_greedy_slot_evidence(backfilled)


def test_unknown_evidence_generations_are_refused():
    evidence = build_greedy_slot_evidence(
        replace(_outcome(), control_plane=None), parity_replay_enabled=False
    )
    unknown = deepcopy(evidence)
    unknown["contract_version"] = "greedy-kernel-slot-evidence-v4"
    with pytest.raises(ValueError, match="unsupported Greedy slot evidence version"):
        validate_greedy_slot_evidence(unknown)
    assert LEGACY_GREEDY_SLOT_EVIDENCE_VERSION == "greedy-kernel-slot-evidence-v1"


# --- retained CSV -------------------------------------------------------------


def _v3_trace(tmp_path, name):
    outcome = replace(
        _outcome(),
        control_plane=_control_plane(),
        controller_resources=_resources(),
    )
    return persist_greedy_trace(
        (build_greedy_slot_evidence(outcome, parity_replay_enabled=False),),
        launch=_launch(csv=1),
        lifecycle=_lifecycle(),
        trace_dir=tmp_path / name,
        run_id=name,
        recorded_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def test_csv_marker_pins_both_the_policy_and_trace_contract(tmp_path):
    trace = _v3_trace(tmp_path, "run-a")
    csv_dir = tmp_path / "csv"
    export_greedy_csv(trace.path, csv_dir)
    marker = json.loads(
        (csv_dir / ".greedy-csv-policy-contract.json").read_text(encoding="utf-8")
    )
    assert marker == {
        "policy_contract_version": "pure-greedy-budgeted-l2-v2",
        "trace_contract_version": GREEDY_TRACE_CONTRACT_VERSION,
    }
    # A second same-generation run may still append its column.
    export_greedy_csv(_v3_trace(tmp_path, "run-b").path, csv_dir)


def test_csv_refuses_a_pre_phase83_marker(tmp_path):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    (csv_dir / ".greedy-csv-policy-contract.json").write_text(
        json.dumps({"policy_contract_version": "pure-greedy-budgeted-l2-v2"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="pre-Phase-8.3 marker"):
        export_greedy_csv(_v3_trace(tmp_path, "run-a").path, csv_dir)


def test_csv_refuses_a_foreign_trace_contract_generation(tmp_path):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    (csv_dir / ".greedy-csv-policy-contract.json").write_text(
        json.dumps(
            {
                "policy_contract_version": "pure-greedy-budgeted-l2-v2",
                "trace_contract_version": (
                    PREDICTED_FAIRNESS_GREEDY_TRACE_CONTRACT_VERSION
                ),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="refuses mixed policy or trace contract"):
        export_greedy_csv(_v3_trace(tmp_path, "run-a").path, csv_dir)
