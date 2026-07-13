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
