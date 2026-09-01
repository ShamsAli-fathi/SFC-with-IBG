from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

import pytest

from IBG import latency_model
from Greedy.comparison import (
    GREEDY_PHASE6_HYBRID_AUDIT_HEAD,
    GREEDY_PHASE6_HYBRID_SOURCE_AUDIT,
    LEGACY_GREEDY_HYBRID_MATCHED_COMPARISON_VERSION,
)
from Greedy.console_output import (
    format_greedy_replica_beliefs,
    format_greedy_slot_metrics,
)
from Greedy.contracts import (
    LEGACY_GREEDY_POLICY_VERSION,
    GreedyConfiguration,
    ReplicaIdentity,
)
from Greedy.control_plane_footprint import GreedyControlPlaneMeter
from Greedy.csv_export import GREEDY_CSV_FILENAMES, export_greedy_csv
from Greedy.evidence import (
    GREEDY_SLOT_EVIDENCE_PREFIX,
    LEGACY_GREEDY_SLOT_EVIDENCE_VERSION,
    build_greedy_slot_evidence,
    canonical_greedy_evidence_json,
    validate_greedy_slot_evidence,
)
from Greedy.kernel_contracts import (
    DEFAULT_GREEDY_KERNEL_OWNERSHIP,
    GreedyKernelControllerConfiguration,
    GreedyKernelDiscoveredReplica,
    GreedyKernelDiscoverySnapshot,
)
from Greedy.kernel_controller import GreedyKernelController
from Greedy.kernel_infrastructure import GreedyServingReadiness, render_controller_job
from Greedy.kernel_lifecycle import (
    GreedyLaunchConfiguration,
    GreedyLifecycleResult,
)
from Greedy.kernel_reporting import run_greedy_evidenced_lifecycle
from Greedy.kernel_profile_reconciliation import materialize_runtime_profiles
from Greedy.kernel_route_contracts import (
    GreedyKernelFlowTelemetry,
    GreedyKernelHopTelemetry,
    GreedyKernelMeasuredPairTelemetry,
    GreedyKernelRunSlotResponse,
)
from Greedy.persistence import (
    LEGACY_GREEDY_TRACE_CONTRACT_VERSION,
    build_greedy_trace_events,
    load_greedy_trace,
    persist_greedy_trace,
    project_greedy_controller_output,
    validate_greedy_trace_events,
)
from Greedy.runtime_resources import (
    GreedyControllerResourceDelta,
    GreedyControllerResourceSnapshot,
    controller_resource_delta,
)


ROOT = Path(__file__).resolve().parents[1]
UNIFORM = (0.25, 0.25, 0.25, 0.25)
PROFILE_FINGERPRINT = materialize_runtime_profiles(
    GreedyConfiguration(2, 3, 2), profile_seed=17
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
                pod_name=f"{ownership.stage_name(identity.stage)}-{identity.replica - 1}",
                pod_uid=f"uid-{identity.stage}-{identity.replica}",
                node_name="greedy-worker",
                endpoint=f"http://{ownership.stage_name(identity.stage)}-{identity.replica - 1}",
                phase="Running",
                ready=True,
                labels=ownership.replica_labels(identity.stage),
            )
            for identity in _identities(configuration)
        ),
    )


def _response(request, *, physical_ms=20.0, observation_ms=2.0, pair_ms=5.0):
    flows = []
    for route in request.routes:
        hops = []
        for target in route.hops:
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
                    modeled_processing_latency_ms=physical_ms - 1.0,
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
            request_latency_ms=10.0 + pair_ms,
            callee_elapsed_ms=10.0,
            measured_pair_latency_ms=pair_ms,
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


class _Discovery:
    def __init__(self, value):
        self.value = value

    def wait_for_complete_ready(self, **_kwargs):
        return self.value

    def close(self):
        return None


class _Generator:
    def run_slot(self, request):
        return _response(request)

    def close(self):
        return None


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


def _outcomes(count=1):
    configuration = GreedyConfiguration(2, 3, 2)
    ticks = iter(float(value) for value in range(6 * count))
    controller = GreedyKernelController(
        controller_configuration=GreedyKernelControllerConfiguration(
            configuration=configuration,
            experiment_id=1,
            root_seed=2050,
            profile_seed=17,
            runtime_profile_fingerprint=PROFILE_FINGERPRINT,
            max_iterations=count,
        ),
        discovery=_Discovery(_snapshot(configuration)),
        flow_generator=_Generator(),
        initial_beliefs={identity: UNIFORM for identity in _identities(configuration)},
        clock=lambda: next(ticks),
    )
    results = []
    try:
        for slot_id in range(1, count + 1):
            outcome = controller.run_slot(slot_id, flow_order=(2, 1))
            results.append(
                replace(
                    outcome,
                    control_plane=_control_plane(),
                    controller_resources=_resources(),
                )
            )
    finally:
        controller.close()
    return tuple(results)


def _launch(*, max_iterations=1, csv=0, parity=0):
    return GreedyLaunchConfiguration(
        configuration=GreedyConfiguration(2, 3, 2),
        max_iterations=max_iterations,
        profile_seed=17,
        root_seed=2050,
        rollout_batch_size=1,
        skip_build=True,
        csv=csv,
        parity_replay=parity,
    )


def _lifecycle(*, configuration=None):
    return GreedyLifecycleResult(
        configuration=configuration or GreedyConfiguration(2, 3, 2),
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


def _evidence(outcome, *, csv=0, parity=0):
    selected = outcome if csv else replace(outcome, control_plane=None)
    return build_greedy_slot_evidence(
        selected, parity_replay_enabled=bool(parity)
    )


def _legacy_v1_events(events):
    legacy = deepcopy(tuple(events))
    started = legacy[0]
    old_required = []
    for item in started["matched_comparison"]["required_matches"]:
        if item["name"] != "ready_identity_semantics":
            old_required.append(item)
            continue
        old_required.extend(
            (
                {
                    "name": "admission_capacity_per_replica",
                    "greedy_value": 2,
                    "hybrid_value": 2,
                    "source_location": (
                        "IBG_Hybrid/kernel_profile_expansion.py:587-600"
                    ),
                },
                {
                    "name": "ready_capacity_semantics",
                    "greedy_value": (
                        "ready-and-current-load-plus-one-within-declared-capacity"
                    ),
                    "hybrid_value": (
                        "ready-and-current-load-plus-one-within-declared-capacity"
                    ),
                    "source_location": "IBG_Hybrid/phase0_contract.py:252-289",
                },
            )
        )
    started["matched_comparison"] = {
        "version": LEGACY_GREEDY_HYBRID_MATCHED_COMPARISON_VERSION,
        "required_matches": old_required,
        "intentional_policy_differences": started["matched_comparison"][
            "intentional_policy_differences"
        ],
    }
    started["matched_comparison_version"] = (
        LEGACY_GREEDY_HYBRID_MATCHED_COMPARISON_VERSION
    )
    started["policy_contract_version"] = LEGACY_GREEDY_POLICY_VERSION
    for event in legacy:
        event["trace_contract_version"] = LEGACY_GREEDY_TRACE_CONTRACT_VERSION
        if "configuration" in event:
            configuration = event["configuration"]
            configuration["admission_capacity_per_replica"] = (
                configuration["num_flows"] + configuration["num_replicas"] - 1
            ) // configuration["num_replicas"]
        if event.get("event") == "iteration_completed":
            event["contract_version"] = LEGACY_GREEDY_SLOT_EVIDENCE_VERSION
            event["policy_contract_version"] = LEGACY_GREEDY_POLICY_VERSION
            # A faithful v1 document carries the retired predicted-utility
            # fairness index and no Phase 8.3 domain flag.
            metrics = event["metrics"]
            metrics.pop("fairness_domain_valid", None)
            predicted = [
                value for _flow, value in metrics["predicted_utility_per_flow"]
            ]
            metrics["jain_fairness"] = (
                float(metrics["predicted_aggregate_utility"]) ** 2
                / (len(predicted) * sum(round(value, 3) ** 2 for value in predicted))
            )
    return validate_greedy_trace_events(legacy)


def test_console_golden_structure_is_complete_and_hides_private_state():
    outcome = _outcomes()[0]
    beliefs = format_greedy_replica_beliefs(
        "Initial replica state", outcome.slot.beliefs_before.mapping
    )
    metrics = format_greedy_slot_metrics(outcome.slot, iteration=1)
    assert beliefs.splitlines()[:2] == [
        "Initial replica state",
        "Stage  Replica  Belief",
    ]
    for label in (
        "Outcome mode: physical-only-v1",
        "Predicted utility:",
        "Realized utility:",
        "Physical utility:",
        "Raw end-to-end utility:",
        "End-to-end SLA violations=",
        "end-to-end SLA excess=",
        "fairness=",
        "equilibrium=",
    ):
        assert label in metrics
    assert "hidden" not in (beliefs + metrics).lower()


def test_evidence_default_replay_is_not_performed_and_enabled_replay_is_captured(monkeypatch):
    outcome = _outcomes()[0]
    called = 0

    def forbidden(_outcome):
        nonlocal called
        called += 1
        raise AssertionError("default evidence must not duplicate the solve")

    monkeypatch.setattr("Greedy.evidence.replay_greedy_evidence_slot", forbidden)
    default = _evidence(outcome)
    assert called == 0
    assert default["pure_kernel_replay_requested"] is False
    assert default["pure_kernel_replay_performed"] is False
    assert "pure_kernel_replay_parity" not in default
    monkeypatch.undo()
    enabled = _evidence(outcome, parity=1)
    assert enabled["pure_kernel_replay_requested"] is True
    assert enabled["pure_kernel_replay_performed"] is True
    assert enabled["pure_kernel_replay_parity"] is True


@pytest.mark.parametrize(
    "mutate",
    (
        lambda item: item["placements"][0].__setitem__("objective_value", float("nan")),
        lambda item: item["placements"][1]["loads_before"][0].__setitem__("load", 9),
        lambda item: item["observations"].pop(),
        lambda item: item["metrics"].__setitem__("end_to_end_sla_violations", 2),
        lambda item: item["metrics"].__setitem__("predicted_aggregate_utility", 999.0),
        lambda item: item.__setitem__("hidden_state", 4),
        lambda item: item.__setitem__("pure_kernel_replay_parity", True),
    ),
)
def test_evidence_rejects_nonfinite_incomplete_inconsistent_hidden_or_fabricated_data(mutate):
    evidence = deepcopy(_evidence(_outcomes()[0]))
    mutate(evidence)
    with pytest.raises(ValueError):
        validate_greedy_slot_evidence(evidence)


def test_evidence_preserves_complete_l2_semantics_and_canonical_json():
    evidence = _evidence(_outcomes()[0])
    assert len(evidence["placements"]) == 2
    assert len(evidence["observations"]) == 4
    assert len(evidence["measured_pairs"]) == 2
    assert all(len(item["selected"]) == 2 for item in evidence["placements"])
    assert all(len(item["bypassed_stages"]) == 1 for item in evidence["placements"])
    payload = canonical_greedy_evidence_json(evidence)
    assert json.loads(payload) == evidence
    assert "hidden_state" not in payload
    assert "observation_seed" not in payload


def test_jsonl_lifecycle_is_atomic_round_trip_complete_and_provenanced(tmp_path):
    evidence = (_evidence(_outcomes()[0]),)
    result = persist_greedy_trace(
        evidence,
        launch=_launch(),
        lifecycle=_lifecycle(),
        trace_dir=tmp_path,
        recorded_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        run_id="fixture-run",
    )
    assert result.path.name == "greedy-experiment-fixture-run.jsonl"
    loaded = load_greedy_trace(result.path)
    assert [item["event"] for item in loaded] == [
        "run_started", "iteration_completed", "run_completed"
    ]
    started = loaded[0]
    assert started["controller_jobs_created"] == 1
    assert len(started["matched_comparison"]["required_matches"]) > 40
    assert len(started["matched_comparison"]["intentional_policy_differences"]) == 11
    assert len(started["matched_comparison"]["unresolved_mismatches"]) == 1
    assert started["pod_resources"]["controller"]["requests"] == {
        "cpu": "2", "memory": "256Mi"
    }
    assert started["images"]["service"]["id"] == "a" * 64
    assert started["worker_allocatable"] == {
        "cpu_millicores": 8000, "memory_mib": 16384
    }
    assert "hidden_state" not in result.path.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        persist_greedy_trace(
            evidence,
            launch=_launch(),
            lifecycle=_lifecycle(),
            trace_dir=tmp_path,
            recorded_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            run_id="fixture-run",
        )
    assert not tuple(tmp_path.glob("*.tmp"))


def test_v1_trace_remains_readable_v2_omits_capacity_and_csv_refuses_mixing(tmp_path):
    outcome = _outcomes()[0]
    v2_evidence = _evidence(outcome, csv=1)
    assert "admission_capacity_per_replica" not in v2_evidence["configuration"]
    v2_events = build_greedy_trace_events(
        (v2_evidence,),
        launch=_launch(csv=1),
        lifecycle=_lifecycle(),
        run_id="v2-fixture",
        recorded_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )
    legacy_events = _legacy_v1_events(v2_events)
    assert legacy_events[0]["policy_contract_version"] == (
        LEGACY_GREEDY_POLICY_VERSION
    )
    assert legacy_events[1]["configuration"][
        "admission_capacity_per_replica"
    ] == 1

    legacy_path = tmp_path / "legacy-v1.jsonl"
    legacy_path.write_text(
        "".join(
            json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
            for event in legacy_events
        ),
        encoding="utf-8",
    )
    assert load_greedy_trace(legacy_path) == legacy_events
    csv_dir = tmp_path / "csv"
    export_greedy_csv(legacy_path, csv_dir)

    v2_trace = persist_greedy_trace(
        (v2_evidence,),
        launch=_launch(csv=1),
        lifecycle=_lifecycle(),
        trace_dir=tmp_path / "v2",
        run_id="v2-fixture",
        recorded_at=datetime(2026, 8, 27, 0, 0, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(ValueError, match="refuses mixed"):
        export_greedy_csv(v2_trace.path, csv_dir)


def test_invalid_trace_is_rejected_before_directory_or_partial_file_creation(tmp_path):
    evidence = deepcopy(_evidence(_outcomes()[0]))
    evidence["runtime_profile_fingerprint"] = "drift"
    trace_dir = tmp_path / "runs"
    with pytest.raises(ValueError):
        persist_greedy_trace(
            (evidence,), launch=_launch(), lifecycle=_lifecycle(), trace_dir=trace_dir
        )
    assert not trace_dir.exists()


def test_trace_rejects_mixed_replay_schema_seed_and_belief_continuity():
    outcomes = _outcomes(2)
    evidence = tuple(_evidence(item) for item in outcomes)
    events = list(
        build_greedy_trace_events(
            evidence,
            launch=_launch(max_iterations=2),
            lifecycle=_lifecycle(),
            run_id="two-slot",
            recorded_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        )
    )
    for mutation in (
        lambda value: value[1].__setitem__("trace_contract_version", "old"),
        lambda value: value[2].__setitem__("root_seed", 99),
        lambda value: value[2].__setitem__("beliefs_before", value[1]["beliefs_before"]),
        lambda value: value[0]["matched_comparison"].__setitem__("version", "drift"),
    ):
        changed = deepcopy(events)
        mutation(changed)
        from Greedy.persistence import validate_greedy_trace_events

        with pytest.raises(ValueError):
            validate_greedy_trace_events(changed)


def test_csv_export_is_opt_in_atomic_wide_aligned_and_duplicate_safe(tmp_path):
    csv_dir = tmp_path / "figures" / "Greedy"
    first = persist_greedy_trace(
        (_evidence(_outcomes()[0], csv=1),),
        launch=_launch(csv=1), lifecycle=_lifecycle(), trace_dir=tmp_path / "run1",
        run_id="short", recorded_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )
    paths = export_greedy_csv(first.path, csv_dir)
    assert set(GREEDY_CSV_FILENAMES).issubset({path.name for path in paths})
    assert (csv_dir / "footprint" / "belief_exchange_total_bytes.csv").exists()
    second_outcomes = _outcomes(2)
    second = persist_greedy_trace(
        tuple(_evidence(item, csv=1) for item in second_outcomes),
        launch=_launch(max_iterations=2, csv=1), lifecycle=_lifecycle(),
        trace_dir=tmp_path / "run2", run_id="long",
        recorded_at=datetime(2026, 8, 26, 0, 0, 1, tzinfo=timezone.utc),
    )
    export_greedy_csv(second.path, csv_dir)
    rows = (csv_dir / "time.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 3
    assert rows[2].split(",")[0] == ""
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in csv_dir.rglob("*.csv")
    }
    with pytest.raises(ValueError, match="already exists"):
        export_greedy_csv(second.path, csv_dir)
    after = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in csv_dir.rglob("*.csv")
    }
    assert before == after
    assert not tuple(csv_dir.rglob("*.tmp"))


def test_csv_zero_trace_refuses_export_without_creating_reports(tmp_path):
    trace = persist_greedy_trace(
        (_evidence(_outcomes()[0]),), launch=_launch(), lifecycle=_lifecycle(),
        trace_dir=tmp_path / "runs", run_id="json-only",
        recorded_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )
    output = tmp_path / "figures"
    with pytest.raises(ValueError, match="--csv 1"):
        export_greedy_csv(trace.path, output)
    assert not output.exists()


def test_controller_output_projection_hides_machine_line_and_rejects_bad_evidence():
    evidence = _evidence(_outcomes()[0])
    emitted = []
    output = "human line\n" + GREEDY_SLOT_EVIDENCE_PREFIX + canonical_greedy_evidence_json(evidence)
    assert project_greedy_controller_output(output, emit=emitted.append) == (evidence,)
    assert emitted == ["human line"]
    with pytest.raises((ValueError, json.JSONDecodeError)):
        project_greedy_controller_output(
            GREEDY_SLOT_EVIDENCE_PREFIX + "{}", emit=lambda _line: None
        )


def test_reporting_wrapper_persists_after_lifecycle_and_keeps_csv_off_by_default(
    monkeypatch, tmp_path
):
    evidence = _evidence(_outcomes()[0])
    lifecycle = _lifecycle()
    progress = []
    monkeypatch.setattr(
        "Greedy.kernel_reporting.run_greedy_lifecycle",
        lambda _launch, **_kwargs: lifecycle,
    )
    reported = run_greedy_evidenced_lifecycle(
        _launch(),
        execute=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("injected controller logs avoid external commands")
        ),
        emit=progress.append,
        controller_log_output=lambda: (
            "human controller output\n"
            + GREEDY_SLOT_EVIDENCE_PREFIX
            + canonical_greedy_evidence_json(evidence)
        ),
        trace_dir=tmp_path / "runs",
        csv_output_dir=tmp_path / "figures" / "Greedy",
    )
    assert reported.lifecycle == lifecycle
    assert reported.trace.path.exists()
    assert reported.csv_paths == ()
    assert not (tmp_path / "figures").exists()
    assert progress[0] == "human controller output"
    assert any(line.startswith("Detailed Greedy JSONL trace:") for line in progress)


def test_control_plane_and_resource_measurements_use_exact_monotonic_deltas():
    ticks = iter((0, 1_000_000, 2_000_000, 4_000_000, 7_000_000, 8_000_000))
    meter = GreedyControlPlaneMeter(wall_clock_ns=lambda: next(ticks))
    meter.begin_slot()
    meter.begin_discovery()
    meter.record_exchange(
        request_field="kubernetes_discovery_tx",
        response_field="kubernetes_discovery_rx",
        request_payload_bytes=7,
        response_payload_bytes=31,
    )
    meter.end_discovery()
    meter.mark_route_dispatch()
    meter.record_exchange(
        request_field="route_command_tx",
        response_field="selected_telemetry_rx",
        request_payload_bytes=101,
        response_payload_bytes=211,
    )
    meter.mark_telemetry_received()
    snapshot = meter.finish_slot()
    assert snapshot["timing_ms"] == {
        "discovery": 1.0,
        "admission": 4.0,
        "feedback": 1.0,
        "active": 5.0,
        "data_plane_wait": 3.0,
    }
    assert snapshot["payload_bytes"]["total"] == 350
    assert snapshot["messages"]["total"] == 4
    delta = controller_resource_delta(
        GreedyControllerResourceSnapshot(1.0, 10, 2, 20),
        GreedyControllerResourceSnapshot(1.25, 12, 5, 29),
    )
    assert delta == GreedyControllerResourceDelta(0.25, 12, 3, 9)


def test_controller_integrates_optional_footprint_and_always_on_resource_samples():
    configuration = GreedyConfiguration(2, 3, 2)
    meter_ticks = iter((0, 1_000_000, 2_000_000, 4_000_000, 7_000_000, 8_000_000))
    meter = GreedyControlPlaneMeter(wall_clock_ns=lambda: next(meter_ticks))

    class MeteredDiscovery(_Discovery):
        def wait_for_complete_ready(self, **_kwargs):
            meter.record_exchange(
                request_field="kubernetes_discovery_tx",
                response_field="kubernetes_discovery_rx",
                request_payload_bytes=7,
                response_payload_bytes=31,
            )
            return self.value

    class MeteredGenerator(_Generator):
        def run_slot(self, request):
            meter.mark_route_dispatch()
            response = _response(request)
            meter.mark_telemetry_received()
            meter.record_exchange(
                request_field="route_command_tx",
                response_field="selected_telemetry_rx",
                request_payload_bytes=101,
                response_payload_bytes=211,
            )
            return response

    samples = iter(
        (
            GreedyControllerResourceSnapshot(1.0, 10, 2, 20),
            GreedyControllerResourceSnapshot(1.25, 12, 5, 29),
        )
    )
    slot_ticks = iter(float(value) for value in range(6))
    controller = GreedyKernelController(
        controller_configuration=GreedyKernelControllerConfiguration(
            configuration=configuration,
            experiment_id=1,
            root_seed=2050,
            profile_seed=17,
            runtime_profile_fingerprint=PROFILE_FINGERPRINT,
            max_iterations=1,
            control_plane_footprint_enabled=True,
        ),
        discovery=MeteredDiscovery(_snapshot(configuration)),
        flow_generator=MeteredGenerator(),
        initial_beliefs={identity: UNIFORM for identity in _identities(configuration)},
        clock=lambda: next(slot_ticks),
        control_plane_meter=meter,
        resource_sampler=lambda: next(samples),
    )
    try:
        outcome = controller.run_slot(1, flow_order=(2, 1))
    finally:
        controller.close()
    assert outcome.control_plane["payload_bytes"]["total"] == 350
    assert outcome.control_plane["messages"]["total"] == 4
    assert outcome.controller_resources == GreedyControllerResourceDelta(
        0.25, 12, 3, 9
    )


def test_launch_flags_reach_controller_without_result_volume_and_cli_has_no_runs():
    launch = _launch(csv=1, parity=1)
    controller = launch.deployment.controller_document.controller
    assert controller.parity_replay_enabled is True
    assert controller.control_plane_footprint_enabled is True
    job = render_controller_job(
        launch.deployment,
        GreedyServingReadiness(
            configuration=launch.configuration,
            ready_identities=_identities(launch.configuration),
            flow_generator_ready=True,
        ),
    )
    volume_names = {item["name"] for item in job["spec"]["template"]["spec"]["volumes"]}
    assert volume_names == {"controller-inputs"}
    source = (ROOT / "scripts" / "run_greedy_kernel.py").read_text(encoding="utf-8")
    for forbidden in ("--runs", "--policy", "--mc-workers", "ProcessPool"):
        assert forbidden not in source


def test_phase6_audit_is_exact_classified_and_new_sources_exclude_hybrid_policy():
    assert GREEDY_PHASE6_HYBRID_AUDIT_HEAD == "8e5114e6e9101057da48255962afa65900c6c8d0"
    assert len(GREEDY_PHASE6_HYBRID_SOURCE_AUDIT) == 6
    assert {item.disposition for item in GREEDY_PHASE6_HYBRID_SOURCE_AUDIT} <= {
        "reuse", "adapt", "exclude"
    }
    assert all(":" in item.source_location and len(item.git_blob) == 40 for item in GREEDY_PHASE6_HYBRID_SOURCE_AUDIT)
    for name in (
        "console_output.py", "control_plane_footprint.py", "csv_export.py",
        "evidence.py", "evidence_replay.py", "kernel_reporting.py",
        "persistence.py", "runtime_resources.py",
    ):
        source = (ROOT / "Greedy" / name).read_text(encoding="utf-8")
        assert "IBG_Hybrid" not in source
        assert "ProcessPool" not in source


def test_phase6_imports_are_silent_and_file_free(tmp_path):
    modules = (
        "Greedy.console_output", "Greedy.control_plane_footprint",
        "Greedy.csv_export", "Greedy.evidence", "Greedy.evidence_replay",
        "Greedy.kernel_reporting", "Greedy.persistence", "Greedy.runtime_resources",
    )
    command = "import importlib; " + "; ".join(
        f"importlib.import_module({module!r})" for module in modules
    )
    completed = subprocess.run(
        [sys.executable, "-c", command], cwd=tmp_path, check=True,
        text=True, capture_output=True,
        env={"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.stdout == completed.stderr == ""
    assert list(tmp_path.iterdir()) == []
