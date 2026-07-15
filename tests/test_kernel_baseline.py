import copy
from types import SimpleNamespace

from testbed.kernel_baseline import build_kernel_baseline_report


def complete_trace():
    samples = {
        (1, 1): (1, 1, 41.0),
        (1, 2): (2, 1, 29.0),
        (1, 3): (3, 1, 19.0),
        (2, 1): (4, 1, 11.0),
        (2, 2): (4, 2, 13.0),
        (2, 3): (4, 3, 15.0),
        (3, 1): (3, 2, 24.0),
        (3, 2): (4, 2, 14.0),
        (3, 3): (4, 3, 16.0),
    }
    placements = []
    observations = []
    flows = []
    profiles = {}
    for flow_id in range(1, 4):
        hops = []
        for stage in range(1, 4):
            state, load, processing = samples[(stage, flow_id)]
            profiles[(stage, flow_id)] = SimpleNamespace(state=state)
            placements.append(
                {
                    "stage": stage,
                    "flow_id": flow_id,
                    "replica_id": flow_id,
                    "pod_name": f"stage-{stage}-pod",
                    "endpoint": f"http://stage-{stage}/",
                }
            )
            likelihood = [0.0, 0.0, 0.0, 0.0]
            likelihood[state - 1] = 1.0
            observations.append(
                {
                    "stage": stage,
                    "flow_id": flow_id,
                    "replica_id": flow_id,
                    "congestion": load,
                    "signal": processing,
                    "likelihood": likelihood,
                }
            )
            hops.append(
                {
                    "datapath_mode": "kernel",
                    "slot_id": 1,
                    "flow_id": flow_id,
                    "stage": stage,
                    "replica_id": flow_id,
                    "pod_name": f"stage-{stage}-pod",
                    "endpoint": f"http://stage-{stage}",
                    "assigned_load": load,
                    "modeled_processing_latency_ms": processing - 1.0,
                    "processing_latency_ms": processing,
                    "request_latency_ms": processing + 2.0,
                    "transport_overhead_ms": 2.0,
                    "signal_latency_ms": processing,
                    "state_estimate": state,
                    "state_likelihood": likelihood,
                }
            )
        flows.append({"flow_id": flow_id, "hops": hops})
    metadata = {
        "backend": "kubernetes",
        "datapath_mode": "kernel",
        "runtime_image": "ibg-testbed:kernel-phase3",
        "environment": {"kubernetes_server": "v1.35.0"},
        "seed": 2050,
        "configuration": {"stages": 3, "replicas_per_stage": 5, "flows": 3},
    }
    return (
        [
            {"event": "run_started", **metadata},
            {
                "event": "iteration_completed",
                **metadata,
                "summary": {
                    "datapath_mode": "kernel",
                    "placements": placements,
                    "observations": observations,
                    "traffic": {
                        "datapath_mode": "kernel",
                        "slot_id": 1,
                        "elapsed_ms": 100.0,
                        "flows": flows,
                    },
                },
            },
            {"event": "run_completed", **metadata, "reached_equilibrium": True},
        ],
        profiles,
    )


def add_pairwise_telemetry(events, iteration_index=1):
    summary = events[iteration_index]["summary"]
    traffic = summary["traffic"]
    summary["metrics"] = {"link_latency_ms_per_flow": {}}
    for flow in traffic["flows"]:
        flow["ingress_request_latency_ms"] = 120.0
        flow["ingress_overhead_ms"] = 0.5
        flow["links"] = []
        for source, target in zip(flow["hops"], flow["hops"][1:]):
            flow["links"].append(
                {
                    "slot_id": traffic["slot_id"],
                    "flow_id": flow["flow_id"],
                    "source_stage": source["stage"],
                    "source_replica_id": source["replica_id"],
                    "source_pod_name": f"stage-{source['stage']}-pod",
                    "target_stage": target["stage"],
                    "target_replica_id": target["replica_id"],
                    "target_pod_name": f"stage-{target['stage']}-pod",
                    "target_endpoint": f"http://stage-{target['stage']}/",
                    "request_latency_ms": 20.0,
                    "callee_elapsed_ms": 19.25,
                    "link_cost_ms": 0.75,
                }
            )
        summary["metrics"]["link_latency_ms_per_flow"][str(flow["flow_id"])] = (
            sum(link["link_cost_ms"] for link in flow["links"])
        )


def test_kernel_baseline_accepts_complete_selected_only_trace():
    events, profiles = complete_trace()

    report = build_kernel_baseline_report(events, profiles)

    assert report["gate_passed"] is True
    assert report["selected_hops"] == 9
    assert report["classification_accuracy"] == 1.0
    assert report["server_overshoot_pass_rate"] == 1.0
    assert report["checks"]["load_one_state_ordering"] is True
    assert report["checks"]["congestion_response"] is True


def test_kernel_baseline_rejects_transport_or_unselected_observation_drift():
    events, profiles = complete_trace()
    iteration = events[1]
    iteration["summary"]["traffic"]["flows"][0]["hops"][0][
        "transport_overhead_ms"
    ] = -1.0
    iteration["summary"]["observations"].append(
        {
            "stage": 4,
            "flow_id": 1,
            "replica_id": 1,
            "congestion": 1,
            "signal": 10.0,
            "likelihood": [0.0, 0.0, 0.0, 1.0],
        }
    )

    report = build_kernel_baseline_report(events, profiles)

    assert report["gate_passed"] is False
    assert report["checks"]["selected_only_correlation"] is False
    assert (
        report["checks"]["transport_overhead_non_negative_and_correlated"]
        is False
    )


def test_kernel_baseline_accepts_pairwise_links_and_separate_ingress():
    events, profiles = complete_trace()
    add_pairwise_telemetry(events)

    report = build_kernel_baseline_report(events, profiles)

    assert report["gate_passed"] is True
    assert report["pairwise_link_cost_ms"]["count"] == 6
    assert report["ingress_overhead_ms"]["count"] == 3
    assert (
        report["checks"]["pairwise_link_cost_complete_and_correlated"]
        is True
    )


def test_kernel_baseline_rejects_pairwise_link_cost_drift():
    events, profiles = complete_trace()
    add_pairwise_telemetry(events)
    events[1]["summary"]["traffic"]["flows"][0]["links"][0][
        "link_cost_ms"
    ] = 2.0

    report = build_kernel_baseline_report(events, profiles)

    assert report["gate_passed"] is False
    assert (
        report["checks"]["pairwise_link_cost_complete_and_correlated"]
        is False
    )


def test_kernel_baseline_rejects_pairwise_link_metric_sum_drift():
    events, profiles = complete_trace()
    add_pairwise_telemetry(events)
    events[1]["summary"]["metrics"]["link_latency_ms_per_flow"]["1"] = 0.0

    report = build_kernel_baseline_report(events, profiles)

    assert report["gate_passed"] is False
    assert (
        report["checks"]["pairwise_link_cost_complete_and_correlated"]
        is False
    )


def test_kernel_baseline_rejects_pairwise_pod_or_endpoint_drift():
    for field in ("source_pod_name", "target_pod_name", "target_endpoint"):
        events, profiles = complete_trace()
        add_pairwise_telemetry(events)
        events[1]["summary"]["traffic"]["flows"][0]["links"][0][
            field
        ] = "wrong"

        report = build_kernel_baseline_report(events, profiles)

        assert report["gate_passed"] is False
        assert (
            report["checks"]["pairwise_link_cost_complete_and_correlated"]
            is False
        )


def test_kernel_baseline_rejects_mixed_transport_schemas():
    events, profiles = complete_trace()
    events.insert(2, copy.deepcopy(events[1]))
    add_pairwise_telemetry(events, iteration_index=2)

    report = build_kernel_baseline_report(events, profiles)

    assert report["gate_passed"] is False
    assert report["checks"]["transport_schema_consistent"] is False
