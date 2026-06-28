import random

import numpy as np
import pandas as pd
import pytest

from claude import backward_d_memoized_simple
from header import (
    Replica,
    aggregate_utility_per_flow,
    aggregate_utility_total,
    embedding,
    is_equilibrium,
    jain_index,
    pdf_cal,
    update,
)
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

    assert replica.utility_kernel(2, 5.0) == pytest.approx(9.285714285714286)
    assert replica.eval_util(2, [4.0, 5.0, 6.0]) == pytest.approx(9.682539682539684)


def test_seeded_solver_and_embedding_are_characterized():
    random.seed(1234)
    np.random.seed(1234)
    replicas = {
        (1, 1): make_replica(replica=1, gamma=0.2, state=4, capacity=2000),
        (1, 2): make_replica(replica=2, gamma=0.3, state=2, capacity=5000),
    }
    flows = [1, 2, 3]

    policy, utility_grid = backward_d_memoized_simple(flows, replicas, 0.8, 1, 2)
    embed, last_embed = embedding(
        policy,
        2,
        {"f_1": [], "f_2": [], "f_3": []},
        flows,
    )

    np.testing.assert_allclose(
        utility_grid.to_numpy(),
        [
            [8.052992351812803, 6.188279158696687, 4.789744263859601],
            [8.12865493638177, 5.667032135810186, 3.9827639038401594],
        ],
    )
    assert embed == {"f_1": [2], "f_2": [1], "f_3": [1]}
    assert last_embed == {1: 2, 2: 1, 3: 1}


def test_belief_update_and_aggregation_are_characterized():
    selected = make_replica(replica=1)
    unselected = make_replica(replica=2)
    likelihood = [0.1, 0.2, 0.3, 0.4]
    selected.tasting = lambda congestion: (4, likelihood)
    replicas = {(1, 1): selected, (1, 2): unselected}

    assert selected.local_update(likelihood, signal=4) == likelihood
    update({1: 1, 2: 1}, 2, 1, replicas, likelihood=0.8)

    assert selected.belief == [0.19, 0.23, 0.27, 0.31]
    assert unselected.belief == [0.25, 0.25, 0.25, 0.25]


def test_signal_likelihood_is_characterized():
    state, posterior = pdf_cal(1.0)

    assert state == 3
    np.testing.assert_allclose(
        posterior,
        [0.20826038, 0.25991709, 0.28627025, 0.24555228],
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
    replicas = {
        (1, 1): make_replica(stage=1, state=4),
        (2, 1): make_replica(stage=2, state=1),
        (3, 1): make_replica(stage=3, state=4),
    }

    assert SLA_v({"f_1": [1, 1, 1]}, replicas) == 1
    assert is_equilibrium(replicas, [[0.24] * 4] * 3) == 1
    assert is_equilibrium(replicas, [[0.1] * 4] * 3) == 0
