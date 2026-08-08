"""Lean image copy of the frozen Exact functions used by Hybrid slots.

The implementations below are kept behavior-identical to their counterparts
in ``IBG/header.py``.  The legacy plotting, CSV, and truncated-normal helpers
are deliberately absent from the controller image.
"""

import numpy as np

from latency_model import DEFAULT_LATENCY_WEIGHT, DEFAULT_REWARD


GLOBAL_BELIEF_RETENTION = 0.8


class Replica:
    def __init__(
        self,
        stage,
        replica,
        belief,
        delay,
        cost,
        gamma,
        state,
        capacity,
        reward=DEFAULT_REWARD,
        latency_weight=DEFAULT_LATENCY_WEIGHT,
    ):
        self.stage = stage
        self.replica = replica
        self.belief = belief
        self.delay = delay
        self.cost = cost
        self.gamma = gamma
        self.weight = 1
        self.state = state
        self.capacity = capacity
        self.reward = reward
        self.latency_weight = latency_weight

    def utility_kernel(self, n, q):
        if n < 1:
            raise ValueError("load must be at least 1")
        if q <= 0:
            raise ValueError("latency q must be positive")
        return self.reward - (self.latency_weight * q) - self.cost

    def local_update(self, likelihood, signal):
        local_update_list = []
        for i in range(len(likelihood), 0, -1):
            numerator = self.belief[len(likelihood) - i] * likelihood[
                len(likelihood) - i
            ]
            denominator = (
                self.belief[len(likelihood) - 4]
                * likelihood[len(likelihood) - 4]
                + self.belief[len(likelihood) - 3]
                * likelihood[len(likelihood) - 3]
                + self.belief[len(likelihood) - 2]
                * likelihood[len(likelihood) - 2]
                + self.belief[len(likelihood) - 1]
                * likelihood[len(likelihood) - 1]
            )
            local_update_list.append(round((numerator / denominator), 3))
        return local_update_list

    def aggregation(self, beliefs):
        w = GLOBAL_BELIEF_RETENTION
        for i in range(0, len(beliefs[0])):
            b_temp = [sublist[i] for sublist in beliefs]
            f1 = w * self.belief[i]
            f2 = (1 - w) * (1 / len(b_temp)) * sum(b_temp)
            result = f1 + f2
            self.belief[i] = round(result, 3)


def is_equilibrium(replica_list, previous_belief_list, threshold=0.033):
    current_belief_list = [replica.belief for replica in replica_list.values()]
    differences = [
        [abs(b - a) for a, b in zip(prev_row, curr_row)]
        for prev_row, curr_row in zip(previous_belief_list, current_belief_list)
    ]
    if all(d < threshold for row in differences for d in row):
        return 1
    return 0


def jain_index(agg_util_per_flow, agg_util_total):
    for key in agg_util_per_flow:
        agg_util_per_flow[key] = round(float(np.sum(agg_util_per_flow[key])), 3)
    numerator = pow(agg_util_total, 2)
    denominator = len(agg_util_per_flow) * sum(
        value**2 for value in agg_util_per_flow.values()
    )
    return numerator / denominator
