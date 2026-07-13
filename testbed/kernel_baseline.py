import math

from IBG.datapath import KERNEL_DATAPATH_MODE


SUPPORTED_CONFIGURATION = {
    "stages": 3,
    "replicas_per_stage": 5,
    "flows": 3,
}
KERNEL_OVERSHOOT_ABSOLUTE_MS = 10.0
KERNEL_OVERSHOOT_RELATIVE = 0.10
MINIMUM_CLASSIFICATION_ACCURACY = 0.80
MINIMUM_OVERSHOOT_PASS_RATE = 0.95


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _distribution(values):
    values = [float(value) for value in values]
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "max": None}
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": max(values),
    }


def build_kernel_baseline_report(events, profiles):
    run_started = [event for event in events if event.get("event") == "run_started"]
    iterations = [
        event for event in events if event.get("event") == "iteration_completed"
    ]
    run_completed = [
        event for event in events if event.get("event") == "run_completed"
    ]
    if len(run_started) != 1 or not iterations or len(run_completed) != 1:
        raise ValueError("expected one complete experiment trace")

    started = run_started[0]
    completed = run_completed[0]
    configuration = started.get("configuration", {})
    runtime_image = started.get("runtime_image")
    mode_checks = []
    correlation_checks = []
    signal_checks = []
    likelihood_checks = []
    transport_checks = []
    overshoot_checks = []
    processing_values = []
    overshoot_values = []
    transport_values = []
    request_values = []
    classified = 0
    total_hops = 0
    groups = {}

    for event in iterations:
        summary = event["summary"]
        traffic = summary.get("traffic") or {}
        hops = [
            hop
            for flow in traffic.get("flows", [])
            for hop in flow.get("hops", [])
        ]
        placements = {
            (item["stage"], item["flow_id"]): item
            for item in summary["placements"]
        }
        observations = {
            (item["stage"], item["flow_id"]): item
            for item in summary["observations"]
        }
        hop_index = {(hop["stage"], hop["flow_id"]): hop for hop in hops}
        selected_keys = set(placements)
        correlation_checks.append(
            selected_keys == set(observations) == set(hop_index)
            and len(selected_keys)
            == configuration.get("stages", 0) * configuration.get("flows", 0)
        )
        mode_checks.extend(
            [
                event.get("datapath_mode") == KERNEL_DATAPATH_MODE,
                summary.get("datapath_mode") == KERNEL_DATAPATH_MODE,
                traffic.get("datapath_mode") == KERNEL_DATAPATH_MODE,
                all(
                    hop.get("datapath_mode") == KERNEL_DATAPATH_MODE
                    for hop in hops
                ),
            ]
        )

        for key, hop in hop_index.items():
            observation = observations[key]
            placement = placements[key]
            profile = profiles[(hop["stage"], hop["replica_id"])]
            modeled = float(hop["modeled_processing_latency_ms"])
            processing = float(hop["processing_latency_ms"])
            request = float(hop["request_latency_ms"])
            transport = float(hop["transport_overhead_ms"])
            overshoot = processing - modeled
            tolerance = max(
                KERNEL_OVERSHOOT_ABSOLUTE_MS,
                KERNEL_OVERSHOOT_RELATIVE * modeled,
            )
            correlation_checks.append(
                hop["replica_id"] == placement["replica_id"]
                and hop["assigned_load"] == observation["congestion"]
            )
            signal_checks.append(
                abs(float(observation["signal"]) - processing) <= 1e-9
                and abs(float(hop["signal_latency_ms"]) - processing) <= 1e-9
            )
            likelihood_checks.append(
                all(
                    abs(float(left) - float(right)) <= 1e-9
                    for left, right in zip(
                        observation["likelihood"],
                        hop["state_likelihood"],
                    )
                )
            )
            transport_checks.append(
                transport >= 0
                and abs(transport - max(0.0, request - processing)) <= 1e-9
            )
            overshoot_checks.append(overshoot <= tolerance)
            processing_values.append(processing)
            overshoot_values.append(overshoot)
            transport_values.append(transport)
            request_values.append(request)
            total_hops += 1
            classified += int(hop["state_estimate"] == profile.state)
            groups.setdefault((profile.state, hop["assigned_load"]), []).append(
                processing
            )

    group_statistics = [
        {
            "state": state,
            "assigned_load": load,
            "count": len(values),
            "mean_processing_latency_ms": sum(values) / len(values),
        }
        for (state, load), values in sorted(groups.items())
    ]
    load_one_means = {
        item["state"]: item["mean_processing_latency_ms"]
        for item in group_statistics
        if item["assigned_load"] == 1
    }
    state_ordering = set(load_one_means) == {1, 2, 3, 4} and all(
        load_one_means[state] > load_one_means[state + 1]
        for state in (1, 2, 3)
    )
    congestion_comparisons = []
    for state in range(1, 5):
        state_groups = [
            item for item in group_statistics if item["state"] == state
        ]
        for left, right in zip(state_groups, state_groups[1:]):
            congestion_comparisons.append(
                {
                    "state": state,
                    "lower_load": left["assigned_load"],
                    "higher_load": right["assigned_load"],
                    "nondecreasing": (
                        left["mean_processing_latency_ms"]
                        <= right["mean_processing_latency_ms"]
                    ),
                }
            )
    classification_accuracy = classified / total_hops if total_hops else 0.0
    overshoot_pass_rate = (
        sum(overshoot_checks) / len(overshoot_checks)
        if overshoot_checks
        else 0.0
    )
    checks = {
        "supported_configuration": configuration == SUPPORTED_CONFIGURATION,
        "kernel_mode_complete": all(mode_checks),
        "runtime_image_recorded": bool(runtime_image and runtime_image != "unknown"),
        "environment_recorded": bool(started.get("environment")),
        "selected_only_correlation": all(correlation_checks),
        "signal_is_selected_processing_latency": all(signal_checks),
        "likelihood_vectors_preserved": all(likelihood_checks),
        "transport_overhead_non_negative_and_correlated": all(transport_checks),
        "server_overshoot_within_tolerance": (
            overshoot_pass_rate >= MINIMUM_OVERSHOOT_PASS_RATE
        ),
        "load_one_state_ordering": state_ordering,
        "congestion_response": bool(congestion_comparisons)
        and all(item["nondecreasing"] for item in congestion_comparisons),
        "classification_accuracy": (
            classification_accuracy >= MINIMUM_CLASSIFICATION_ACCURACY
        ),
        "equilibrium_reached": completed.get("reached_equilibrium") is True,
    }
    return {
        "gate_passed": all(checks.values()),
        "checks": checks,
        "configuration": configuration,
        "datapath_mode": started.get("datapath_mode"),
        "runtime_image": runtime_image,
        "environment": started.get("environment", {}),
        "iterations": len(iterations),
        "selected_hops": total_hops,
        "classification_accuracy": classification_accuracy,
        "server_overshoot_pass_rate": overshoot_pass_rate,
        "tolerance": {
            "server_overshoot_ms": (
                "at least 95% of hops within max(10 ms, 10% modeled "
                "processing latency)"
            ),
            "transport_overhead": "non-negative; distribution reported without an upper gate",
        },
        "processing_latency_ms": _distribution(processing_values),
        "server_overshoot_ms": _distribution(overshoot_values),
        "request_latency_ms": _distribution(request_values),
        "transport_overhead_ms": _distribution(transport_values),
        "state_load_groups": group_statistics,
        "congestion_comparisons": congestion_comparisons,
    }
