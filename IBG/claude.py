from functools import lru_cache

import numpy as np
import pandas as pd

from latency_model import sample_belief_latency_ms


class BREIBGPolicy:
    """Exact per-stage BR_EIBG policy for one-of-M replica selection.

    The paper presents the elementary recursion as choose/skip for one
    replica.  An SFC stage requires exactly one replica, so each subgame here
    branches over all active replicas.  The continuation game is memoized by
    its sufficient state: the current load vector (whose sum determines the
    next player index).
    """

    def __init__(self, utility_grid, num_replica_slots=None):
        if utility_grid.empty:
            raise ValueError("utility_grid must contain at least one replica")

        self.replica_ids = tuple(sorted(int(value) for value in utility_grid.index))
        if len(self.replica_ids) != len(set(self.replica_ids)):
            raise ValueError("utility_grid replica IDs must be unique")

        self.num_players = len(utility_grid.columns)
        if self.num_players < 1:
            raise ValueError("utility_grid must contain at least one player")
        if tuple(utility_grid.columns) != tuple(range(1, self.num_players + 1)):
            raise ValueError("utility_grid columns must be congestion levels 1..N")

        self.num_replica_slots = (
            max(self.replica_ids)
            if num_replica_slots is None
            else num_replica_slots
        )
        if self.num_replica_slots < max(self.replica_ids):
            raise ValueError("num_replica_slots does not cover every replica ID")
        if any(replica_id < 1 for replica_id in self.replica_ids):
            raise ValueError("replica IDs must be positive")

        ordered_grid = utility_grid.loc[list(self.replica_ids)]
        self._utilities = ordered_grid.to_numpy(dtype=float)
        if not np.isfinite(self._utilities).all():
            raise ValueError("utility_grid must contain only finite values")

        @lru_cache(maxsize=None)
        def solve(loads):
            if sum(loads) == self.num_players:
                return 0, loads

            best_replica = None
            best_final_loads = None
            best_utility = -np.inf

            for row, replica_id in enumerate(self.replica_ids):
                replica_position = replica_id - 1
                next_loads = list(loads)
                next_loads[replica_position] += 1
                _, final_loads = solve(tuple(next_loads))
                final_replica_load = final_loads[replica_position]
                current_utility = self._utilities[row, final_replica_load - 1]

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

        self._solve = solve

    def _normalize_loads(self, loads):
        normalized = tuple(loads)
        if len(normalized) != self.num_replica_slots:
            raise ValueError(
                f"load vector must contain {self.num_replica_slots} entries"
            )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, np.integer))
            or value < 0
            for value in normalized
        ):
            raise ValueError("load vector entries must be non-negative integers")
        if sum(normalized) > self.num_players:
            raise ValueError("load vector cannot contain more assignments than flows")
        return tuple(int(value) for value in normalized)

    def solve_state(self, loads):
        """Return the current SPNE action and predicted terminal load vector."""
        return self._solve(self._normalize_loads(loads))

    def cache_info(self):
        return self._solve.cache_info()

    def __getitem__(self, loads):
        replica_id, _ = self.solve_state(loads)
        return replica_id

    def get(self, loads, default=0):
        try:
            return self[loads]
        except (TypeError, ValueError):
            return default


def _sample_replica_latency(replica, load, sample_count=30):
    return np.asarray(
        [
            sample_belief_latency_ms(replica.belief, load)
            for _ in range(sample_count)
        ],
        dtype=float,
    )


def br_eibg_exact(
    flow_list,
    replica_list,
    likelihood,
    stage,
    num_of_replicas,
):
    """Build the exact memoized BR_EIBG policy for one decoupled stage.

    ``likelihood`` remains in the public signature for compatibility with the
    reference runner.  Expected utility is calculated from each replica's
    current belief and the existing Monte Carlo quality model.
    """
    del likelihood

    if not flow_list:
        raise ValueError("flow_list must contain at least one flow")
    if num_of_replicas < 1:
        raise ValueError("num_of_replicas must be at least 1")

    replicas_in_stage = sorted(
        (
            replica
            for replica in replica_list.values()
            if replica.stage == stage
        ),
        key=lambda replica: replica.replica,
    )
    if not replicas_in_stage:
        raise ValueError(f"stage {stage} must contain at least one replica")
    if any(replica.replica > num_of_replicas for replica in replicas_in_stage):
        raise ValueError("replica ID exceeds num_of_replicas")

    loads = np.arange(1, len(flow_list) + 1)
    utility_grid_values = np.zeros((len(replicas_in_stage), len(flow_list)))

    for row, replica in enumerate(replicas_in_stage):
        utility_grid_values[row, :] = [
            replica.eval_util(
                load,
                _sample_replica_latency(replica, load),
            )
            for load in loads
        ]

    utility_grid = pd.DataFrame(
        utility_grid_values,
        index=[replica.replica for replica in replicas_in_stage],
        columns=loads,
    )
    policy = BREIBGPolicy(
        utility_grid,
        num_replica_slots=num_of_replicas,
    )
    return policy, utility_grid


def backward_d_memoized_simple(
    flow_list,
    replica_list,
    likelihood,
    stage,
    num_of_replicas,
):
    """Compatibility wrapper for the former provisional solver name."""
    return br_eibg_exact(
        flow_list,
        replica_list,
        likelihood,
        stage,
        num_of_replicas,
    )
