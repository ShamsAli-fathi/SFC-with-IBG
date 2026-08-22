"""Phase 5 orchestration for one complete pure-Python IBG-Hybrid slot."""

from __future__ import annotations

import importlib
import random
import sys
import time
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import replace
from itertools import combinations, product
from pathlib import Path
from typing import Mapping

from IBG import latency_model as exact_latency
from IBG import learning as exact_learning
from IBG.report import SLA_v

from .contracts import GlobalLoadState, HybridConfiguration, ReplicaChoice
from .console_output import format_hybrid_slot_metrics
from .expected_utility import expected_stage_utility_from_belief
from .phase0_contract import (
    DEFAULT_HYBRID_POLICY_PARAMETERS,
    HYBRID_FLOW_ORDER_SEED_SCHEME,
    HYBRID_LINK_WEIGHT_UTILITY_PER_MS,
    HYBRID_POLICY_CONTRACT_VERSION,
    HybridActivationContext,
    HybridPolicyParameters,
    PipelinePath,
    ReplicaAdmission,
    derive_flow_order_seed,
    maximum_contention_ratio,
    maximum_normalized_belief_entropy,
    select_pipeline_path,
)
from .policy import (
    CandidateAccounting,
    HybridGreedyDecision,
    HybridLookaheadDecision,
    HybridMonteCarloDecision,
    IBGHybridPolicy,
)
from .simulation import (
    HybridSlotSimulationAdapter,
    InProcessHybridSimulationAdapter,
)
from .slot_contracts import (
    BeliefVector,
    HybridFlow,
    HybridMeasuredPair,
    HybridPairValue,
    HybridPlacement,
    HybridReplica,
    HybridSelectedObservation,
    HybridSimulationResult,
    HybridSlotInput,
    HybridSlotMetrics,
    HybridSlotResult,
)


EXACT_BELIEF_RETENTION = 0.8
EXACT_EQUILIBRIUM_THRESHOLD = 0.04
HYBRID_SLA_LATENCY_THRESHOLD_MS = 80.0


# These names intentionally describe orchestration only.  They do not select
# or alter an internal policy automatically: ``mc`` is reachable solely when
# the caller explicitly requests it.
HYBRID_SLOT_POLICY_LOOKAHEAD = "lookahead"
HYBRID_SLOT_POLICY_MC = "mc"
DEFAULT_HYBRID_MC_WORKERS = 3
_HYBRID_SLOT_POLICIES = frozenset(
    (HYBRID_SLOT_POLICY_LOOKAHEAD, HYBRID_SLOT_POLICY_MC)
)


def _require_slot_policy(policy_mode: str) -> str:
    if not isinstance(policy_mode, str):
        raise TypeError("policy_mode must be a string")
    if policy_mode not in _HYBRID_SLOT_POLICIES:
        supported = ", ".join(sorted(_HYBRID_SLOT_POLICIES))
        raise ValueError(f"policy_mode must be one of: {supported}")
    return policy_mode


def _require_mc_workers(mc_workers: int) -> int:
    if isinstance(mc_workers, bool) or not isinstance(mc_workers, int):
        raise TypeError("mc_workers must be an integer")
    if mc_workers < 1:
        raise ValueError("mc_workers must be positive")
    return mc_workers


def _load_exact_header():
    """Load the frozen Exact module only while a slot actually runs.

    The historical Exact source uses flat imports. Tests already expose
    ``IBG/`` on ``sys.path``; a clean package consumer receives the same
    source through a temporary import path. Merely importing Hybrid remains
    free of Exact header side effects.
    """

    try:
        return importlib.import_module("header")
    except ModuleNotFoundError as error:
        if error.name != "header":
            raise
    exact_directory = str(Path(__file__).resolve().parents[1] / "IBG")
    sys.path.insert(0, exact_directory)
    try:
        return importlib.import_module("header")
    finally:
        if sys.path and sys.path[0] == exact_directory:
            del sys.path[0]


def _policy_maps(slot_input: HybridSlotInput):
    admission = {
        replica.choice: ReplicaAdmission(
            choice=replica.choice,
            ready=replica.ready,
            max_assigned_flows=replica.max_assigned_flows,
        )
        for replica in slot_input.replicas
    }
    return admission, slot_input.beliefs, slot_input.planning_pair_link_costs


def _activation_from_greedy_pool(
    *,
    greedy: HybridGreedyDecision,
    state: GlobalLoadState,
    configuration: HybridConfiguration,
    beliefs: Mapping[ReplicaChoice, BeliefVector],
    admission: Mapping[ReplicaChoice, ReplicaAdmission],
    high_priority: bool,
) -> HybridActivationContext:
    active_choices = {
        choice
        for scored in greedy.scored_actions
        for choice in scored.action.choices
    }
    if not active_choices:
        raise RuntimeError("activation requires a feasible pruned replica pool")
    return HybridActivationContext(
        contention_ratio=maximum_contention_ratio(
            state,
            configuration,
            {
                choice: admission[choice]
                for choice in active_choices
            },
        ),
        maximum_normalized_belief_entropy=maximum_normalized_belief_entropy(
            {
                choice: beliefs[choice]
                for choice in active_choices
            }
        ),
        high_priority=high_priority,
    )


def _activation_reason(
    path: PipelinePath,
    context: HybridActivationContext,
    parameters: HybridPolicyParameters,
) -> str:
    if path is not PipelinePath.LOOKAHEAD:
        raise RuntimeError(
            "automatic core Hybrid orchestration must use lookahead"
        )
    return (
        "default-pruned-lookahead"
        f"-d{parameters.lookahead_future_flows}"
    )


def _accounting_for_decision(
    decision: (
        HybridGreedyDecision
        | HybridLookaheadDecision
        | HybridMonteCarloDecision
    ),
) -> CandidateAccounting:
    if isinstance(decision, HybridGreedyDecision):
        return decision.accounting
    return decision.focal_accounting


def _validate_simulation_result(
    *,
    result: HybridSimulationResult,
    actions_by_flow,
    final_loads: GlobalLoadState,
) -> None:
    expected_observations = {
        (flow_id, choice)
        for flow_id, action in actions_by_flow.items()
        for choice in action.choices
    }
    actual_observations = {
        (observation.flow_id, observation.choice)
        for observation in result.observations
    }
    if len(result.observations) != len(expected_observations):
        raise RuntimeError(
            "simulation returned an incomplete or duplicate selected observation set"
        )
    if actual_observations != expected_observations:
        raise RuntimeError(
            "simulation observations do not exactly match committed selections"
        )
    for observation in result.observations:
        if observation.assigned_load != final_loads.load_for(observation.choice):
            raise RuntimeError(
                "simulation observation does not use final assigned load"
            )

    expected_flows = set(actions_by_flow)
    actual_pair_flows = {pair.flow_id for pair in result.measured_pairs}
    if len(result.measured_pairs) != len(expected_flows):
        raise RuntimeError(
            "simulation must return exactly one measured pair per committed flow"
        )
    if actual_pair_flows != expected_flows:
        raise RuntimeError(
            "simulation measured-pair records do not cover committed flows"
        )
    for pair in result.measured_pairs:
        action = actions_by_flow[pair.flow_id]
        if (pair.source, pair.target) != action.choices:
            raise RuntimeError(
                "simulation measured pair does not match the committed action"
            )


def _make_exact_learning_replicas(slot_input: HybridSlotInput):
    exact_header = _load_exact_header()
    replicas = {}
    for profile in sorted(slot_input.replicas, key=lambda value: value.choice):
        replicas[(profile.choice.stage, profile.choice.replica)] = (
            exact_header.Replica(
                stage=profile.choice.stage,
                replica=profile.choice.replica,
                belief=list(profile.belief),
                delay=25,
                cost=exact_latency.DEFAULT_COST,
                gamma=0.0,
                # Exact posterior/aggregation and linear utility do not read
                # ``state``. Keep the actual hidden state inside the
                # simulation observation adapter only.
                state=1,
                capacity=profile.max_assigned_flows,
                reward=exact_latency.DEFAULT_REWARD,
                latency_weight=exact_latency.DEFAULT_LATENCY_WEIGHT,
            )
        )
    return exact_header, replicas


def _belief_snapshot(replicas) -> tuple[tuple[ReplicaChoice, BeliefVector], ...]:
    return tuple(
        (
            ReplicaChoice(stage, replica),
            tuple(float(value) for value in replicas[(stage, replica)].belief),
        )
        for stage, replica in sorted(replicas)
    )


def _metric_pairs(values: Mapping[int, float]) -> tuple[tuple[int, float], ...]:
    return tuple((flow, float(values[flow])) for flow in sorted(values))


def _compute_metrics(
    *,
    slot_input: HybridSlotInput,
    placements: tuple[HybridPlacement, ...],
    observations: tuple[HybridSelectedObservation, ...],
    measured_pairs: tuple[HybridMeasuredPair, ...],
    beliefs_before,
    beliefs_after,
    exact_header,
    exact_replicas,
    elapsed_seconds: float,
) -> HybridSlotMetrics:
    beliefs_before_map = dict(beliefs_before)
    # Every selected stage value is conditioned on the final slot load, not
    # the load at the time the focal action was committed.
    final_loads = placements[-1].state_after
    expected_per_flow = {}
    for placement in placements:
        expected_per_flow[placement.flow.flow_id] = (
            sum(
                expected_stage_utility_from_belief(
                    beliefs_before_map[choice],
                    final_loads.load_for(choice),
                )
                for choice in placement.action.choices
            )
            - HYBRID_LINK_WEIGHT_UTILITY_PER_MS
            * slot_input.planning_pair_link_costs[placement.action.choices]
        )
    aggregate_expected = sum(expected_per_flow.values())

    physical_latency = {
        flow.flow_id: 0.0
        for flow in slot_input.flows
    }
    physical_utility = {
        flow.flow_id: 0.0
        for flow in slot_input.flows
    }
    for observation in observations:
        physical_latency[observation.flow_id] += (
            observation.physical_processing_latency_ms
        )
        replica = exact_replicas[
            (observation.choice.stage, observation.choice.replica)
        ]
        physical_utility[observation.flow_id] += replica.utility_kernel(
            observation.assigned_load,
            observation.physical_processing_latency_ms,
        )

    pair_latency = {
        pair.flow_id: pair.latency_ms
        for pair in measured_pairs
    }
    raw_end_to_end_latency = {
        flow_id: physical_latency[flow_id] + pair_latency[flow_id]
        for flow_id in physical_latency
    }
    raw_reference_utility = {
        flow_id: physical_utility[flow_id]
        - HYBRID_LINK_WEIGHT_UTILITY_PER_MS * pair_latency[flow_id]
        for flow_id in physical_utility
    }
    sla_violations = SLA_v(
        raw_end_to_end_latency,
        HYBRID_SLA_LATENCY_THRESHOLD_MS,
    )
    sla_excess_ms = sum(
        max(
            0.0,
            raw_end_to_end_latency[flow_id]
            - HYBRID_SLA_LATENCY_THRESHOLD_MS,
        )
        for flow_id in sorted(raw_end_to_end_latency)
    )

    fairness_input = {
        flow_id: [expected_per_flow[flow_id]]
        for flow_id in expected_per_flow
    }
    fairness = exact_header.jain_index(
        fairness_input,
        aggregate_expected,
    )
    previous_beliefs = [
        list(values)
        for _choice, values in beliefs_before
    ]
    equilibrium = bool(
        exact_header.is_equilibrium(
            exact_replicas,
            previous_beliefs,
            threshold=EXACT_EQUILIBRIUM_THRESHOLD,
        )
    )
    before_map = dict(beliefs_before)
    after_map = dict(beliefs_after)
    maximum_change = max(
        abs(after - before)
        for choice in before_map
        for before, after in zip(before_map[choice], after_map[choice])
    )

    return HybridSlotMetrics(
        aggregate_expected_utility=aggregate_expected,
        aggregate_expected_utility_per_flow=_metric_pairs(expected_per_flow),
        physical_realized_utility=sum(physical_utility.values()),
        physical_realized_utility_per_flow=_metric_pairs(physical_utility),
        physical_processing_latency_ms_per_flow=_metric_pairs(physical_latency),
        measured_pair_latency_ms_per_flow=_metric_pairs(pair_latency),
        raw_end_to_end_latency_ms_per_flow=_metric_pairs(raw_end_to_end_latency),
        raw_end_to_end_reference_utility=sum(raw_reference_utility.values()),
        raw_end_to_end_reference_utility_per_flow=_metric_pairs(
            raw_reference_utility
        ),
        sla_latency_threshold_ms=HYBRID_SLA_LATENCY_THRESHOLD_MS,
        end_to_end_sla_violations=sla_violations,
        end_to_end_sla_excess_ms=sla_excess_ms,
        jain_fairness=fairness,
        elapsed_seconds=elapsed_seconds,
        maximum_belief_change=maximum_change,
        equilibrium=equilibrium,
    )


def _place_all_flows(
    *,
    slot_input: HybridSlotInput,
    policy: IBGHybridPolicy,
    policy_mode: str,
    mc_workers: int,
    ordered_flow_ids: list[int],
    lookahead_executor: Executor | None,
    rollout_executor: ProcessPoolExecutor | None,
) -> tuple[tuple[HybridPlacement, ...], GlobalLoadState]:
    """Commit every real focal placement, optionally sharing one MC pool."""

    admission, beliefs, planning_links = _policy_maps(slot_input)
    flow_by_id = slot_input.flow_by_id
    state = slot_input.initial_loads
    placements = []
    for decision_position, flow_id in enumerate(ordered_flow_ids, start=1):
        flow = flow_by_id[flow_id]
        state_before = state
        greedy_probe = policy.select_greedy(
            state=state_before,
            admission=admission,
            beliefs=beliefs,
            known_pair_link_costs=planning_links,
        )
        activation = _activation_from_greedy_pool(
            greedy=greedy_probe,
            state=state_before,
            configuration=slot_input.configuration,
            beliefs=beliefs,
            admission=admission,
            high_priority=flow.high_priority,
        )
        automatic_path = select_pipeline_path(
            activation,
            slot_input.parameters,
        )
        if automatic_path is not PipelinePath.LOOKAHEAD:
            raise RuntimeError(
                "automatic core Hybrid orchestration selected a non-lookahead path"
            )
        if policy_mode == HYBRID_SLOT_POLICY_LOOKAHEAD:
            path = automatic_path
            activation_reason = _activation_reason(
                path,
                activation,
                slot_input.parameters,
            )
            detail = policy.select_lookahead(
                state=state_before,
                admission=admission,
                beliefs=beliefs,
                known_pair_link_costs=planning_links,
                branch_executor=lookahead_executor,
            )
        else:
            path = PipelinePath.MONTE_CARLO
            activation_reason = "explicit-production-monte-carlo-v5"
            detail = policy.select_monte_carlo(
                state=state_before,
                admission=admission,
                beliefs=beliefs,
                known_pair_link_costs=planning_links,
                root_seed=slot_input.root_seed,
                slot_id=slot_input.slot_id,
                decision_position=decision_position,
                flow_id=flow_id,
                rollout_workers=mc_workers,
                rollout_executor=rollout_executor,
            )

        state = detail.result.state_after
        expected_state = state_before.apply(
            detail.result.action,
            slot_input.configuration,
        )
        if state != expected_state:
            raise RuntimeError(
                "policy returned state containing more than its focal commit"
            )
        placements.append(
            HybridPlacement(
                decision_position=decision_position,
                flow=flow,
                activation=activation,
                path=path,
                activation_reason=activation_reason,
                action=detail.result.action,
                skipped_stage=detail.result.action.skipped_stage(
                    slot_input.configuration
                ),
                state_before=state_before,
                state_after=state,
                objective_value=detail.result.objective_value,
                candidate_accounting=_accounting_for_decision(detail),
                policy_detail=detail,
            )
        )
    return tuple(placements), state


def run_hybrid_slot(
    slot_input: HybridSlotInput,
    *,
    policy: IBGHybridPolicy | None = None,
    simulation_adapter: HybridSlotSimulationAdapter | None = None,
    policy_mode: str = HYBRID_SLOT_POLICY_LOOKAHEAD,
    mc_workers: int = DEFAULT_HYBRID_MC_WORKERS,
    lookahead_executor: Executor | None = None,
) -> HybridSlotResult:
    """Place all flows, then simulate, learn, and report one Hybrid slot.

    ``lookahead`` is the unchanged normal Hybrid mode.  ``mc`` is an explicit
    full-slot execution mode for the completed v5 production Monte Carlo
    selector; it is never selected by activation inputs.
    """

    if not isinstance(slot_input, HybridSlotInput):
        raise TypeError("slot_input must be HybridSlotInput")
    policy_mode = _require_slot_policy(policy_mode)
    mc_workers = _require_mc_workers(mc_workers)
    if (
        lookahead_executor is not None
        and policy_mode != HYBRID_SLOT_POLICY_LOOKAHEAD
    ):
        raise ValueError(
            "lookahead_executor is valid only for deterministic lookahead"
        )
    policy = policy or IBGHybridPolicy(
        slot_input.configuration,
        slot_input.parameters,
    )
    if policy.configuration != slot_input.configuration:
        raise ValueError("policy configuration does not match the slot input")
    if policy.parameters != slot_input.parameters:
        raise ValueError("policy parameters do not match the slot input")
    simulation_adapter = (
        simulation_adapter or InProcessHybridSimulationAdapter()
    )

    started_at = time.perf_counter()
    flow_order_seed = derive_flow_order_seed(
        slot_input.root_seed,
        slot_input.slot_id,
    )
    ordered_flow_ids = [flow.flow_id for flow in slot_input.flows]
    random.Random(flow_order_seed).shuffle(ordered_flow_ids)

    if policy_mode == HYBRID_SLOT_POLICY_MC:
        # One pool lives for the whole placement phase, avoiding twenty
        # process-start/shutdown cycles while keeping learning/simulation out
        # of worker processes.
        with ProcessPoolExecutor(max_workers=mc_workers) as rollout_executor:
            placement_tuple, state = _place_all_flows(
                slot_input=slot_input,
                policy=policy,
                policy_mode=policy_mode,
                mc_workers=mc_workers,
                ordered_flow_ids=ordered_flow_ids,
                lookahead_executor=None,
                rollout_executor=rollout_executor,
            )
    else:
        placement_tuple, state = _place_all_flows(
            slot_input=slot_input,
            policy=policy,
            policy_mode=policy_mode,
            mc_workers=mc_workers,
            ordered_flow_ids=ordered_flow_ids,
            lookahead_executor=lookahead_executor,
            rollout_executor=None,
        )
    actions_by_flow = {
        placement.flow.flow_id: placement.action
        for placement in placement_tuple
    }
    simulation_result = simulation_adapter.execute(
        root_seed=slot_input.root_seed,
        slot_id=slot_input.slot_id,
        actions_by_flow=actions_by_flow,
        final_loads=state,
        replicas=slot_input.replica_by_choice,
        measured_pair_latency_ms=slot_input.simulated_pair_latency_ms,
    )
    if not isinstance(simulation_result, HybridSimulationResult):
        raise TypeError(
            "simulation adapter must return HybridSimulationResult"
        )
    _validate_simulation_result(
        result=simulation_result,
        actions_by_flow=actions_by_flow,
        final_loads=state,
    )

    exact_header, exact_replicas = _make_exact_learning_replicas(slot_input)
    beliefs_before = _belief_snapshot(exact_replicas)
    exact_learning.apply_observations(
        simulation_result.observations,
        exact_replicas,
    )
    beliefs_after = _belief_snapshot(exact_replicas)
    metrics = _compute_metrics(
        slot_input=slot_input,
        placements=placement_tuple,
        observations=simulation_result.observations,
        measured_pairs=simulation_result.measured_pairs,
        beliefs_before=beliefs_before,
        beliefs_after=beliefs_after,
        exact_header=exact_header,
        exact_replicas=exact_replicas,
        elapsed_seconds=0.0,
    )
    metrics = replace(
        metrics,
        elapsed_seconds=time.perf_counter() - started_at,
    )
    return HybridSlotResult(
        contract_version=HYBRID_POLICY_CONTRACT_VERSION,
        configuration=slot_input.configuration,
        parameters=slot_input.parameters,
        root_seed=slot_input.root_seed,
        slot_id=slot_input.slot_id,
        flow_order_seed_scheme=HYBRID_FLOW_ORDER_SEED_SCHEME,
        flow_order_seed=flow_order_seed,
        flow_order=tuple(ordered_flow_ids),
        placements=placement_tuple,
        final_loads=state,
        observations=simulation_result.observations,
        measured_pairs=simulation_result.measured_pairs,
        beliefs_before=beliefs_before,
        beliefs_after=beliefs_after,
        metrics=metrics,
    )


def run_and_print_hybrid_slot(
    slot_input: HybridSlotInput,
    *,
    policy: IBGHybridPolicy | None = None,
    simulation_adapter: HybridSlotSimulationAdapter | None = None,
    policy_mode: str = HYBRID_SLOT_POLICY_LOOKAHEAD,
    mc_workers: int = DEFAULT_HYBRID_MC_WORKERS,
    iteration: int = 1,
) -> HybridSlotResult:
    result = run_hybrid_slot(
        slot_input,
        policy=policy,
        simulation_adapter=simulation_adapter,
        policy_mode=policy_mode,
        mc_workers=mc_workers,
    )
    print(format_hybrid_slot_metrics(result, iteration=iteration))
    return result


def make_default_hybrid_slot_input(
    *,
    root_seed: int = 2050,
    slot_id: int = 1,
    beliefs: Mapping[ReplicaChoice, BeliefVector] | None = None,
) -> HybridSlotInput:
    """Construct the authoritative 20x3x10 Phase 5 simulation input."""

    configuration = HybridConfiguration()
    parameters = DEFAULT_HYBRID_POLICY_PARAMETERS
    default_belief = (0.25, 0.25, 0.25, 0.25)
    replicas = tuple(
        HybridReplica(
            choice=choice,
            belief=default_belief if beliefs is None else beliefs[choice],
            ready=True,
            max_assigned_flows=configuration.num_flows,
            hidden_state=((choice.stage + choice.replica - 2) % 4) + 1,
        )
        for choice in (
            ReplicaChoice(stage, replica)
            for stage in range(1, configuration.num_stages + 1)
            for replica in range(1, configuration.num_replicas + 1)
        )
    )
    pair_identities = tuple(
        (ReplicaChoice(stage_a, replica_a), ReplicaChoice(stage_b, replica_b))
        for stage_a, stage_b in combinations(
            range(1, configuration.num_stages + 1),
            2,
        )
        for replica_a, replica_b in product(
            range(1, configuration.num_replicas + 1),
            repeat=2,
        )
    )
    planning = tuple(
        HybridPairValue(
            source=source,
            target=target,
            latency_ms=(
                0.25 * (target.stage - source.stage)
                + 0.01 * abs(target.replica - source.replica)
            ),
        )
        for source, target in pair_identities
    )
    measured = tuple(
        HybridPairValue(
            source=source,
            target=target,
            latency_ms=(
                1.0
                + 0.5 * (target.stage - source.stage)
                + 0.02 * ((source.replica + target.replica) % 5)
            ),
        )
        for source, target in pair_identities
    )
    return HybridSlotInput(
        configuration=configuration,
        parameters=parameters,
        root_seed=root_seed,
        slot_id=slot_id,
        flows=tuple(
            HybridFlow(flow_id)
            for flow_id in range(1, configuration.num_flows + 1)
        ),
        replicas=replicas,
        planning_pair_links=planning,
        simulated_pair_outcomes=measured,
        initial_loads=GlobalLoadState.empty(configuration),
    )
