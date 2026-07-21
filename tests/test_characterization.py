import random
from functools import lru_cache
from itertools import product

import numpy as np
import pandas as pd
import pytest

from claude import BREIBGPolicy, br_eibg_exact
from header import (
    GLOBAL_BELIEF_RETENTION,
    Replica,
    aggregate_utility_per_flow,
    aggregate_utility_total,
    embedding,
    is_equilibrium,
    jain_index,
)
from latency_model import latency_likelihood
from learning import apply_observations
from ports import Observation
from report import SLA_v


def make_replica(stage=1, replica=1, *, gamma=0.2, state=4, capacity=2000):
    return Replica(
        stage=stage,
        replica=replica,
        belief=[0.25, 0.25, 0.25, 0.25],
        delay=25,
        cost=1,
        gamma=gamma,
        state=state,
        capacity=capacity,
    )


def test_utility_kernel_and_expected_utility_are_characterized():
    replica = make_replica()

    assert replica.utility_kernel(2, 5.0) == pytest.approx(94.0)
    assert replica.eval_util(2, [4.0, 5.0, 6.0]) == pytest.approx(94.0)


def test_seeded_br_eibg_and_embedding_are_characterized():
    random.seed(1234)
    np.random.seed(1234)
    replicas = {
        (1, 1): make_replica(replica=1, gamma=0.2, state=4, capacity=2000),
        (1, 2): make_replica(replica=2, gamma=0.3, state=2, capacity=5000),
    }
    flows = [1, 2, 3]

    policy, utility_grid = br_eibg_exact(flows, replicas, 0.8, 1, 2)
    embed, last_embed = embedding(
        policy,
        2,
        {"f_1": [], "f_2": [], "f_3": []},
        flows,
    )

    np.testing.assert_allclose(
        utility_grid.to_numpy(),
        [
            [71.90248064746864, 67.83006845656784, 52.944750553458405],
            [72.57688129310978, 66.13598685091296, 53.98056517418372],
        ],
    )
    assert embed == {"f_1": [2], "f_2": [1], "f_3": [1]}
    assert last_embed == {1: 2, 2: 1, 3: 1}


def test_br_eibg_uses_continuation_play_instead_of_myopic_utility():
    utility_grid = pd.DataFrame(
        [[2.0, 1.0, 1.0], [3.0, 2.0, 1.0]],
        index=[1, 2],
        columns=[1, 2, 3],
    )
    policy = BREIBGPolicy(utility_grid)

    action, predicted_final_loads = policy.solve_state((0, 0))

    assert utility_grid.loc[2, 1] > utility_grid.loc[1, 1]
    assert action == 1
    assert predicted_final_loads == (1, 2)
    assert policy[(1, 0)] == 2
    assert policy[(1, 1)] == 2
    assert policy.cache_info().hits > 0


def test_br_eibg_memoizes_the_three_flow_five_replica_state_space():
    utility_grid = pd.DataFrame(
        [
            [8.0, 5.0, 2.0],
            [7.5, 5.5, 2.5],
            [7.0, 6.0, 3.0],
            [6.5, 5.0, 4.0],
            [6.0, 4.5, 3.5],
        ],
        index=[1, 2, 3, 4, 5],
        columns=[1, 2, 3],
    )
    policy = BREIBGPolicy(utility_grid)

    action, predicted_final_loads = policy.solve_state((0, 0, 0, 0, 0))
    cache = policy.cache_info()

    assert action in {1, 2, 3, 4, 5}
    assert sum(predicted_final_loads) == 3
    assert cache.misses == 56
    assert cache.hits > 0


def _tuple_state_reference(utility_grid, num_replica_slots, loads):
    """Original tuple-state BR_EIBG recurrence for encoding equivalence."""
    replica_ids = tuple(sorted(int(value) for value in utility_grid.index))
    utilities = utility_grid.loc[list(replica_ids)].to_numpy(dtype=float)
    num_players = len(utility_grid.columns)

    @lru_cache(maxsize=None)
    def solve(loads):
        if sum(loads) == num_players:
            return 0, loads

        best_replica = None
        best_final_loads = None
        best_utility = -np.inf
        for row, replica_id in enumerate(replica_ids):
            next_loads = list(loads)
            replica_position = replica_id - 1
            next_loads[replica_position] += 1
            _, final_loads = solve(tuple(next_loads))
            current_utility = utilities[
                row,
                final_loads[replica_position] - 1,
            ]
            if (
                current_utility > best_utility
                or (
                    current_utility == best_utility
                    and (
                        best_replica is None
                        or replica_id < best_replica
                    )
                )
            ):
                best_replica = replica_id
                best_final_loads = final_loads
                best_utility = current_utility
        return best_replica, best_final_loads

    assert len(loads) == num_replica_slots
    return solve(tuple(loads))


def test_br_eibg_packed_cache_preserves_tuple_recurrence_and_sparse_slots():
    utility_grid = pd.DataFrame(
        [
            [-1.0, -3.0, -5.0],
            [-1.0, -3.0, -5.0],
            [-2.0, -2.0, -2.0],
        ],
        index=[1, 3, 5],
        columns=[1, 2, 3],
    )
    policy = BREIBGPolicy(utility_grid, num_replica_slots=5)

    for loads in product(range(4), repeat=5):
        if sum(loads) > 3:
            continue
        assert policy.solve_state(loads) == _tuple_state_reference(
            utility_grid,
            5,
            loads,
        )


def test_br_eibg_policy_can_release_its_exact_stage_cache_promptly():
    utility_grid = pd.DataFrame(
        [[3.0, 2.0], [2.0, 1.0]],
        index=[1, 2],
        columns=[1, 2],
    )
    policy = BREIBGPolicy(utility_grid)
    policy.solve_state((0, 0))

    assert policy.cache_info().currsize > 0

    policy.clear_cache()

    assert policy.cache_info().currsize == 0


def test_belief_update_and_aggregation_are_characterized():
    selected = make_replica(replica=1)
    unselected = make_replica(replica=2)
    likelihood = [0.1, 0.2, 0.3, 0.4]
    replicas = {(1, 1): selected, (1, 2): unselected}

    assert selected.local_update(likelihood, signal=12.0) == likelihood
    apply_observations(
        [
            Observation(1, 1, 1, 2, 12.0, tuple(likelihood)),
            Observation(1, 2, 1, 2, 12.0, tuple(likelihood)),
        ],
        replicas,
    )

    assert GLOBAL_BELIEF_RETENTION == 0.8
    assert selected.belief == [0.22, 0.24, 0.26, 0.28]
    assert unselected.belief == [0.25, 0.25, 0.25, 0.25]


def test_signal_likelihood_is_characterized():
    posterior = latency_likelihood(18.0, load=1)

    np.testing.assert_allclose(
        posterior,
        [0.0, 0.0, 0.9438503105630781, 0.05614968943692187],
        rtol=1e-7,
    )


def test_metrics_are_characterized():
    utility_grid = pd.DataFrame(
        [[8, 6, 4], [7, 5, 3]],
        index=[1, 2],
        columns=[1, 2, 3],
    )
    last_embed = {1: 1, 2: 1, 3: 2}

    aggregate = aggregate_utility_total(utility_grid, last_embed, 0)
    per_flow = aggregate_utility_per_flow(
        last_embed,
        utility_grid,
        {1: [], 2: [], 3: []},
    )
    fairness = jain_index(per_flow, aggregate)

    assert aggregate == 19
    assert per_flow == {1: 6.0, 2: 6.0, 3: 7.0}
    assert fairness == pytest.approx(0.9944903581267218)


def test_sla_and_equilibrium_rules_are_characterized():
    replicas = {(1, 1): make_replica(stage=1, state=4)}

    assert SLA_v({1: 111.0, 2: 110.0}, threshold_ms=110.0) == 1
    assert is_equilibrium(replicas, [[0.24] * 4]) == 1
    assert is_equilibrium(replicas, [[0.218] * 4]) == 1
    assert is_equilibrium(replicas, [[0.217] * 4]) == 0
    assert is_equilibrium(replicas, [[0.1] * 4]) == 0
