from header import *
from header_b import *
from report import *
from claude import backward_d_memoized_simple
from budgeted import *
import pandas
import numpy
import random
import pickle
import copy
import sys
import uuid
import time

for run_time in range(1, 30):
    hash_value = uuid.uuid4().hex[:8]

    sys.setrecursionlimit(1000)

    is_budgeted = 1

    likelihood = 0.8  # Constant likelihood
    q_low = [25, 40, 50]
    q_high = [60, 80, 100]
    cost_list = [1, 2]
    gamma_list = [0.2, 0.22, 0.24]
    states_list = [1, 2, 3, 4]
    capacity_list = [2000, 5000]
    belief = [0.25, 0.25, 0.25, 0.25]  # Good belief is last
    replica_list = {}
    num_of_stages = 3
    num_of_replicas = 80
    number_of_flows = 50
    flow_list = lst = [i for i in range(1, number_of_flows + 1)]  # Number of flows/tenants
    budget = num_of_stages + 2

    load_pickle = 0

    if load_pickle == 1:  # Load a previously saved Replica set (MUST BE STORED BEFORE)
        with open('Replica.pkl', 'rb') as f:
            replica_list = pickle.load(f)
    else:
        for i in (range(1, num_of_stages + 1)):  # Instantiate the pods and replicas
            l = delay_gen(q_low, q_high, num_of_replicas)
            for j in (range(1, num_of_replicas + 1)):
                replica_list[(i, j)] = Replica(i, j, belief.copy(), l[j - 1],
                                               random.choices(cost_list, weights=[0.75, 0.25], k=1)[0],
                                               random.choices(gamma_list, weights=[0.5, 0.3, 0.2], k=1)[0],
                                               random.choices(states_list, weights=[0.25, 0.25, 0.25, 0.25], k=1)[0],
                                               random.choices(capacity_list, weights=[0.6, 0.4], k=1)[0])

    print("Initial Replica Status:")
    for key, value in replica_list.items():
        print(f"Key: {key}, Value: {value}")

    create_belief_csv(replica_list)

    keys = [f"f_{i}" for i in range(1, len(flow_list) + 1)]
    empty_embed_dict = {k: [] for k in keys}
    embed_dict = copy.deepcopy(empty_embed_dict)

    if is_budgeted == 0:
        iteration = 0
        while iteration != -1:
            agg_util_total = 0
            agg_util_per_flow = {i: [] for i in range(1, number_of_flows + 1)}
            start = time.time()
            previous_belief_list = [copy.deepcopy(replica.belief) for replica in replica_list.values()]  # Store previous belief values
            for stage in range(1, num_of_stages + 1):
                random.shuffle(flow_list)
                policy, utility_grid = backward_d_memoized_simple(flow_list, replica_list, likelihood, stage,
                                                                  num_of_replicas)
                embed_dict, last_embed = embedding(policy, num_of_replicas, embed_dict, flow_list)
                end = time.time()
                agg_util_total = aggregate_utility_total(utility_grid, last_embed, agg_util_total)
                agg_util_per_flow = aggregate_utility_per_flow(last_embed, utility_grid, agg_util_per_flow)
                update(last_embed, num_of_replicas, stage, replica_list, likelihood)
            iteration += 1
            print("Elapsed:", end - start, "seconds")
            csv_gen_time(end - start, hash_value)
            # violation_count = SLA_v(embed_dict, replica_list)
            violation_count = SLA_v_b_v2(per_flow_latency)
            jain = jain_index(agg_util_per_flow, agg_util_total)
            csv_gen_SLA(violation_count, hash_value)
            csv_gen_util(agg_util_total, hash_value)
            csv_gen_jain(jain, hash_value)

            embed_dict = copy.deepcopy(empty_embed_dict)
            stop = is_equilibrium(replica_list, previous_belief_list)  # Checks Equilibrium
            print(f"Current Iteration: {iteration}")
            create_belief_csv(replica_list)
            if stop == 1:
                break
    else:
        iteration = 0
        while iteration != -1:
            start = time.time()
            previous_belief_list = [copy.deepcopy(replica.belief) for replica in replica_list.values()]  # Store previous belief values
            random.shuffle(flow_list)
            policy, grids_by_stage = backward_budgeted_memoized(
                flow_list=flow_list,
                replica_list=replica_list,
                num_of_stages=num_of_stages,
                num_of_replicas=num_of_replicas
            )
            embed_log, final_loads = embedding_budgeted(
                policy=policy,
                num_of_stages=num_of_stages,
                num_of_replicas=num_of_replicas,
                flow_list=flow_list
            )

            per_flow_latency = latency(embed_log, flow_list, replica_list)
            agg_util_per_flow = {f: [] for f in flow_list}
            agg_total = aggregate_utility_total(grids_by_stage, embed_log, per_flow_latency)
            agg_util_per_flow = aggregate_utility_per_flow(embed_log, grids_by_stage, agg_util_per_flow, per_flow_latency)

            print("Total aggregate utility =", agg_total)
            print("Per-flow aggregate utility =", {f: sum(v) for f, v in agg_util_per_flow.items()})

            update_b(embed_log, num_of_replicas, replica_list)
            stop = is_equilibrium(replica_list, previous_belief_list)  # Checks Equilibrium
            end = time.time()
            print("Elapsed:", end - start, "seconds")
            csv_gen_time(end - start, hash_value)
            # violation_count = SLA_v_b(embed_log, replica_list)
            violation_count = SLA_v_b_v2(per_flow_latency)
            csv_gen_SLA(violation_count, hash_value)
            jain = jain_index(agg_util_per_flow, agg_total)
            csv_gen_util(agg_total, hash_value)
            csv_gen_jain(jain, hash_value)

            print(f"Current Iteration: {iteration}")
            iteration += 1
            if stop == 1:
                break

    print("\n \n Final Replica Status")
    for key, value in replica_list.items():
        print(f"Key: {key}, Value: {value}")

    print(f" \n \nThe program reached equilibrium in {iteration} iterations")

# log_results(flow_list, iteration)
