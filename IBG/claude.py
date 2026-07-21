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

        # The exact recurrence has one subgame per load vector.  Store that
        # vector in a compact integer cache key rather than constructing a
        # list/tuple for every candidate transition.  The high field records
        # the number of assigned players, so the packed key still represents
        # precisely the same state as ``loads`` in the recurrence below.
        #
        # ``num_players`` is the largest possible load, hence this many bits
        # can represent every slot load from zero through ``num_players``.
        state_bits = max(1, self.num_players.bit_length())
        slot_shifts = tuple(
            state_bits * slot for slot in range(self.num_replica_slots)
        )
        state_digit_mask = (1 << state_bits) - 1
        assignment_count_shift = state_bits * self.num_replica_slots
        assignment_count_increment = 1 << assignment_count_shift
        load_vector_mask = assignment_count_increment - 1
        candidate_choices = tuple(
            (
                replica_id,
                1 << slot_shifts[replica_id - 1],
                slot_shifts[replica_id - 1],
                row,
            )
            for row, replica_id in enumerate(self.replica_ids)
        )
        # Keep the cache closure independent of ``self`` so the policy itself
        # is not retained through the recursive cache.  The recursive cache
        # wrapper still has a self-cycle, so callers clear its memo table once
        # stage placement has completed.
        num_players = self.num_players
        utilities = self._utilities

        @lru_cache(maxsize=None)
        def solve(packed_state):
            if (
                packed_state >> assignment_count_shift
            ) == num_players:
                return 0, packed_state & load_vector_mask

            best_replica = None
            best_final_load_vector = None
            best_utility = -np.inf

            for (
                replica_id,
                replica_increment,
                replica_shift,
                row,
            ) in candidate_choices:
                _, final_load_vector = solve(
                    packed_state
                    + replica_increment
                    + assignment_count_increment
                )
                final_replica_load = (
                    final_load_vector >> replica_shift
                ) & state_digit_mask
                current_utility = utilities[row, final_replica_load - 1]

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
                    best_final_load_vector = final_load_vector
                    best_utility = current_utility

            return best_replica, best_final_load_vector

        self._solve = solve
        self._state_bits = state_bits
        self._slot_shifts = slot_shifts
        self._state_digit_mask = state_digit_mask
        self._assignment_count_shift = assignment_count_shift

    def _pack_loads(self, loads):
        load_vector = sum(
            int(value) << shift
            for value, shift in zip(loads, self._slot_shifts)
        )
        return load_vector | (
            sum(loads) << self._assignment_count_shift
        )

    def _unpack_loads(self, packed_load_vector):
        return tuple(
            (packed_load_vector >> shift) & self._state_digit_mask
            for shift in self._slot_shifts
        )

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
        normalized_loads = self._normalize_loads(loads)
        replica_id, final_load_vector = self._solve(
            self._pack_loads(normalized_loads)
        )
        return replica_id, self._unpack_loads(final_load_vector)

    def cache_info(self):
        return self._solve.cache_info()

    def clear_cache(self):
        """Release this one-stage exact-policy memo table when placement ends.

        A policy is needed only while ``embedding`` resolves the ordered
        placements for its stage.  Its recursive ``lru_cache`` otherwise
        retains every exact subgame state through the next garbage-collection
        cycle, so callers that finish a stage should explicitly discard it.
        This affects cache lifetime only; it does not alter the recurrence,
        candidate set, or tie-breaking rule.
        """
        self._solve.cache_clear()

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
