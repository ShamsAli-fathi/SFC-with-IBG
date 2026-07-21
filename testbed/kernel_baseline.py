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


def _normalized_endpoint(value):
    if not isinstance(value, str) or not value:
        return None
    return value.rstrip("/")


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
    pairwise_link_checks = []
    pairwise_link_values = []
    ingress_overhead_values = []
    pairwise_schema_seen = False
    transport_schemas = set()
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
        flows = traffic.get("flows", [])
        pairwise_schema_declared = any(
            "links" in flow
            or "ingress_request_latency_ms" in flow
            or "ingress_overhead_ms" in flow
            for flow in flows
        )
        pairwise_schema_seen = pairwise_schema_seen or pairwise_schema_declared
        transport_schemas.add(
            "pairwise" if pairwise_schema_declared else "historical"
        )
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
            observation_jitter = float(hop.get("observation_jitter_ms", 0.0))
            signal = float(hop["signal_latency_ms"])
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
                observation_jitter >= 0
                and abs(signal - processing - observation_jitter) <= 1e-6
                and abs(float(observation["signal"]) - signal) <= 1e-9
                and abs(
                    float(observation.get("observation_jitter_ms", 0.0))
                    - observation_jitter
                )
                <= 1e-9
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
                and (
                    pairwise_schema_declared
                    or abs(
                        transport - max(0.0, request - processing)
                    ) <= 1e-9
                )
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

        if pairwise_schema_declared:
            expected_links = max(0, configuration.get("stages", 0) - 1)
            link_metrics = summary.get("metrics", {}).get(
                "link_latency_ms_per_flow", {}
            )
            for flow in flows:
                flow_id = int(flow.get("flow_id", -1))
                flow_hops = {hop["stage"]: hop for hop in flow.get("hops", [])}
                links = flow.get("links", [])
                pairwise_link_checks.append("links" in flow)
                pairwise_link_checks.append(len(links) == expected_links)
                ingress_request = float(
                    flow.get("ingress_request_latency_ms", -1.0)
                )
                ingress = float(flow.get("ingress_overhead_ms", -1.0))
                pairwise_link_checks.append(
                    ingress_request >= 0 and ingress >= 0
                )
                if ingress >= 0:
                    ingress_overhead_values.append(ingress)
                observed_stage_pairs = set()
                link_cost_sum = 0.0
                for link in links:
                    source_stage = int(link["source_stage"])
                    target_stage = int(link["target_stage"])
                    request_latency = float(link["request_latency_ms"])
                    callee_elapsed = float(link["callee_elapsed_ms"])
                    cost = float(link["link_cost_ms"])
                    link_cost_sum += cost
                    observed_stage_pairs.add((source_stage, target_stage))
                    source_hop = flow_hops.get(source_stage, {})
                    target_hop = flow_hops.get(target_stage, {})
                    source_placement = placements.get(
                        (source_stage, flow_id), {}
                    )
                    target_placement = placements.get(
                        (target_stage, flow_id), {}
                    )
                    pairwise_link_checks.append(
                        target_stage == source_stage + 1
                        and int(link["slot_id"]) == int(traffic["slot_id"])
                        and int(link["flow_id"]) == int(flow["flow_id"])
                        and link["source_replica_id"]
                        == source_hop.get("replica_id")
                        == source_placement.get("replica_id")
                        and link.get("source_pod_name")
                        == source_hop.get("pod_name")
                        == source_placement.get("pod_name")
                        and link["target_replica_id"]
                        == target_hop.get("replica_id")
                        == target_placement.get("replica_id")
                        and link.get("target_pod_name")
                        == target_hop.get("pod_name")
                        == target_placement.get("pod_name")
                        and _normalized_endpoint(link.get("target_endpoint"))
                        == _normalized_endpoint(target_hop.get("endpoint"))
                        == _normalized_endpoint(
                            target_placement.get("endpoint")
                        )
                        and request_latency >= 0
                        and callee_elapsed >= 0
                        and cost >= 0
                        and abs(
                            cost
                            - max(0.0, request_latency - callee_elapsed)
                        )
                        <= 1e-9
                    )
                    pairwise_link_values.append(cost)
                pairwise_link_checks.append(
                    observed_stage_pairs
                    == {
                        (stage, stage + 1)
                        for stage in range(1, expected_links + 1)
                    }
                )
                link_metric = link_metrics.get(str(flow_id))
                pairwise_link_checks.append(
                    link_metric is not None
                    and abs(link_cost_sum - float(link_metric)) <= 1e-9
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
        "transport_schema_consistent": len(transport_schemas) == 1,
    }
    if pairwise_schema_seen:
        checks["pairwise_link_cost_complete_and_correlated"] = bool(
            pairwise_link_checks
        ) and all(pairwise_link_checks)
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
            "transport_overhead": (
                "non-negative compatibility telemetry; distribution reported "
                "without an upper gate"
            ),
        },
        "processing_latency_ms": _distribution(processing_values),
        "server_overshoot_ms": _distribution(overshoot_values),
        "request_latency_ms": _distribution(request_values),
        "transport_overhead_ms": _distribution(transport_values),
        "pairwise_link_cost_ms": _distribution(pairwise_link_values),
        "ingress_overhead_ms": _distribution(ingress_overhead_values),
        "state_load_groups": group_statistics,
        "congestion_comparisons": congestion_comparisons,
    }
