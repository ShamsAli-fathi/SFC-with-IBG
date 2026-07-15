import random
import pandas as pd
import numpy as np
from itertools import product
import csv
import os
import sys
from collections import Counter
from scipy.stats import truncnorm

from latency_model import (
    DEFAULT_LATENCY_WEIGHT,
    DEFAULT_REWARD,
    estimate_state,
    latency_likelihood,
    require_state_parameters,
    sample_latency_ms,
)

sys.setrecursionlimit(1000)

GLOBAL_BELIEF_RETENTION = 0.8


class Replica:
    def __init__(self, stage, replica, belief, delay, cost, gamma, state,
                 capacity, reward=DEFAULT_REWARD,
                 latency_weight=DEFAULT_LATENCY_WEIGHT):
        self.stage = stage
        self.replica = replica
        self.belief = belief  # GOOD belief
        self.delay = delay  # q is Delay
        self.cost = cost  # cost of using the replica -> used for budgeted approach
        self.gamma = gamma  # how strongly congestion penalizes utility
        self.weight = 1
        self.state = state
        self.capacity = capacity
        self.reward = reward
        self.latency_weight = latency_weight

    def __repr__(self):
        return (f"Replica(stage={self.stage}, replica={self.replica}, "
                f"belief={self.belief}, delay={self.delay}, "
                f"cost={self.cost}, gamma={self.gamma}, weight={self.weight}, "
                f"state={self.state}, capacity={self.capacity})")

    def utility_kernel(self, n, q):
        """landa = self.gamma
        current_belief = self.belief
        pr = likelihood * ((2 * current_belief) - 1)
        congestion = landa * ((n - 1) / (n + 1))
        kernel = pr - congestion
        return kernel"""
        if n < 1:
            raise ValueError("load must be at least 1")
        if q <= 0:
            raise ValueError("latency q must be positive")
        return self.reward - (self.latency_weight * q) - self.cost

    def eval_util(self, n, q_list):  # likelihood of (q_low | Good) or (q_bad | Bad)
        """q_low = [25, 40, 50]
        q_high = [60, 80, 100]

        # Expected utility given each state
        e_good = (sum(likelihood / len(q_low) * self.utility_kernel(n, likelihood) for q in q_low) +
                  sum((1 - likelihood) / len(q_high) * self.utility_kernel(n, likelihood) for q in q_high))
        e_bad = (sum(likelihood / len(q_high) * self.utility_kernel(n, likelihood) for q in q_high) +
                 sum((1 - likelihood) / len(q_low) * self.utility_kernel(n, likelihood) for q in q_low))

        # Average overstates
        U = (self.belief * e_good) + ((1 - self.belief) * e_bad)
        return U"""
        if len(q_list) == 0:
            raise ValueError("q_list must contain at least one latency sample")
        avg_util_list = []
        for q in q_list:
            sampled_utility = self.utility_kernel(n, q)
            avg_util_list.append(sampled_utility)
        avg_util = sum(avg_util_list) / len(avg_util_list)
        return avg_util

    def observe_latency(self, load, random_source=None, latency_ms=None):
        parameters = require_state_parameters(self.state)
        if latency_ms is None:
            latency_ms = sample_latency_ms(load, parameters, random_source)
        likelihood = latency_likelihood(latency_ms, load)
        return float(latency_ms), estimate_state(likelihood), likelihood

    def local_update(self, likelihood, signal):
        local_update_list = []
        for i in range(len(likelihood), 0, -1):
            numerator = self.belief[len(likelihood) - i] * likelihood[len(likelihood) - i]
            denominator = ((self.belief[len(likelihood) - 4] * likelihood[len(likelihood) - 4]) +
                          (self.belief[len(likelihood) - 3] * likelihood[len(likelihood) - 3]) +
                         (self.belief[len(likelihood) - 2] * likelihood[len(likelihood) - 2]) +
                         (self.belief[len(likelihood) - 1] * likelihood[len(likelihood) - 1]))
            local_update_list.append(round((numerator / denominator), 3))
        return local_update_list


    def tasting(self, congestion, e=-1):
        variance = {1: 4, 2: 2, 3: 1, 4: 0.5}
        while e <= 0:
            e = np.random.normal(loc=0, scale=np.sqrt(variance[self.state]))
        value = ((50 / self.capacity) * congestion) + e
        pdf_signal, like = pdf_cal(value)
        return pdf_signal, like

    def aggregation(self, beliefs):
        w = GLOBAL_BELIEF_RETENTION

        for i in range(0, len(beliefs[0])):
            b_temp = [sublist[i] for sublist in beliefs]
            f1 = w * self.belief[i]
            f2 = (1 - w) * (1 / len(b_temp)) * sum(b_temp)
            result = f1 + f2
            self.belief[i] = round(result, 3)  # Belief Updated


def update(last_embed, number_of_replicas, stage, replica_list, likelihood):
    keys = [i for i in range(1, number_of_replicas + 1)]
    local_belief = {k: [] for k in keys}
    replica_congestion = Counter(last_embed.values())

    for index, rep in last_embed.items():
        if rep != 0:
            signal, like = replica_list[(stage, rep)].tasting(replica_congestion[rep])
            result = replica_list[(stage, rep)].local_update(like, signal)
            local_belief[rep].append(result)

    for index, beliefs in local_belief.items():
        if local_belief[index]:
            replica_list[(stage, index)].aggregation(local_belief[index])


def backward_d(flow_list, replica_list,
               likelihood, stage, num_of_replicas):  # Best response recursion for the elementary IBG, decoupled version
    #    dfs = {}
    #    joins = {}
    must_predict = 0
    policy_dict = {}
    utility_grid = pd.DataFrame()
    for f in range(len(flow_list) - 1, -1,
                   -1):  # f -> the index in the list and number of flow_lists before the player
        #        dfs[f"df_{flow_list[f]}"] = pd.DataFrame()
        if f == len(flow_list) - 1:  # Is it the last player?
            for index, rep in replica_list.items():
                if rep.stage == stage:
                    sharer = f + 1
                    while sharer >= 1:
                        utility = rep.eval_util(sharer, likelihood)
                        utility_grid.loc[rep.replica, sharer] = utility
                        # dfs[f"df_{flow_list[f]}"].loc[rep.replica, sharer] = utility
                        sharer = sharer - 1
            utility_grid = utility_grid[sorted(utility_grid.columns)]
            # policy_dict[f"f_{flow_list[f]}"] = predicting(f, num_of_replicas, utility_grid)
            policy_dict = predicting(f, num_of_replicas, utility_grid)
            break
    return policy_dict, utility_grid


def delay_gen(q_low, q_high, num_of_replicas):  # Generate a number of q delay values
    num_low = random.choice([15, 20])  # at least x low delay values
    num_high = num_of_replicas - num_low
    selected_low = random.choices(q_low, k=num_low)
    selected_high = random.choices(q_high, k=num_high)
    final_selection = selected_low + selected_high
    random.shuffle(final_selection)
    return final_selection


def predicting(people, servers, utility_grid):  # optimized version of the so-called function
    combos_dict = {}
    U = utility_grid.to_numpy()
    for choices in product(range(servers + 1), repeat=people):
        counts = tuple(choices.count(s) for s in range(1, servers + 1))
        temp_list = [U[i, counts[i]] for i in range(servers)]
        index = int(np.argmax(temp_list))
        if temp_list[index] > 0:
            index += 1
        else:
            index = 0
        combos_dict[counts] = index
    return combos_dict


def embedding(policy, num_of_replicas, embed_dict, flow_list):  # Does the embedding and final server selection
    current_state = [0] * num_of_replicas
    last_embed = dict.fromkeys(flow_list)

    for i in flow_list:
        replica_embed = policy[tuple(current_state)]
        current_state[replica_embed - 1] += 1
        embed_dict[f"f_{i}"].append(replica_embed)
        last_embed[i] = replica_embed
    return embed_dict, last_embed


def is_equilibrium(replica_list, previous_belief_list, threshold=0.03):
    current_belief_list = [replica.belief for replica in replica_list.values()]
    differences = [
        [abs(b - a) for a, b in zip(prev_row, curr_row)]
        for prev_row, curr_row in zip(previous_belief_list, current_belief_list)
    ]
    if all(d < threshold for row in differences for d in row):
        return 1
    else:
        return 0


def log_results(flow_list, iteration, filename="results.csv"):
    """
    Appends the current len(flow_list) and iteration value to a CSV file.
    Creates the file with headers if it doesn't exist.
    """
    fieldnames = ["Number of flows", "Iterations"]
    new_row = {
        "Number of flows": len(flow_list),
        "Iterations": iteration
    }

    # Check if the CSV file already exists
    file_exists = os.path.isfile(filename)

    # Append the data
    with open(filename, mode='a', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        # Write header only once
        if not file_exists:
            writer.writeheader()

        writer.writerow(new_row)

    print(f"Appended: {new_row} → {filename}")


def create_belief_csv(replica_list, filename="replica_results.csv"):
    """
    Append a dictionary (replica_list) as a new row to a CSV file.
    Creates the CSV with headers on first call if it doesn't exist.
    """
    data = {key: value.belief for key, value in replica_list.items()}

    # Convert to DataFrame (single row)
    df = pd.DataFrame([data])

    # Check if file exists
    if not os.path.exists(filename):
        # First time: create with headers
        df.to_csv(filename, index=False)
    else:
        # Append without headers
        df.to_csv(filename, mode='a', header=False, index=False)


from scipy.stats import truncnorm
import numpy as np

def pdf_cal(s, priors=None):
    """
    Computes posterior probabilities for truncated normal states.
    Sampling model: resample N(mu, sigma) until x >= 0.
    """
    states = {
        1: (0, np.sqrt(4)),
        2: (0, np.sqrt(2)),
        3: (0, np.sqrt(1)),
        4: (0, np.sqrt(0.5))  # good state
    }

    # compute likelihoods
    likelihoods = {}
    for st, (mu, sigma) in states.items():
        a = (0 - mu) / sigma   # LEFT truncation in std space
        b = np.inf
        tn = truncnorm(a, b, loc=mu, scale=sigma)
        likelihoods[st] = tn.pdf(s)

    keys = list(states.keys())
    vals = np.array([likelihoods[k] for k in keys], dtype=float)

    # Apply priors if given
    if priors is not None:
        pri = np.array([priors.get(k, 1.0) for k in keys])
        vals *= pri

    # Normalize to posterior-ish distribution
    total = vals.sum()
    if total == 0:
        post = np.ones_like(vals) / len(vals)
    else:
        post = vals / total

    # Pick most likely state
    best_state = keys[np.argmax(post)]

    return best_state, post


def aggregate_utility_total(utility_grid, last_embed, agg_util):
    value_counts = Counter(last_embed.values())
    for rep, congestion in value_counts.items():
        u = congestion * utility_grid.loc[rep, congestion]
        agg_util += u
    return agg_util


def aggregate_utility_per_flow(last_embed, utility_grid, agg_util_per_flow):
    value_counts = Counter(last_embed.values())
    for flow, rep in last_embed.items():
        u = utility_grid.loc[rep, value_counts[rep]]
        agg_util_per_flow[flow].append(u)
    return agg_util_per_flow


def jain_index(agg_util_per_flow, agg_util_total):
    for k in agg_util_per_flow:
        agg_util_per_flow[k] = round(float(np.sum(agg_util_per_flow[k])), 3)

    numerator = pow(agg_util_total, 2)
    denominator = len(agg_util_per_flow) * sum(v**2 for v in agg_util_per_flow.values())
    x = numerator / denominator
    return x
