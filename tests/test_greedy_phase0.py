from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Greedy.legacy_characterization import (
    LEGACY_CALLABLE_CLASSIFICATIONS,
    LegacyDisposition,
    characterize_legacy_sources,
)
from Greedy.phase0_contract import (
    CANONICAL_DECISION_FIXTURES,
    CANONICAL_COMPARISON_TOPOLOGY_FIXTURE,
    CANONICAL_SLOT_FIXTURE,
    EXCLUDED_SELECTION_FEATURES,
    GREEDY_EQUILIBRIUM_THRESHOLD,
    GREEDY_ACTION_SCORE_MODE,
    GREEDY_CANONICAL_COMPARISON_FLOW_COUNT,
    GREEDY_CANONICAL_COMPARISON_REPLICAS_PER_STAGE,
    GREEDY_CANONICAL_COMPARISON_STAGE_COUNT,
    GREEDY_HYBRID_COMPATIBILITY_MATRIX,
    GREEDY_OBSERVATION_JITTER_MODE,
    GREEDY_OUTCOME_LATENCY_MODE,
    GREEDY_PHYSICAL_JITTER_MODE,
    GREEDY_POLICY_CONTRACT_VERSION,
    GREEDY_RUNS_PER_INVOCATION,
    GREEDY_REQUIRED_DIMENSION_OPTIONS,
    GREEDY_REQUIRES_EXPLICIT_DIMENSIONS,
    GREEDY_SELECTION_BUDGET,
    GREEDY_SLA_LATENCY_THRESHOLD_MS,
    GREEDY_SUPPORTS_RUNS_OPTION,
    OBSERVATION_JITTER_MS_BY_STATE,
    PHYSICAL_JITTER_MS_BY_STATE,
    POLICY_FORBIDDEN_INPUT_FIELDS,
    POLICY_VISIBLE_INPUT_FIELDS,
    SEQUENTIAL_LOAD_FIXTURE,
    SMALL_HAND_CHECKED_TOPOLOGY_FIXTURE,
    CompatibilityDisposition,
    GreedyTopologyFixture,
    raw_end_to_end_sla_fixture,
    strict_equilibrium_fixture,
)
from IBG import latency_model
from IBG.learning import apply_observations
from IBG.outcome_latency import outcome_latency_ms_per_flow
from IBG.report import SLA_v
from IBG_Hybrid.expected_utility import expected_stage_utility_from_belief


LEGACY_ROOT = ROOT / "Greedy"


def _load_legacy_module(filename: str):
    path = LEGACY_ROOT / filename
    spec = importlib.util.spec_from_file_location(f"greedy_phase0_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase0_contract_version_dimensions_capacity_and_counts():
    assert GREEDY_POLICY_CONTRACT_VERSION == "pure-greedy-budgeted-l2-v1"
    assert GREEDY_SELECTION_BUDGET == 2
    assert GREEDY_ACTION_SCORE_MODE == "sum-immediate-expected-stage-utility-v1"
    assert SMALL_HAND_CHECKED_TOPOLOGY_FIXTURE.stages == (1, 2, 3)
    assert SMALL_HAND_CHECKED_TOPOLOGY_FIXTURE.admission_capacity_per_replica == 2
    assert SMALL_HAND_CHECKED_TOPOLOGY_FIXTURE.expected_route_count == 3
    assert SMALL_HAND_CHECKED_TOPOLOGY_FIXTURE.expected_selected_observation_count == 6
    assert SMALL_HAND_CHECKED_TOPOLOGY_FIXTURE.expected_consecutive_pair_count == 3
    assert SMALL_HAND_CHECKED_TOPOLOGY_FIXTURE.bypassed_stages_per_action == 1
    assert GreedyTopologyFixture(5, 3, 2).admission_capacity_per_replica == 3
    with pytest.raises(ValueError, match="positive"):
        GreedyTopologyFixture(0, 2, 1)
    with pytest.raises(TypeError, match="integer"):
        GreedyTopologyFixture(True, 2, 1)
    with pytest.raises(ValueError, match="two-stage"):
        GreedyTopologyFixture(1, 1, 1)


def test_phase0_dimensions_are_explicit_and_10x3x5_is_comparison_only():
    assert GREEDY_REQUIRES_EXPLICIT_DIMENSIONS is True
    assert GREEDY_REQUIRED_DIMENSION_OPTIONS == ("--flow", "--stage", "--replica")
    assert (
        GREEDY_CANONICAL_COMPARISON_FLOW_COUNT,
        GREEDY_CANONICAL_COMPARISON_STAGE_COUNT,
        GREEDY_CANONICAL_COMPARISON_REPLICAS_PER_STAGE,
    ) == (10, 3, 5)
    assert CANONICAL_COMPARISON_TOPOLOGY_FIXTURE == GreedyTopologyFixture(10, 3, 5)
    assert CANONICAL_COMPARISON_TOPOLOGY_FIXTURE.admission_capacity_per_replica == 2
    assert CANONICAL_COMPARISON_TOPOLOGY_FIXTURE.expected_route_count == 10
    assert CANONICAL_COMPARISON_TOPOLOGY_FIXTURE.expected_selected_observation_count == 20
    assert CANONICAL_COMPARISON_TOPOLOGY_FIXTURE.expected_consecutive_pair_count == 10
    assert CANONICAL_COMPARISON_TOPOLOGY_FIXTURE.bypassed_stages_per_action == 1
    assert GREEDY_RUNS_PER_INVOCATION == 1
    assert GREEDY_SUPPORTS_RUNS_OPTION is False


def test_phase0_decision_fixtures_freeze_projected_load_ties_nonpositive_and_failure():
    for fixture in CANONICAL_DECISION_FIXTURES:
        for action, _score in fixture.scores_at_projected_load:
            assert fixture.projected_loads_for(action) == tuple(
                (identity, dict(fixture.current_loads)[identity] + 1)
                for identity in action
            )
        fixture.assert_contract_winner()
    by_name = {fixture.name: fixture for fixture in CANONICAL_DECISION_FIXTURES}
    assert by_name["lowest-canonical-action-exact-tie"].expected_action == (
        (1, 1),
        (2, 1),
    )
    assert by_name["best-non-positive-is-still-selected"].expected_action == (
        (1, 1),
        (3, 1),
    )
    assert by_name["empty-feasible-set-fails"].expected_failure == "no-feasible-action"


def test_phase0_sequential_load_and_complete_slot_schema_fixtures():
    for step in SEQUENTIAL_LOAD_FIXTURE:
        step.assert_single_sequential_action_mutation()
    CANONICAL_SLOT_FIXTURE.assert_complete()
    assert tuple(step.flow_id for step in SEQUENTIAL_LOAD_FIXTURE) == (2, 1, 3)
    assert tuple(
        tuple(stage for stage, _replica in route)
        for _flow, route in CANONICAL_SLOT_FIXTURE.routes
    ) == ((1, 3), (1, 2), (2, 3))
    assert CANONICAL_SLOT_FIXTURE.bypassed_stages == (
        (2, (2,)),
        (1, (3,)),
        (3, (1,)),
    )


def test_phase0_policy_input_and_exclusion_boundary_is_explicit():
    assert POLICY_VISIBLE_INPUT_FIELDS.isdisjoint(POLICY_FORBIDDEN_INPUT_FIELDS)
    assert {"hidden_state", "profile_seed"} <= POLICY_FORBIDDEN_INPUT_FIELDS
    assert {
        "recursion",
        "future-flow-simulation",
        "candidate-pruning",
        "lookahead",
        "monte-carlo",
        "milp",
        "link-cost-selection-term",
    } <= EXCLUDED_SELECTION_FEATURES
    assert "budgeted-action" not in EXCLUDED_SELECTION_FEATURES
    assert "cross-stage-objective" not in EXCLUDED_SELECTION_FEATURES


def test_legacy_static_characterization_finds_unsafe_driver_dimensions_rng_and_csv():
    result = characterize_legacy_sources()
    assert result.experiment_loop_range == (1, 30)
    assert result.hard_coded_flow_count == 50
    assert result.hard_coded_stage_count == 3
    assert result.hard_coded_replica_count == 80
    assert result.hard_coded_total_replica_count == 240
    assert result.active_budgeted_flag == 1
    assert "main.py" in result.import_time_execution_files
    assert "test.py" in result.import_time_execution_files
    assert "random.shuffle" in result.global_random_calls
    assert "random.choices" in result.global_random_calls
    assert "np.random.normal" in result.global_random_calls
    assert "np.random.choice" in result.global_random_calls
    assert "uuid.uuid4" in result.global_random_calls
    assert result.explicit_seed_calls == ()
    assert {"header.py", "main.py", "report.py", "test.py"} <= set(result.csv_write_files)


def test_every_legacy_top_level_callable_has_an_explicit_disposition():
    result = characterize_legacy_sources()
    assert set(LEGACY_CALLABLE_CLASSIFICATIONS) == set(result.top_level_callable_names)
    assert {entry.disposition for entry in LEGACY_CALLABLE_CLASSIFICATIONS.values()} == {
        LegacyDisposition.REUSE_WITH_COMPATIBILITY_TESTS,
        LegacyDisposition.REFERENCE_ONLY,
        LegacyDisposition.RETIRE,
    }


def test_phase0_modules_import_silently_without_writes(tmp_path):
    code = "import Greedy.phase0_contract; import Greedy.legacy_characterization"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={"PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_legacy_budgeted_path_selects_exactly_two_stages(monkeypatch):
    legacy = _load_legacy_module("budgeted.py")
    replicas = {
        (stage, 1): SimpleNamespace(stage=stage, replica=1)
        for stage in range(1, 4)
    }

    def deterministic_grids(**_kwargs):
        return {
            1: (np.array([[3.0]]), None, [replicas[(1, 1)]]),
            2: (np.array([[2.0]]), None, [replicas[(2, 1)]]),
            3: (np.array([[1.0]]), None, [replicas[(3, 1)]]),
        }

    monkeypatch.setattr(legacy, "build_utility_grids_budgeted", deterministic_grids)
    policy, _grids = legacy.backward_budgeted_memoized(
        flow_list=[1],
        replica_list=replicas,
        num_of_stages=3,
        num_of_replicas=1,
    )
    routes, loads = legacy.embedding_budgeted(policy, 3, 1, [1])

    assert routes == {1: [(1, 1), (2, 1)]}
    assert len(routes[1]) == 2
    assert loads == (1, 1, 0)


def test_legacy_dormant_path_returns_zero_and_embedding_mutates_last_load():
    legacy_solver = _load_legacy_module("claude.py")
    legacy_header = _load_legacy_module("header.py")

    class NegativeReplica:
        def __init__(self, replica):
            self.stage = 1
            self.replica = replica
            self.belief = [0.25] * 4

        def eval_util(self, _load, _samples):
            return -1.0

    replicas = {(1, replica): NegativeReplica(replica) for replica in (1, 2)}
    policy, _grid = legacy_solver.backward_d_memoized_simple(
        [1, 2], replicas, 0.8, 1, 2
    )
    assert policy[(0, 0)] == 0

    class RecordingZeroPolicy:
        def __init__(self):
            self.states = []

        def __getitem__(self, state):
            self.states.append(state)
            return 0

    zero_policy = RecordingZeroPolicy()
    embeds = {"f_1": [], "f_2": []}
    _embed_dict, last = legacy_header.embedding(zero_policy, 2, embeds, [1, 2])

    assert zero_policy.states == [(0, 0), (0, 1)]
    assert last == {1: 0, 2: 0}


def test_legacy_historical_utility_sla_equilibrium_and_csv_behavior():
    legacy = _load_legacy_module("header.py")
    replica = legacy.Replica(1, 1, [0.25] * 4, 25, 1, 0.2, 4, 5_000)
    assert replica.utility_kernel(2, 10.0) == pytest.approx(100 / (10 * 1.4) - 5)
    assert legacy.SLA_v_b_v2({1: 15.0, 2: 15.25, 3: 17.0}) == pytest.approx(2.25)

    replicas = {(1, 1): SimpleNamespace(belief=[0.31, 0.25, 0.25, 0.19])}
    before = [[0.25, 0.25, 0.25, 0.25]]
    assert legacy.is_equilibrium(replicas, before) == 0
    assert legacy.is_equilibrium(replicas, before, threshold=0.061) == 1

    characterization = characterize_legacy_sources()
    assert "report.py" in characterization.csv_write_files
    assert "test.py" in characterization.csv_write_files


def test_active_jitter_likelihood_learning_outcome_sla_fairness_and_equilibrium_compatibility():
    import header as exact_header

    assert GREEDY_PHYSICAL_JITTER_MODE == latency_model.JITTER_DISTRIBUTION
    assert GREEDY_OBSERVATION_JITTER_MODE == latency_model.OBSERVATION_JITTER_DISTRIBUTION
    assert PHYSICAL_JITTER_MS_BY_STATE == tuple(
        latency_model.CALIBRATED_STATE_PARAMETERS[state].jitter_ms
        for state in range(1, 5)
    )
    assert OBSERVATION_JITTER_MS_BY_STATE == tuple(
        latency_model.OBSERVATION_JITTER_MS_BY_STATE[state]
        for state in range(1, 5)
    )
    signal = 55.0
    likelihood = latency_model.learning_signal_likelihood(signal, load=1)
    assert sum(likelihood) == pytest.approx(1.0)
    assert all(
        latency_model.learning_signal_pdf(signal, 1, state) >= 0
        for state in range(1, 5)
    )

    class LearningReplica:
        def __init__(self):
            self.belief = [0.25] * 4
            self.updates = 0

        def local_update(self, likelihood_values, _signal):
            self.updates += 1
            return list(likelihood_values)

        def aggregation(self, beliefs):
            self.belief = list(beliefs[0])

    selected = LearningReplica()
    unselected = LearningReplica()
    observation = SimpleNamespace(
        stage=1,
        replica_id=1,
        likelihood=(0.1, 0.2, 0.3, 0.4),
        signal=55.0,
    )
    apply_observations([observation], {(1, 1): selected, (1, 2): unselected})
    assert selected.updates == 1
    assert unselected.updates == 0

    physical = {1: 30.0, 2: 40.0}
    pair = {1: 10.0, 2: 20.0}
    assert GREEDY_OUTCOME_LATENCY_MODE == "physical-only-v1"
    assert outcome_latency_ms_per_flow(physical, pair) == physical
    raw = {1: 80.0, 2: 80.000001, 3: 83.25}
    assert SLA_v(raw, GREEDY_SLA_LATENCY_THRESHOLD_MS) == 2
    assert raw_end_to_end_sla_fixture(raw) == pytest.approx((2, 3.250001))

    fairness_input = {1: [1.0], 2: [2.0], 3: [3.0]}
    assert exact_header.jain_index(fairness_input, 6.0) == pytest.approx(36 / 42)
    assert strict_equilibrium_fixture(0.039999) is True
    assert strict_equilibrium_fixture(GREEDY_EQUILIBRIUM_THRESHOLD) is False
    boundary_replicas = {(1, 1): SimpleNamespace(belief=[0.30, 0.25, 0.25, 0.20])}
    assert exact_header.is_equilibrium(
        boundary_replicas,
        [[0.25, 0.25, 0.25, 0.25]],
        threshold=GREEDY_EQUILIBRIUM_THRESHOLD,
    ) == 0


def test_expected_utility_compatibility_and_matrix_boundaries():
    belief = (0.1, 0.2, 0.3, 0.4)
    expected = sum(
        probability * latency_model.expected_state_utility(state, 2)
        for state, probability in enumerate(belief, start=1)
    )
    assert expected_stage_utility_from_belief(belief, 2) == pytest.approx(expected)

    by_component = {entry.component: entry for entry in GREEDY_HYBRID_COMPATIBILITY_MATRIX}
    assert by_component["physical and observation latency laws"].disposition is CompatibilityDisposition.REUSE
    assert by_component["belief-driven expected stage utility"].disposition is CompatibilityDisposition.ADAPT
    assert by_component[
        "Hybrid pruning, lookahead, Monte Carlo, and pair-aware selection"
    ].disposition is CompatibilityDisposition.EXCLUDE
