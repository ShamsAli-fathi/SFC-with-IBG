import copy
import pickle
import random
import sys
import uuid

from budgeted import backward_budgeted_memoized, embedding_budgeted
from header import Replica, create_belief_csv, delay_gen, is_equilibrium
from header_b import SLA_v_b, update_b
from report import csv_gen_SLA, csv_gen_jain, csv_gen_time, csv_gen_util
from runner import run_decoupled_slot


DEFAULT_EXPERIMENT_RUNS = 1


def create_replicas(
    num_of_stages,
    num_of_replicas,
    belief,
    q_low,
    q_high,
    cost_list,
    gamma_list,
    states_list,
    capacity_list,
):
    replica_list = {}
    for stage in range(1, num_of_stages + 1):
        delays = delay_gen(q_low, q_high, num_of_replicas)
        for replica in range(1, num_of_replicas + 1):
            replica_list[(stage, replica)] = Replica(
                stage,
                replica,
                belief.copy(),
                delays[replica - 1],
                random.choices(cost_list, weights=[0.75, 0.25], k=1)[0],
                random.choices(gamma_list, weights=[0.5, 0.3, 0.2], k=1)[0],
                random.choices(states_list, weights=[0.25] * 4, k=1)[0],
                random.choices(capacity_list, weights=[0.6, 0.4], k=1)[0],
            )
    return replica_list


def run_decoupled_experiment(
    flow_list,
    replica_list,
    num_of_stages,
    num_of_replicas,
    likelihood,
    hash_value,
):
    iteration = 0
    while True:
        result = run_decoupled_slot(
            flow_list=flow_list,
            replica_list=replica_list,
            num_of_stages=num_of_stages,
            num_of_replicas=num_of_replicas,
            likelihood=likelihood,
        )
        iteration += 1

        print("Elapsed:", result.elapsed_seconds, "seconds")
        csv_gen_time(result.elapsed_seconds, hash_value)
        csv_gen_SLA(result.sla_violations, hash_value)
        csv_gen_util(result.aggregate_utility_total, hash_value)
        csv_gen_jain(result.jain_fairness, hash_value)
        print(f"Current Iteration: {iteration}")
        create_belief_csv(replica_list)

        if result.equilibrium == 1:
            return iteration


def run_budgeted_experiment(
    flow_list,
    replica_list,
    num_of_stages,
    num_of_replicas,
    hash_value,
):
    iteration = 0
    while True:
        previous_beliefs = [
            copy.deepcopy(replica.belief) for replica in replica_list.values()
        ]
        random.shuffle(flow_list)
        policy, _ = backward_budgeted_memoized(
            flow_list=flow_list,
            replica_list=replica_list,
            num_of_stages=num_of_stages,
            num_of_replicas=num_of_replicas,
        )
        embed_log, _ = embedding_budgeted(
            policy=policy,
            num_of_stages=num_of_stages,
            num_of_replicas=num_of_replicas,
            flow_list=flow_list,
        )
        update_b(embed_log, num_of_replicas, replica_list)
        stop = is_equilibrium(replica_list, previous_beliefs)
        csv_gen_SLA(SLA_v_b(embed_log, replica_list), hash_value)

        print(f"Current Iteration: {iteration}")
        iteration += 1
        if stop == 1:
            return iteration


def main(experiment_runs=DEFAULT_EXPERIMENT_RUNS, is_budgeted=False, load_pickle=False):
    sys.setrecursionlimit(1000)

    likelihood = 0.8
    q_low = [25, 40, 50]
    q_high = [60, 80, 100]
    cost_list = [1, 2]
    gamma_list = [0.2, 0.22, 0.24]
    states_list = [1, 2, 3, 4]
    capacity_list = [2000, 5000]
    belief = [0.25, 0.25, 0.25, 0.25]
    num_of_stages = 3
    num_of_replicas = 4
    number_of_flows = 3

    for _ in range(experiment_runs):
        hash_value = uuid.uuid4().hex[:8]
        flow_list = list(range(1, number_of_flows + 1))

        if load_pickle:
            with open("Replica.pkl", "rb") as file:
                replica_list = pickle.load(file)
        else:
            replica_list = create_replicas(
                num_of_stages,
                num_of_replicas,
                belief,
                q_low,
                q_high,
                cost_list,
                gamma_list,
                states_list,
                capacity_list,
            )

        print("Initial Replica Status:")
        for key, value in replica_list.items():
            print(f"Key: {key}, Value: {value}")

        create_belief_csv(replica_list)

        if is_budgeted:
            iteration = run_budgeted_experiment(
                flow_list,
                replica_list,
                num_of_stages,
                num_of_replicas,
                hash_value,
            )
        else:
            iteration = run_decoupled_experiment(
                flow_list,
                replica_list,
                num_of_stages,
                num_of_replicas,
                likelihood,
                hash_value,
            )

        print("\n \n Final Replica Status")
        for key, value in replica_list.items():
            print(f"Key: {key}, Value: {value}")
        print(f" \n \nThe program reached equilibrium in {iteration} iterations")


if __name__ == "__main__":
    main()
