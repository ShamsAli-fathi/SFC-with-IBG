"""Canonical validated evidence for one committed Greedy Kernel slot."""

from __future__ import annotations

from dataclasses import asdict
import json
from math import isfinite
from typing import Mapping

from .contracts import (
    GREEDY_POLICY_VERSION,
    LEGACY_GREEDY_POLICY_VERSION,
    ReplicaIdentity,
)
from .control_plane_footprint import validate_greedy_control_plane_snapshot
from .evidence_replay import replay_greedy_evidence_slot
from .kernel_contracts import GreedyKernelControllerSlotResult
from .metrics import clamped_end_to_end_fairness
from .runtime_resources import validate_controller_resource_mapping
from .simulation import GREEDY_FLOW_ORDER_SEED_SCHEME
from .slot_contracts import (
    GREEDY_EXPLICIT_FLOW_ORDER_SCHEME,
    GREEDY_SLOT_CONTRACT_VERSION,
)


GREEDY_SLOT_EVIDENCE_PREFIX = "GREEDY_SLOT_EVIDENCE="
LEGACY_GREEDY_SLOT_EVIDENCE_VERSION = "greedy-kernel-slot-evidence-v1"
# v1 and v2 both scored Jain over the link-free predicted per-flow utility.
# v3 scores the paper end-to-end series with the zero floor and records
# ``fairness_domain_valid``.  Both older generations stay readable verbatim.
PREDICTED_FAIRNESS_GREEDY_SLOT_EVIDENCE_VERSION = "greedy-kernel-slot-evidence-v2"
GREEDY_SLOT_EVIDENCE_VERSION = "greedy-kernel-slot-evidence-v3"
# Four independently rounded three-decimal posterior entries can differ from
# unit mass by at most 4 * 0.0005 in a single slot.  The learner never
# renormalizes, and each slot re-rounds a retained belief
# (``GREEDY_BELIEF_RETENTION`` 0.8), so that per-slot error accumulates
# geometrically toward 4 * 0.0005 / (1 - 0.8) = 0.01 across a long run.  The
# former single-pass bound rejected legitimate frozen learner output from slot
# 12 onward.  Expected utility already divides by the belief sum, so this drift
# never reaches placement, learning, utility, SLA, or equilibrium.  Preserve
# those learner outputs verbatim while still rejecting malformed vectors.
GREEDY_ROUNDED_BELIEF_SUM_TOLERANCE = 0.0100001


def _identity(identity: ReplicaIdentity) -> dict[str, int]:
    return {"stage": identity.stage, "replica": identity.replica}


def _loads(entries) -> list[dict[str, int]]:
    return [
        {"stage": identity.stage, "replica": identity.replica, "load": load}
        for identity, load in entries
    ]


def _beliefs(snapshot) -> dict[str, list[float]]:
    return {
        f"{identity.stage}:{identity.replica}": list(belief)
        for identity, belief in snapshot.entries
    }


def _finite_tree(value: object, path: str = "evidence") -> None:
    if isinstance(value, float) and not isfinite(value):
        raise ValueError(f"{path} contains a non-finite number")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _finite_tree(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _finite_tree(item, f"{path}[{index}]")


def build_greedy_slot_evidence(
    outcome: GreedyKernelControllerSlotResult,
    *,
    parity_replay_enabled: bool,
) -> dict[str, object]:
    if not isinstance(outcome, GreedyKernelControllerSlotResult):
        raise TypeError("outcome must be GreedyKernelControllerSlotResult")
    if not isinstance(parity_replay_enabled, bool):
        raise TypeError("parity_replay_enabled must be boolean")
    slot = outcome.slot
    observations = []
    for item in slot.observations:
        provenance = getattr(item, "provenance", None)
        observations.append(
            {
                "flow_id": item.flow_id,
                **_identity(item.identity),
                "assigned_load": item.assigned_load,
                "physical_processing_latency_ms": (
                    item.physical_processing_latency_ms
                ),
                "observation_jitter_ms": item.observation_jitter_ms,
                "learning_signal_ms": item.learning_signal_ms,
                "likelihood": list(item.likelihood),
                "estimated_state": item.estimated_state,
                "pod_name": getattr(provenance, "pod_name", None),
                "pod_uid": getattr(provenance, "pod_uid", None),
            }
        )
    evidence = {
        "contract_version": GREEDY_SLOT_EVIDENCE_VERSION,
        "policy_contract_version": GREEDY_POLICY_VERSION,
        "slot_contract_version": slot.contract_version,
        "experiment_id": slot.experiment_id,
        "slot_id": slot.slot_id,
        "root_seed": slot.root_seed,
        "profile_seed": slot.profile_seed,
        "runtime_profile_fingerprint": slot.profile_fingerprint,
        "configuration": {
            "num_flows": slot.configuration.num_flows,
            "num_stages": slot.configuration.num_stages,
            "num_replicas": slot.configuration.num_replicas,
            "stage_budget": 2,
        },
        "flow_order_seed_scheme": slot.flow_order_seed_scheme,
        "flow_order_seed": slot.flow_order_seed,
        "flow_order": list(slot.flow_order),
        "placements": [
            {
                "decision_position": placement.decision_position,
                "flow_id": placement.flow_id,
                "selected": [_identity(item) for item in placement.action.choices],
                "bypassed_stages": list(placement.bypassed_stages),
                "stage_utilities": list(placement.decision.stage_utilities),
                "objective_value": placement.decision.objective_value,
                "loads_before": _loads(placement.decision.state_before.entries),
                "loads_after": _loads(placement.decision.state_after.entries),
                "evaluated_actions": placement.decision.evaluated_actions,
                "feasible_actions": placement.decision.feasible_actions,
            }
            for placement in slot.placements
        ],
        "final_loads": _loads(slot.final_loads.entries),
        "observations": observations,
        "observation_count": len(observations),
        "measured_pairs": [
            {
                "flow_id": pair.flow_id,
                "source": _identity(pair.source),
                "target": _identity(pair.target),
                "measured_pair_latency_ms": pair.latency_ms,
            }
            for pair in slot.measured_pairs
        ],
        "measured_pair_count": len(slot.measured_pairs),
        "beliefs_before": _beliefs(slot.beliefs_before),
        "beliefs_after": _beliefs(slot.beliefs_after),
        "metrics": asdict(slot.metrics),
        "phase_timings_seconds": asdict(outcome.phase_timings),
        "controller_to_generator_requests": (
            outcome.controller_to_generator_requests
        ),
        "selected_route_requests": outcome.selected_route_requests,
        "pure_kernel_replay_requested": parity_replay_enabled,
        "pure_kernel_replay_performed": parity_replay_enabled,
    }
    if outcome.control_plane is not None:
        evidence["control_plane"] = dict(outcome.control_plane)
    if outcome.controller_resources is not None:
        evidence["controller_resources"] = outcome.controller_resources.to_mapping()
    if parity_replay_enabled:
        replay = replay_greedy_evidence_slot(outcome)
        if not replay.matched:
            raise RuntimeError("Greedy Pure/Kernel parity replay failed")
        evidence["pure_kernel_replay_parity"] = True
    return validate_greedy_slot_evidence(evidence)


def canonical_greedy_evidence_json(evidence: Mapping[str, object]) -> str:
    validated = validate_greedy_slot_evidence(evidence)
    return json.dumps(validated, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _flow_pairs(value: object, *, name: str, flows: set[int]) -> dict[int, float]:
    if not isinstance(value, (list, tuple)) or len(value) != len(flows):
        raise ValueError(f"{name} must cover every flow")
    result = {}
    for item in value:
        if (
            not isinstance(item, (list, tuple))
            or len(item) != 2
            or isinstance(item[0], bool)
            or not isinstance(item[0], int)
            or item[0] in result
            or isinstance(item[1], bool)
            or not isinstance(item[1], (int, float))
            or not isfinite(float(item[1]))
        ):
            raise ValueError(f"{name} contains invalid flow values")
        result[item[0]] = float(item[1])
    if set(result) != flows:
        raise ValueError(f"{name} must cover configured flows")
    return result


def _integer_value(name: str, value: object, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer at least {minimum}")
    return value


def _finite_number(name: str, value: object, *, minimum: float | None = None) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
        or (minimum is not None and float(value) < minimum)
    ):
        qualifier = " finite" if minimum is None else f" finite and at least {minimum}"
        raise ValueError(f"{name} must be{qualifier}")
    return float(value)


def _identity_mapping(
    value: object,
    *,
    name: str,
    num_stages: int,
    num_replicas: int,
) -> tuple[int, int]:
    if not isinstance(value, Mapping) or set(value) != {"stage", "replica"}:
        raise ValueError(f"{name} is not a canonical replica identity")
    stage = _integer_value(f"{name}.stage", value["stage"], minimum=1)
    replica = _integer_value(f"{name}.replica", value["replica"], minimum=1)
    if stage > num_stages or replica > num_replicas:
        raise ValueError(f"{name} is outside the configured topology")
    return stage, replica


def _load_mapping(
    value: object,
    *,
    name: str,
    identities: tuple[tuple[int, int], ...],
) -> dict[tuple[int, int], int]:
    if not isinstance(value, list) or len(value) != len(identities):
        raise ValueError(f"{name} must cover every replica")
    result: dict[tuple[int, int], int] = {}
    ordered = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"stage", "replica", "load"}:
            raise ValueError(f"{name} contains malformed load entries")
        identity = (item["stage"], item["replica"])
        load = _integer_value(f"{name}.load", item["load"])
        if identity in result:
            raise ValueError(f"{name} contains duplicate replica loads")
        ordered.append(identity)
        result[identity] = load
    if tuple(ordered) != identities:
        raise ValueError(f"{name} identities are incomplete or noncanonical")
    return result


def _belief_mapping(
    value: object,
    *,
    name: str,
    identities: tuple[tuple[int, int], ...],
) -> dict[tuple[int, int], tuple[float, ...]]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    expected = {f"{stage}:{replica}" for stage, replica in identities}
    if set(value) != expected:
        raise ValueError(f"{name} must cover every replica identity")
    result = {}
    for stage, replica in identities:
        belief = value[f"{stage}:{replica}"]
        if not isinstance(belief, list) or len(belief) != 4:
            raise ValueError(f"{name} belief vectors must contain four entries")
        normalized = tuple(
            _finite_number(f"{name}.{stage}:{replica}", item, minimum=0.0)
            for item in belief
        )
        if (
            abs(sum(normalized) - 1.0)
            > GREEDY_ROUNDED_BELIEF_SUM_TOLERANCE
        ):
            raise ValueError(
                f"{name} belief vectors exceed the rounded unit-mass tolerance"
            )
        result[(stage, replica)] = normalized
    return result


def validate_greedy_slot_evidence(
    value: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("Greedy slot evidence must be an object")
    try:
        # The validator returns the exact JSON-compatible representation that
        # is persisted, so tuples cannot make an in-memory trace differ from
        # its round trip.
        document = json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError("Greedy slot evidence is not finite JSON data") from error
    required = {
        "contract_version", "policy_contract_version", "slot_contract_version",
        "experiment_id", "slot_id", "root_seed", "profile_seed",
        "runtime_profile_fingerprint", "configuration", "flow_order_seed_scheme",
        "flow_order_seed", "flow_order", "placements", "final_loads",
        "observations", "observation_count", "measured_pairs",
        "measured_pair_count", "beliefs_before", "beliefs_after", "metrics",
        "phase_timings_seconds", "controller_to_generator_requests",
        "selected_route_requests", "pure_kernel_replay_requested",
        "pure_kernel_replay_performed",
    }
    optional = {"pure_kernel_replay_parity", "control_plane", "controller_resources"}
    if not required.issubset(document) or not set(document).issubset(required | optional):
        raise ValueError("Greedy slot evidence fields are incomplete or unexpected")
    evidence_version = document["contract_version"]
    if evidence_version not in {
        LEGACY_GREEDY_SLOT_EVIDENCE_VERSION,
        PREDICTED_FAIRNESS_GREEDY_SLOT_EVIDENCE_VERSION,
        GREEDY_SLOT_EVIDENCE_VERSION,
    }:
        raise ValueError("unsupported Greedy slot evidence version")
    legacy_v1 = evidence_version == LEGACY_GREEDY_SLOT_EVIDENCE_VERSION
    predicted_fairness = evidence_version != GREEDY_SLOT_EVIDENCE_VERSION
    expected_policy_version = (
        LEGACY_GREEDY_POLICY_VERSION if legacy_v1 else GREEDY_POLICY_VERSION
    )
    if document["policy_contract_version"] != expected_policy_version:
        raise ValueError("Greedy slot policy provenance drifted")
    if document["slot_contract_version"] != GREEDY_SLOT_CONTRACT_VERSION:
        raise ValueError("Greedy slot contract provenance drifted")
    _integer_value("experiment_id", document["experiment_id"], minimum=1)
    _integer_value("slot_id", document["slot_id"], minimum=1)
    _integer_value("root_seed", document["root_seed"])
    _integer_value("profile_seed", document["profile_seed"])
    for name in ("runtime_profile_fingerprint", "flow_order_seed_scheme"):
        if not isinstance(document[name], str) or not document[name]:
            raise ValueError(f"{name} must be nonempty")
    flow_order_seed = document["flow_order_seed"]
    if document["flow_order_seed_scheme"] == GREEDY_EXPLICIT_FLOW_ORDER_SCHEME:
        if flow_order_seed is not None:
            raise ValueError("explicit Greedy flow order cannot record a derived seed")
    elif document["flow_order_seed_scheme"] == GREEDY_FLOW_ORDER_SEED_SCHEME:
        _integer_value("flow_order_seed", flow_order_seed)
    else:
        raise ValueError("Greedy evidence flow-order seed scheme drifted")
    configuration = document["configuration"]
    expected_configuration_fields = {
        "num_flows", "num_stages", "num_replicas", "stage_budget",
    }
    if legacy_v1:
        expected_configuration_fields.add("admission_capacity_per_replica")
    if (
        not isinstance(configuration, Mapping)
        or set(configuration) != expected_configuration_fields
    ):
        raise ValueError("Greedy evidence configuration is invalid")
    n, k, m = (
        configuration["num_flows"], configuration["num_stages"],
        configuration["num_replicas"],
    )
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in (n, k, m)):
        raise ValueError("Greedy evidence dimensions are invalid")
    if k < 2 or configuration["stage_budget"] != 2:
        raise ValueError("Greedy evidence must retain fixed L=2")
    if legacy_v1 and configuration["admission_capacity_per_replica"] != (n + m - 1) // m:
        raise ValueError("Greedy evidence admission capacity is inconsistent")
    flows = set(range(1, n + 1))
    identities = tuple(
        (stage, replica)
        for stage in range(1, k + 1)
        for replica in range(1, m + 1)
    )
    order = document["flow_order"]
    if not isinstance(order, list) or len(order) != n or set(order) != flows:
        raise ValueError("Greedy evidence flow order is incomplete")
    placements = document["placements"]
    observations = document["observations"]
    pairs = document["measured_pairs"]
    if not isinstance(placements, list) or len(placements) != n:
        raise ValueError("Greedy evidence requires N placements")
    if [item.get("flow_id") for item in placements if isinstance(item, Mapping)] != order:
        raise ValueError("Greedy evidence placements do not retain flow order")
    expected_placement_fields = {
        "decision_position", "flow_id", "selected", "bypassed_stages",
        "stage_utilities", "objective_value", "loads_before", "loads_after",
        "evaluated_actions", "feasible_actions",
    }
    previous_loads = {identity: 0 for identity in identities}
    selected_by_flow = {}
    for position, item in enumerate(placements, start=1):
        if (
            not isinstance(item, Mapping)
            or set(item) != expected_placement_fields
            or item.get("decision_position") != position
            or item.get("flow_id") != order[position - 1]
        ):
            raise ValueError("Greedy evidence decision positions are invalid")
        selected = item.get("selected")
        bypassed = item.get("bypassed_stages")
        if not isinstance(selected, list) or len(selected) != 2:
            raise ValueError("Greedy evidence placement must contain two selections")
        selected_identities = tuple(
            _identity_mapping(
                identity, name="selected identity", num_stages=k, num_replicas=m
            )
            for identity in selected
        )
        stages = [identity[0] for identity in selected_identities]
        if not stages[0] < stages[1]:
            raise ValueError("Greedy evidence selected stages are invalid")
        if bypassed != [stage for stage in range(1, k + 1) if stage not in stages]:
            raise ValueError("Greedy evidence bypass set is invalid")
        utilities = item["stage_utilities"]
        if not isinstance(utilities, list) or len(utilities) != 2:
            raise ValueError("Greedy evidence must retain two stage utilities")
        utilities = tuple(_finite_number("stage utility", value) for value in utilities)
        objective = _finite_number("objective_value", item["objective_value"])
        if abs(sum(utilities) - objective) > 1e-9:
            raise ValueError("Greedy evidence objective is not the stage-utility sum")
        before = _load_mapping(
            item["loads_before"], name="loads_before", identities=identities
        )
        after = _load_mapping(
            item["loads_after"], name="loads_after", identities=identities
        )
        if before != previous_loads:
            raise ValueError("Greedy evidence load chain is discontinuous")
        expected_after = dict(before)
        for identity in selected_identities:
            expected_after[identity] += 1
            if (
                legacy_v1
                and expected_after[identity]
                > configuration["admission_capacity_per_replica"]
            ):
                raise ValueError("Greedy evidence exceeds admission capacity")
        if after != expected_after:
            raise ValueError("Greedy evidence load mutation is inconsistent")
        evaluated = _integer_value("evaluated_actions", item["evaluated_actions"], minimum=1)
        feasible = _integer_value("feasible_actions", item["feasible_actions"], minimum=1)
        if feasible > evaluated:
            raise ValueError("Greedy feasible-action count exceeds evaluated actions")
        previous_loads = after
        selected_by_flow[item["flow_id"]] = selected_identities
    final_loads = _load_mapping(
        document["final_loads"], name="final_loads", identities=identities
    )
    if final_loads != previous_loads:
        raise ValueError("Greedy evidence final loads do not match the decision chain")
    if document["observation_count"] != 2 * n or not isinstance(observations, list) or len(observations) != 2 * n:
        raise ValueError("Greedy evidence selected observation count is invalid")
    if document["measured_pair_count"] != n or not isinstance(pairs, list) or len(pairs) != n:
        raise ValueError("Greedy evidence selected pair count is invalid")
    expected_observation_fields = {
        "flow_id", "stage", "replica", "assigned_load",
        "physical_processing_latency_ms", "observation_jitter_ms",
        "learning_signal_ms", "likelihood", "estimated_state", "pod_name",
        "pod_uid",
    }
    observed = set()
    physical_by_flow = {flow: 0.0 for flow in flows}
    for item in observations:
        if not isinstance(item, Mapping) or set(item) != expected_observation_fields:
            raise ValueError("Greedy evidence observation fields are malformed")
        flow = _integer_value("observation flow_id", item["flow_id"], minimum=1)
        identity = _identity_mapping(
            {"stage": item["stage"], "replica": item["replica"]},
            name="observation identity", num_stages=k, num_replicas=m,
        )
        key = (flow, identity)
        if flow not in flows or key in observed or identity not in selected_by_flow[flow]:
            raise ValueError("Greedy evidence observations are not exactly selected-only")
        observed.add(key)
        assigned = _integer_value("observation assigned_load", item["assigned_load"], minimum=1)
        if assigned != final_loads[identity]:
            raise ValueError("Greedy evidence observation load is not final-load conditioned")
        physical = _finite_number(
            "physical_processing_latency_ms",
            item["physical_processing_latency_ms"], minimum=0.0,
        )
        jitter = _finite_number(
            "observation_jitter_ms", item["observation_jitter_ms"], minimum=0.0
        )
        signal = _finite_number("learning_signal_ms", item["learning_signal_ms"], minimum=0.0)
        if abs(physical + jitter - signal) > 1e-9:
            raise ValueError("Greedy evidence collapses or misstates separated jitter")
        likelihood = item["likelihood"]
        if not isinstance(likelihood, list) or len(likelihood) != 4:
            raise ValueError("Greedy evidence likelihood must have four entries")
        likelihood = tuple(
            _finite_number("likelihood", value, minimum=0.0) for value in likelihood
        )
        if abs(sum(likelihood) - 1.0) > 1e-9:
            raise ValueError("Greedy evidence likelihood must sum to one")
        if item["estimated_state"] != likelihood.index(max(likelihood)) + 1:
            raise ValueError("Greedy evidence estimated state is inconsistent")
        for field in ("pod_name", "pod_uid"):
            if item[field] is not None and (
                not isinstance(item[field], str) or not item[field]
            ):
                raise ValueError(f"Greedy evidence {field} is malformed")
        physical_by_flow[flow] += physical
    expected_observations = {
        (flow, identity)
        for flow, selected_identities in selected_by_flow.items()
        for identity in selected_identities
    }
    if observed != expected_observations:
        raise ValueError("Greedy evidence selected observation coverage is incomplete")
    expected_pair_fields = {
        "flow_id", "source", "target", "measured_pair_latency_ms"
    }
    pair_latency = {}
    for pair in pairs:
        if not isinstance(pair, Mapping) or set(pair) != expected_pair_fields:
            raise ValueError("Greedy evidence pair fields are malformed")
        flow = _integer_value("pair flow_id", pair["flow_id"], minimum=1)
        source = _identity_mapping(
            pair["source"], name="pair source", num_stages=k, num_replicas=m
        )
        target = _identity_mapping(
            pair["target"], name="pair target", num_stages=k, num_replicas=m
        )
        if flow not in flows or flow in pair_latency or (source, target) != selected_by_flow[flow]:
            raise ValueError("Greedy evidence pairs do not match selected routes")
        pair_latency[flow] = _finite_number(
            "measured_pair_latency_ms", pair["measured_pair_latency_ms"], minimum=0.0
        )
    if set(pair_latency) != flows:
        raise ValueError("Greedy evidence pair coverage is incomplete")
    beliefs_before = _belief_mapping(
        document["beliefs_before"], name="beliefs_before", identities=identities
    )
    beliefs_after = _belief_mapping(
        document["beliefs_after"], name="beliefs_after", identities=identities
    )
    metrics = document["metrics"]
    if not isinstance(metrics, Mapping):
        raise ValueError("Greedy evidence metrics are missing")
    metric_fields = {
        "predicted_aggregate_utility", "predicted_utility_per_flow",
        "physical_realized_aggregate_utility", "physical_realized_utility_per_flow",
        "physical_processing_latency_ms_per_flow", "measured_pair_latency_ms_per_flow",
        "raw_end_to_end_latency_ms_per_flow", "raw_end_to_end_reference_utility",
        "raw_end_to_end_reference_utility_per_flow", "sla_latency_threshold_ms",
        "end_to_end_sla_violations", "end_to_end_sla_excess_ms", "jain_fairness",
        "maximum_belief_change", "equilibrium",
    }
    if not predicted_fairness:
        metric_fields = metric_fields | {"fairness_domain_valid"}
    if set(metrics) != metric_fields:
        raise ValueError("Greedy evidence metric fields are incomplete or unexpected")
    raw = _flow_pairs(
        metrics.get("raw_end_to_end_latency_ms_per_flow"),
        name="raw end-to-end latency", flows=flows,
    )
    threshold = metrics.get("sla_latency_threshold_ms")
    if threshold != 80.0:
        raise ValueError("Greedy evidence SLA threshold drifted")
    violations = sum(raw[flow] > threshold for flow in sorted(raw))
    excess = sum(max(0.0, raw[flow] - threshold) for flow in sorted(raw))
    if metrics.get("end_to_end_sla_violations") != violations:
        raise ValueError("Greedy evidence SLA violation count is inconsistent")
    if metrics.get("end_to_end_sla_excess_ms") != excess:
        raise ValueError("Greedy evidence SLA excess is inconsistent")
    metric_pairs = {}
    for name, aggregate in (
        ("predicted_utility_per_flow", "predicted_aggregate_utility"),
        ("physical_realized_utility_per_flow", "physical_realized_aggregate_utility"),
        ("raw_end_to_end_reference_utility_per_flow", "raw_end_to_end_reference_utility"),
    ):
        per_flow = _flow_pairs(metrics.get(name), name=name, flows=flows)
        aggregate_value = _finite_number(aggregate, metrics.get(aggregate))
        if abs(sum(per_flow.values()) - aggregate_value) > 1e-9:
            raise ValueError(f"Greedy evidence {aggregate} is inconsistent")
        metric_pairs[name] = per_flow
    physical_metric = _flow_pairs(
        metrics["physical_processing_latency_ms_per_flow"],
        name="physical processing latency", flows=flows,
    )
    measured_metric = _flow_pairs(
        metrics["measured_pair_latency_ms_per_flow"],
        name="measured pair latency", flows=flows,
    )
    for flow in flows:
        if abs(physical_metric[flow] - physical_by_flow[flow]) > 1e-9:
            raise ValueError("Greedy evidence physical latency is inconsistent")
        if abs(measured_metric[flow] - pair_latency[flow]) > 1e-9:
            raise ValueError("Greedy evidence measured pair latency is inconsistent")
        if abs(raw[flow] - physical_by_flow[flow] - pair_latency[flow]) > 1e-9:
            raise ValueError("Greedy evidence raw end-to-end latency is inconsistent")
        reference = metric_pairs["raw_end_to_end_reference_utility_per_flow"][flow]
        physical_utility = metric_pairs["physical_realized_utility_per_flow"][flow]
        if abs(reference - (physical_utility - pair_latency[flow])) > 1e-9:
            raise ValueError("Greedy evidence raw reference utility is inconsistent")
    fairness = _finite_number("jain_fairness", metrics.get("jain_fairness"), minimum=0.0)
    if predicted_fairness:
        predicted = metric_pairs["predicted_utility_per_flow"]
        denominator = len(predicted) * sum(
            round(value, 3) ** 2 for value in predicted.values()
        )
        if denominator == 0:
            raise ValueError("Greedy evidence fairness denominator is zero")
        expected_fairness = (
            float(metrics["predicted_aggregate_utility"]) ** 2 / denominator
        )
        expected_domain_valid = None
    else:
        expected_fairness, expected_domain_valid = clamped_end_to_end_fairness(
            metric_pairs["raw_end_to_end_reference_utility_per_flow"]
        )
    if abs(fairness - expected_fairness) > 1e-9:
        raise ValueError("Greedy evidence fairness is inconsistent")
    if expected_domain_valid is not None:
        domain_valid = metrics["fairness_domain_valid"]
        if not isinstance(domain_valid, bool):
            raise ValueError("Greedy evidence fairness domain flag must be boolean")
        if domain_valid is not expected_domain_valid:
            raise ValueError("Greedy evidence fairness domain flag is inconsistent")
    maximum_change = max(
        abs(before - after)
        for identity in identities
        for before, after in zip(
            beliefs_before[identity], beliefs_after[identity], strict=True
        )
    )
    if abs(_finite_number("maximum_belief_change", metrics["maximum_belief_change"], minimum=0.0) - maximum_change) > 1e-9:
        raise ValueError("Greedy evidence maximum belief change is inconsistent")
    if not isinstance(metrics["equilibrium"], bool) or metrics["equilibrium"] is not (maximum_change < 0.04):
        raise ValueError("Greedy evidence equilibrium is inconsistent")
    timing_fields = {
        "discovery_seconds", "admission_placement_seconds", "route_dispatch_seconds",
        "data_plane_wait_seconds", "feedback_validation_seconds", "total_slot_seconds",
    }
    timings = document["phase_timings_seconds"]
    if not isinstance(timings, Mapping) or set(timings) != timing_fields:
        raise ValueError("Greedy evidence phase timing fields are invalid")
    components = tuple(
        _finite_number(name, timings[name], minimum=0.0)
        for name in timing_fields - {"total_slot_seconds"}
    )
    total = _finite_number("total_slot_seconds", timings["total_slot_seconds"], minimum=0.0)
    if abs(sum(components) - total) > 1e-9:
        raise ValueError("Greedy evidence phase timing total is inconsistent")
    requested = document["pure_kernel_replay_requested"]
    performed = document["pure_kernel_replay_performed"]
    if not isinstance(requested, bool) or performed is not requested:
        raise ValueError("Greedy replay request/performance provenance is inconsistent")
    if requested:
        if document.get("pure_kernel_replay_parity") is not True:
            raise ValueError("Greedy enabled replay did not pass")
    elif "pure_kernel_replay_parity" in document:
        raise ValueError("Greedy disabled replay cannot record a result")
    if document.get("controller_to_generator_requests") != 1 or document.get("selected_route_requests") != n:
        raise ValueError("Greedy evidence request counts are inconsistent")
    if "control_plane" in document:
        validate_greedy_control_plane_snapshot(document["control_plane"])
    if "controller_resources" in document:
        validate_controller_resource_mapping(document["controller_resources"])
    forbidden = {
        "hidden_state", "hidden_states", "observation_seed", "observation_seeds",
        "physical_seed", "physical_seeds", "runtime_profiles", "profile_map",
    }
    def reject_hidden(item: object) -> None:
        if isinstance(item, Mapping):
            if forbidden & set(item):
                raise ValueError("Greedy evidence exposes hidden runtime state or seeds")
            for nested in item.values():
                reject_hidden(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                reject_hidden(nested)
    reject_hidden(document)
    _finite_tree(document)
    return document
