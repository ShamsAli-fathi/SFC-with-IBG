import os
import subprocess
import sys
from pathlib import Path

import pytest

from IBG_Hybrid import (
    FeasibilityResult,
    GlobalLoadState,
    HYBRID_STAGE_BUDGET,
    HybridConfiguration,
    ReplicaChoice,
    TwoStageAction,
)
from IBG_Hybrid.budgeted import (
    backward_budgeted_rollout,
    embedding_budgeted,
    require_hybrid_stage_budget,
)
from IBG_Hybrid.main import DEFAULT_CONFIGURATION
from IBG_Hybrid.oracle import (
    enumerate_two_stage_actions,
    solve_tiny_exhaustive,
)


ROOT = Path(__file__).resolve().parents[1]


def action(*pairs):
    return TwoStageAction(
        tuple(ReplicaChoice(stage, replica) for stage, replica in pairs)
    )


def test_default_configuration_is_20x3x10_with_l2():
    assert HYBRID_STAGE_BUDGET == 2
    assert DEFAULT_CONFIGURATION == HybridConfiguration(
        num_flows=20,
        num_stages=3,
        num_replicas=10,
        stage_budget=2,
    )


def test_two_stage_action_requires_distinct_canonical_stages():
    selected = action((1, 3), (3, 2))

    assert selected.stages == (1, 3)

    with pytest.raises(ValueError, match="exactly 2"):
        TwoStageAction((ReplicaChoice(1, 1),))
    with pytest.raises(ValueError, match="distinct stages"):
        action((1, 1), (1, 2))
    with pytest.raises(ValueError, match="in increasing stage order"):
        action((3, 1), (1, 1))


def test_action_rejects_replica_ids_outside_configuration():
    configuration = HybridConfiguration(num_flows=1, num_replicas=2)

    with pytest.raises(ValueError, match="replica 3 exceeds"):
        action((1, 3), (2, 1)).validate_for(configuration)


def test_skipped_stage_is_absent_and_only_selected_loads_change():
    configuration = HybridConfiguration(num_flows=1, num_replicas=2)
    initial = GlobalLoadState.empty(configuration)
    selected = action((1, 2), (3, 1))

    updated = initial.apply(selected, configuration)

    assert selected.skipped_stage(configuration) == 2
    assert initial.loads == ((0, 0), (0, 0), (0, 0))
    assert updated.loads == ((0, 1), (0, 0), (1, 0))
    assert updated.total_assignments == HYBRID_STAGE_BUDGET


def test_unsupported_budget_is_rejected_at_every_phase1_boundary():
    with pytest.raises(ValueError, match="exactly L=2"):
        require_hybrid_stage_budget(3)
    with pytest.raises(ValueError, match="exactly L=2"):
        HybridConfiguration(stage_budget=3)
    with pytest.raises(ValueError, match="exactly L=2"):
        backward_budgeted_rollout(
            flow_list=[],
            replica_list={},
            num_of_stages=3,
            num_of_replicas=1,
            stage_budget=3,
        )
    with pytest.raises(ValueError, match="exactly L=2"):
        embedding_budgeted(
            policy={},
            num_of_stages=3,
            num_of_replicas=1,
            flow_list=[],
            stage_budget=3,
        )


def test_oracle_enumeration_and_tie_breaking_are_deterministic():
    configuration = HybridConfiguration(num_flows=1, num_replicas=2)
    actions = tuple(enumerate_two_stage_actions(configuration))

    assert len(actions) == 12
    assert actions[0] == action((1, 1), (2, 1))
    assert actions[-1] == action((2, 2), (3, 2))

    result = solve_tiny_exhaustive(
        configuration,
        GlobalLoadState.empty(configuration),
        remaining_flows=1,
        action_value=lambda _action, _state: 0.0,
    )

    assert result.action == actions[0]
    assert result.evaluated_actions == 12
    assert result.feasible_actions == 12


def test_oracle_uses_coupled_continuation_from_global_loads():
    configuration = HybridConfiguration(num_flows=2, num_replicas=1)
    initial = GlobalLoadState.empty(configuration)
    stage_12 = action((1, 1), (2, 1))
    stage_13 = action((1, 1), (3, 1))
    after_12 = initial.apply(stage_12, configuration)
    after_13 = initial.apply(stage_13, configuration)

    def value(candidate, state):
        if state == initial:
            return {
                stage_12: 5.0,
                stage_13: 4.0,
            }.get(candidate, 0.0)
        if state == after_12:
            return 0.0
        if state == after_13 and candidate == stage_12:
            return 10.0
        return 0.0

    result = solve_tiny_exhaustive(
        configuration,
        initial,
        remaining_flows=2,
        action_value=value,
    )

    assert result.action == stage_13
    assert result.objective_value == 14.0
    assert result.state_after == after_13


def test_oracle_respects_explicit_feasibility_results():
    configuration = HybridConfiguration(num_flows=1, num_replicas=1)
    allowed = action((2, 1), (3, 1))

    def feasibility(candidate, _state):
        if candidate == allowed:
            return FeasibilityResult.accepted()
        return FeasibilityResult.rejected("fixture capacity")

    result = solve_tiny_exhaustive(
        configuration,
        GlobalLoadState.empty(configuration),
        remaining_flows=1,
        action_value=lambda _action, _state: 0.0,
        feasibility_check=feasibility,
    )

    assert result.action == allowed
    assert result.feasible_actions == 1
    assert result.feasibility == FeasibilityResult.accepted()


def test_oracle_refuses_the_production_20x3x10_problem():
    configuration = HybridConfiguration()
    initial = GlobalLoadState.empty(configuration)

    with pytest.raises(ValueError, match="test-only"):
        solve_tiny_exhaustive(
            configuration,
            initial,
            remaining_flows=configuration.num_flows,
            action_value=lambda _action, _state: 0.0,
        )
    with pytest.raises(ValueError, match="actions per state"):
        solve_tiny_exhaustive(
            configuration,
            initial,
            remaining_flows=1,
            action_value=lambda _action, _state: 0.0,
        )


def test_importing_hybrid_modules_has_no_output_or_file_side_effects(tmp_path):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["MPLCONFIGDIR"] = str(tmp_path / "matplotlib")
    modules = (
        "IBG_Hybrid",
        "IBG_Hybrid.budgeted",
        "IBG_Hybrid.claude",
        "IBG_Hybrid.contracts",
        "IBG_Hybrid.header",
        "IBG_Hybrid.header_b",
        "IBG_Hybrid.main",
        "IBG_Hybrid.oracle",
        "IBG_Hybrid.report",
    )
    command = "; ".join(f"import {module}" for module in modules)

    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert list(tmp_path.iterdir()) == []
