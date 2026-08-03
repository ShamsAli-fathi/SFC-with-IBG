import random
import pandas as pd
import numpy as np
from itertools import product
import csv
import os
from collections import Counter
from scipy.stats import truncnorm


class Replica:
    def __init__(self, stage, replica, belief, delay, cost, gamma, state,
                 capacity):  # Base info of each replica j in stage k
        self.stage = stage
        self.replica = replica
        self.belief = belief  # GOOD belief
        self.delay = delay  # q is Delay
        self.cost = cost  # cost of using the replica -> used for budgeted approach
        self.gamma = gamma  # how strongly congestion penalizes utility
        self.weight = 1
        self.state = state
        self.capacity = capacity

    def __repr__(self):
        return (f"Replica(stage={self.stage}, replica={self.replica}, "
                f"belief={self.belief}, delay={self.delay}, "
                f"cost={self.cost}, gamma={self.gamma}, weight={self.weight}), "
                f"state={self.state}, capacity={self.capacity}")

    def utility_kernel(self, n, q):
        """ landa = self.gamma
         # denominator = (1 + self.gamma * (n - 1)) * (1 + self.cost * q)
         current_belief = self.belief
         # kernel = (self.weight / denominator) * current_belief  # utility kernel
         pr = likelihood * ((2 * current_belief) - 1)
         # kernel = (self.weight / denominator) * (pr - (1 - pr))  # utility kernel
         congestion = landa * ((n - 1) / (n + 1))
         kernel = pr - congestion"""
        gamma = self.gamma
        beta = 100
        denominator = q * (1 + gamma * n)
        kernel = beta / denominator - 5
        return kernel

    def eval_util(self, n, q):  # likelihood of (q_low | Good) or (q_bad | Bad)

        """q_low = [25, 40, 50]
        q_high = [60, 80, 100]

        # Expected utility given each state
        e_good = (sum(likelihood / len(q_low) * self.utility_kernel(q, n, likelihood) for q in q_low) +
                  sum((1 - likelihood) / len(q_high) * self.utility_kernel(q, n, likelihood) for q in q_high))
        e_bad = (sum(likelihood / len(q_high) * self.utility_kernel(q, n, likelihood) for q in q_high) +
                 sum((1 - likelihood) / len(q_low) * self.utility_kernel(q, n, likelihood) for q in q_low))

        # Average overstates
        U = (self.belief * e_good) + ((1 - self.belief) * e_bad)"""
        return self.utility_kernel(n, q)


    def local_update(self, likelihood, signal):
        if signal == 2:  # Signal = 2 -> Good Signal (Low Delay)
            numerator = self.belief * likelihood
            denominator = numerator + ((1 - self.belief) * (1 - likelihood))
        else:  # Signal = 0 -> Good Signal (Low Delay)
            numerator = self.belief * (1 - likelihood)
            denominator = numerator + ((1 - self.belief) * likelihood)
        return round((numerator / denominator), 3)


    def tasting(self, congestion, e=-1):
        """# When a replica is processed by the flow, it generates an observable signal. this signal s is:
        # s ~ p(. | Hidden State)           Here we use Bernoulli
        if self.delay < 55:
            s = 0 if random.random() < likelihood else 1  # s = 0 -> Good Signal (Low Delay)     s = 1 -> Bad Signal
        else:
            s = 1 if random.random() < likelihood else 1  # s = 1 -> Bad Signal (High Delay)
        return s"""
        variance = {1: 3, 2: 0.5}
        while e <= 0:
            e = np.random.normal(loc=0, scale=np.sqrt(variance[self.state]))
        value = ((50 / self.capacity) * congestion) + e
        pdf_signal = pdf_cal(value)
        return pdf_signal


    def aggregation(self, beliefs):
        w = 0.7  # How important global belief is

        f1 = w * self.belief
        f2 = (1 - w) * (1 / len(beliefs)) * sum(beliefs)
        result = f1 + f2
        self.belief = round(result, 3)  # Belief Updated


"""def MILP_solver(num_of_replicas, number_of_flows, marginal_grid, utility_grid):
    # index sets (replicas and flows start at 1 per your convention)
    replicas = list(range(1, num_of_replicas + 1))
    flows = list(range(1, number_of_flows + 1))
    random.shuffle(flows)
    seats_n = list(range(1, number_of_flows + 1))  # at most N seats usable on any replica

    # create solver
    solver = pywraplp.Solver.CreateSolver('CBC_MIXED_INTEGER_PROGRAMMING')
    if not solver:
        raise RuntimeError('Could not create OR-Tools CBC solver.')

    # variables
    # x[i,j] = 1 if flow i uses replica j
    x = {(i, j): solver.IntVar(0, 1, f'x_{i}_{j}') for i in flows for j in replicas}

    # z[j,n] = 1 if the n-th seat on replica j is taken (marginal seat)
    z = {(j, n): solver.IntVar(0, 1, f'z_{j}_{n}') for j in replicas for n in seats_n}

    # constraints
    # (a) each flow picks exactly one replica
    for i in flows:
        solver.Add(sum(x[(i, j)] for j in replicas) == 1)

    # (b) link counts to seats (number of assigned flows to replica j equals number of taken seats on j)
    for j in replicas:
        solver.Add(sum(x[(i, j)] for i in flows) == sum(z[(j, n)] for n in seats_n))

    # (c) seat monotonicity (no gaps)
    for j in replicas:
        for n in seats_n[1:]:  # from 2 … N
            solver.Add(z[(j, n)] <= z[(j, n - 1)])

    # objective: maximize sum of marginals Δ_j(n) * z[j,n]
    objective = solver.Objective()
    for j in replicas:
        for n in seats_n:
            # pull the marginal directly from your DataFrame
            delta_jn = float(marginal_grid.loc[j, n])
            if delta_jn != 0.0:
                objective.SetCoefficient(z[(j, n)], delta_jn)
    # (x-variables do not appear in the objective because flows are symmetric; z captures total welfare)
    objective.SetMaximization()

    status = solver.Solve()

    # 6) read solution
    if status == pywraplp.Solver.OPTIMAL:
        # print('Objective (total welfare) =', objective.Value())

        # counts per replica (final sharers)
        counts = {j: int(sum(z[(j, n)].solution_value() for n in seats_n)) for j in replicas}
        # print('Replica final counts:', counts)

        # assignments per flow (which replica chosen)
        assignment = {f"f_{i}": None for i in flows}
        for i in flows:
            for j in replicas:
                if x[(i, j)].solution_value() > 0.5:
                    assignment[f"f_{i}"] = j
                    break
        assignment = prune_negative_replicas(assignment, utility_grid)  # Remove if any selected util is negative, put 0
        # print('Assignments (flow -> replica):', assignment)
    else:
        print('No optimal solution found (status =', status, ')')

    return assignment
"""


"""def MILP_solver(num_of_replicas, number_of_flows, marginal_grid, utility_grid):
    # This MILP optimizes for total welfare using marginal
    # index sets (replicas and flows start at 1 per your convention)
    replicas = list(range(1, num_of_replicas + 1))
    flows = list(range(1, number_of_flows + 1))
    random.shuffle(flows)
    seats_n = list(range(1, number_of_flows + 1))  # at most N seats usable on any replica

    # ============= PRE-FILTERING: Find valid (replica, count) pairs =============
    valid_replica_counts = {}  # {replica_j: [valid counts where u_j(n) > 0]}
    max_valid_count = {}  # {replica_j: maximum count with positive utility}

    for j in replicas:
        valid_counts = []
        for n in seats_n:
            utility_value = float(utility_grid.loc[j, n])
            if utility_value > 0:
                valid_counts.append(n)

        valid_replica_counts[j] = valid_counts
        max_valid_count[j] = max(valid_counts) if valid_counts else 0

    # Filter out replicas that have NO positive utility at any count
    usable_replicas = [j for j in replicas if max_valid_count[j] > 0]

    if not usable_replicas:
        print("WARNING: No replicas have positive utility! Returning empty assignment.")
        return {f"f_{i}": 0 for i in flows}

    # ============= CREATE SOLVER =============
    solver = pywraplp.Solver.CreateSolver('CBC_MIXED_INTEGER_PROGRAMMING')
    if not solver:
        raise RuntimeError('Could not create OR-Tools CBC solver.')

    # ============= VARIABLES =============
    # x[i,j] = 1 if flow i uses replica j (only for usable replicas)
    x = {(i, j): solver.IntVar(0, 1, f'x_{i}_{j}')
         for i in flows for j in usable_replicas}

    # z[j,n] = 1 if the n-th seat on replica j is taken
    # Only create z variables for valid counts
    z = {}
    for j in usable_replicas:
        for n in valid_replica_counts[j]:
            z[(j, n)] = solver.IntVar(0, 1, f'z_{j}_{n}')

    # ============= CONSTRAINTS =============
    # (a) Each flow picks exactly one replica (from usable replicas only)
    for i in flows:
        solver.Add(sum(x[(i, j)] for j in usable_replicas) == 1)

    # (b) Link counts to seats - count must match one of the valid counts
    for j in usable_replicas:
        # Number of flows assigned = sum of valid seat indicators
        solver.Add(
            sum(x[(i, j)] for i in flows) ==
            sum(z[(j, n)] for n in valid_replica_counts[j])
        )

    # (c) Seat monotonicity within valid counts
    for j in usable_replicas:
        valid_counts_sorted = sorted(valid_replica_counts[j])
        for idx in range(1, len(valid_counts_sorted)):
            n_curr = valid_counts_sorted[idx]
            n_prev = valid_counts_sorted[idx - 1]
            solver.Add(z[(j, n_curr)] <= z[(j, n_prev)])

    # (d) At most one valid count can be active per replica
    for j in usable_replicas:
        if len(valid_replica_counts[j]) > 1:
            # Only one seat count should be "active" (the actual count)
            solver.Add(sum(z[(j, n)] for n in valid_replica_counts[j]) <= max_valid_count[j])

    # ============= OBJECTIVE =============
    objective = solver.Objective()
    for j in usable_replicas:
        for n in valid_replica_counts[j]:
            delta_jn = float(marginal_grid.loc[j, n])
            if delta_jn > 0:  # Only add positive marginals
                objective.SetCoefficient(z[(j, n)], delta_jn)
    objective.SetMaximization()

    # ============= SOLVE =============
    status = solver.Solve()

    # ============= READ SOLUTION =============
    if status == pywraplp.Solver.OPTIMAL:
        # Assignments per flow
        assignment = {f"f_{i}": 0 for i in flows}  # Default to 0 (unassigned)
        for i in flows:
            for j in usable_replicas:
                if x[(i, j)].solution_value() > 0.5:
                    assignment[f"f_{i}"] = j
                    break

        # Verify all assignments have positive utility
        counts = {j: sum(1 for fid, rep in assignment.items() if rep == j)
                  for j in usable_replicas}

        # Double-check: ensure no negative utilities slipped through
        for fid, j in assignment.items():
            if j > 0:
                n = counts[j]
                util = float(utility_grid.loc[j, n])
                if util <= 0:
                    print(f"WARNING: {fid} assigned to replica {j} with n={n}, utility={util}")
                    assignment[fid] = 0  # Unassign

        return assignment
    else:
        print(f'No optimal solution found (status = {status})')
        return {f"f_{i}": 0 for i in flows}"""


"""def MILP_solver(num_of_replicas, number_of_flows, marginal_grid, utility_grid):
    # Optimized Pure MILP that maximizes sum of individual utilities.
    # Uses tighter Big-M bounds and variable reduction.
    import time
    start_time = time.time()

    replicas = list(range(1, num_of_replicas + 1))
    flows = list(range(1, number_of_flows + 1))
    random.shuffle(flows)
    seats_n = list(range(1, number_of_flows + 1))

    # print(f"Starting MILP with {number_of_flows} flows and {num_of_replicas} replicas...")

    # ============= PRE-PROCESSING: Calculate bounds and filter =============
    # Find min/max utilities to set tighter Big-M
    u_min = float(utility_grid.min().min())
    u_max = float(utility_grid.max().max())
    M = max(abs(u_min), abs(u_max)) * 2  # Tighter Big-M
    # print(f"  Utility range: [{u_min:.2f}, {u_max:.2f}], Big-M: {M:.2f}")

    # Pre-filter: Find replicas with at least one positive utility
    valid_replicas = []
    valid_counts = {}  # {replica: [counts where u > 0]}

    for j in replicas:
        positive_counts = []
        for n in seats_n:
            if float(utility_grid.loc[j, n]) > 0:
                positive_counts.append(n)

        if positive_counts:
            valid_replicas.append(j)
            valid_counts[j] = positive_counts

    if not valid_replicas:
        print("  ERROR: No replicas have positive utility!")
        return {f"f_{i}": 0 for i in flows}

    # print(f"  Valid replicas: {len(valid_replicas)}/{num_of_replicas}")

    # ============= CREATE SOLVER =============
    solver = pywraplp.Solver.CreateSolver('CBC_MIXED_INTEGER_PROGRAMMING')
    if not solver:
        raise RuntimeError('Could not create OR-Tools CBC solver.')

    # Set aggressive parameters
    solver.SetTimeLimit(30000)  # 30 second timeout
    # solver.EnableOutput()  # Show solver progress

    # ============= VARIABLES (Reduced) =============
    # Only create x variables for valid replicas
    x = {(i, j): solver.IntVar(0, 1, f'x_{i}_{j}')
         for i in flows for j in valid_replicas}

    # Only create y variables for valid (replica, count) pairs
    y = {}
    for j in valid_replicas:
        for n in valid_counts[j]:
            y[(j, n)] = solver.IntVar(0, 1, f'y_{j}_{n}')

    # Simplified: Use actual utility values directly in objective
    # No separate u variables - compute utility contribution directly

    # print(f"  Variables created: {len(x)} x-vars, {len(y)} y-vars")
    # print(f"  Time elapsed: {time.time() - start_time:.2f}s")

    # ============= CONSTRAINTS =============

    # (1) Each flow picks exactly one replica
    for i in flows:
        solver.Add(sum(x[(i, j)] for j in valid_replicas) == 1)

    # (2) Count consistency: actual count = sum of count indicators
    for j in valid_replicas:
        count_j = sum(x[(i, j)] for i in flows)
        solver.Add(count_j == sum(n * y[(j, n)] for n in valid_counts[j]))

    # (3) At most one count indicator active per replica
    for j in valid_replicas:
        solver.Add(sum(y[(j, n)] for n in valid_counts[j]) <= 1)

    # print(f"  Constraints added")
    # print(f"  Time elapsed: {time.time() - start_time:.2f}s")

    # ============= OBJECTIVE (Simplified) =============
    # Directly use: utility contribution = sum over all (i,j,n) of u[j,n] * x[i,j] * y[j,n]
    # This is bilinear (x * y), but we can linearize with auxiliary variables

    # Create auxiliary variable w[i,j,n] = x[i,j] * y[j,n]
    w = {}
    for i in flows:
        for j in valid_replicas:
            for n in valid_counts[j]:
                w[(i, j, n)] = solver.IntVar(0, 1, f'w_{i}_{j}_{n}')
                # McCormick linearization: w = x * y
                solver.Add(w[(i, j, n)] <= x[(i, j)])
                solver.Add(w[(i, j, n)] <= y[(j, n)])
                solver.Add(w[(i, j, n)] >= x[(i, j)] + y[(j, n)] - 1)

    # Objective: sum of utilities
    objective = solver.Objective()
    for i in flows:
        for j in valid_replicas:
            for n in valid_counts[j]:
                utility_val = float(utility_grid.loc[j, n])
                if utility_val > 0:  # Only add positive contributions
                    objective.SetCoefficient(w[(i, j, n)], utility_val)

    objective.SetMaximization()

    print(f"  Objective set, starting solve...")
    print(f"  Time elapsed: {time.time() - start_time:.2f}s")

    # ============= SOLVE =============
    status = solver.Solve()

    solve_time = time.time() - start_time
    print(f"\n  Solve completed in {solve_time:.2f}s")
    # print(f"  Status: {status}")

    # ============= READ SOLUTION =============
    if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
        assignment = {f"f_{i}": 0 for i in flows}

        for i in flows:
            for j in valid_replicas:
                if x[(i, j)].solution_value() > 0.5:
                    assignment[f"f_{i}"] = j
                    break

        # Calculate actual utilities
        counts = {j: sum(1 for fid, rep in assignment.items() if rep == j)
                  for j in valid_replicas}
        total_utility = 0

        # print(f"\n  Assignment Summary:")
        for fid, j in sorted(assignment.items()):
            if j > 0:
                n = counts[j]
                util = float(utility_grid.loc[j, n])
                total_utility += util
                # print(f"    {fid} → replica {j} (n={n}): utility = {util:.3f}")

        # print(f"\n  Total utility: {total_utility:.2f}")
        # print(f"  Flows assigned: {sum(1 for r in assignment.values() if r != 0)}/{number_of_flows}")

        return assignment
    else:
        print(f'  No solution found (status = {status})')
        print(f'  Solver might have hit time limit or problem is infeasible')
        return {f"f_{i}": 0 for i in flows}
"""

def MILP_solver(num_of_replicas, number_of_flows, marginal_grid, utility_grid):
    """
    Fast MILP using marginal_grid, but with NO pre-filtering.
    All (j, n) pairs are included regardless of total welfare.

    W(j,n) = sum_{k=1..n} marginal[j,k]
    """

    from ortools.linear_solver import pywraplp
    import random

    replicas = list(range(1, num_of_replicas + 1))
    flows    = list(range(1, number_of_flows + 1))
    random.shuffle(flows)

    seats_n = list(range(1, number_of_flows + 1))

    # ==========================================================
    # BUILD ALL W(j,n) with NO filtering
    # ==========================================================
    welfare_map = {}          # (j,n) -> W(j,n)
    for j in replicas:
        cum_welfare = 0.0
        for n in seats_n:
            m_val = float(marginal_grid.loc[j, n])
            cum_welfare += m_val
            welfare_map[(j, n)] = cum_welfare

    # Every replica keeps all n options
    valid_replicas = replicas
    valid_counts   = {j: seats_n[:] for j in replicas}

    # ==========================================================
    # CREATE SOLVER
    # ==========================================================
    solver = pywraplp.Solver.CreateSolver('CBC_MIXED_INTEGER_PROGRAMMING')
    solver.SetTimeLimit(5000)

    # ==========================================================
    # VARIABLES
    # ==========================================================
    x = {
        (i, j): solver.IntVar(0, 1, f"x_{i}_{j}")
        for i in flows
        for j in valid_replicas
    }

    y = {
        (j, n): solver.IntVar(0, 1, f"y_{j}_{n}")
        for j in valid_replicas
        for n in valid_counts[j]
    }

    # ==========================================================
    # CONSTRAINTS
    # ==========================================================

    # (1) each flow chooses exactly one replica
    for i in flows:
        solver.Add(sum(x[(i, j)] for j in valid_replicas) == 1)

    # (2) flows assigned = chosen n
    for j in valid_replicas:
        lhs = sum(x[(i, j)] for i in flows)
        rhs = sum(n * y[(j, n)] for n in valid_counts[j])
        solver.Add(lhs == rhs)

    # (3) at most one congestion level per replica
    for j in valid_replicas:
        solver.Add(sum(y[(j, n)] for n in valid_counts[j]) <= 1)

    # ==========================================================
    # OBJECTIVE
    # ==========================================================
    objective = solver.Objective()
    for j in valid_replicas:
        for n in valid_counts[j]:
            objective.SetCoefficient(y[(j, n)], welfare_map[(j, n)])
    objective.SetMaximization()

    # ==========================================================
    # SOLVE
    # ==========================================================
    status = solver.Solve()

    # ==========================================================
    # READ SOLUTION
    # ==========================================================
    assignment = {f"f_{i}": 0 for i in flows}

    if status in (solver.OPTIMAL, solver.FEASIBLE):
        for i in flows:
            for j in valid_replicas:
                if x[(i, j)].solution_value() > 0.5:
                    assignment[f"f_{i}"] = j
                    break
    else:
        print("MILP failed, returning zeros.")

    return assignment




def prune_negative_replicas(assignment, utility_grid, seed=None):
    """
    If a replica's per-flow utility at its current sharers n is <= 0,
    randomly remove flows from that replica until utility > 0 (or none left).
    assignment: dict like {'f_1': 2, 'f_2': 3, ...} with 0 meaning unassigned
    utility_grid: DataFrame, rows=replica id (ints), cols=n sharers (ints)
    """
    if seed is not None:
        random.seed(seed)

    # Build reverse map: replica -> list of flows assigned to it
    by_rep = {int(j): [] for j in utility_grid.index.astype(int)}
    for fid, r in assignment.items():
        if r in by_rep:
            by_rep[r].append(fid)

    # For each replica, drop random flows until u_j(n) > 0 (or n == 0)
    for j, flist in by_rep.items():
        n = len(flist)
        # If utility at current n is nonpositive, keep removing
        while n > 0 and float(utility_grid.loc[j, n]) <= 0.0:
            victim = random.choice(flist)
            assignment[victim] = 0
            flist.remove(victim)
            n -= 1
        # optional: you can update counts here if you keep a counts dict
        # counts[j] = n

    return assignment  # (and counts if you track it)


def update(last_embed, number_of_replicas, stage, replica_list, likelihood):
    keys = [i for i in range(1, number_of_replicas + 1)]
    local_belief = {k: [] for k in keys}
    replica_congestion = Counter(last_embed.values())

    for index, rep in last_embed.items():
        if rep != 0:
            signal = replica_list[(stage, rep)].tasting(likelihood)
            result = replica_list[(stage, rep)].local_update(likelihood, signal)
            local_belief[rep].append(result)

    for index, beliefs in local_belief.items():
        if local_belief[index]:
            replica_list[(stage, index)].aggregation(local_belief[index])


def util_grid_make(flow_list, replica_list,
                   likelihood, stage):  # Best response recursion for the elementary IBG, decoupled version
    def draw(belief):
        return np.random.choice([np.random.normal(5, np.sqrt(0.5)), np.random.normal(15, np.sqrt(1))], p=[belief, 1 - belief])

    utility_grid = pd.DataFrame()
    for f in range(len(flow_list) - 1, -1,
                   -1):  # f -> the index in the list and number of flow_lists before the player
        if f == len(flow_list) - 1:  # Is it the last player?
            for index, rep in replica_list.items():
                if rep.stage == stage:
                    q_draws = [draw(rep.belief) for _ in range(30)]
                    q = sum(q_draws) / 30
                    sharer = f + 1
                    while sharer >= 1:
                        utility = rep.eval_util(sharer, q)
                        utility_grid.loc[rep.replica, sharer] = utility
                        sharer = sharer - 1
            utility_grid = utility_grid[sorted(utility_grid.columns)]
            break  # Simply added a break to previous code, because I'm lazy....duh
    marginal_grid = marginal(utility_grid)
    return utility_grid, marginal_grid


def marginal(df):
    # Compute total welfare G_j(n) = n * u_j(n)
    G = df.mul(df.columns, axis=1)

    # Compute marginals Δ_j(n) = G_j(n) - G_j(n-1)
    marginals = G.diff(axis=1)
    marginals[1] = G[1]  # first marginal = G(n=1)

    # Optional: round for clarity
    marginals = marginals.round(5)
    return marginals


def delay_gen(q_low, q_high, num_of_replicas):  # Generate a number of q delay values
    num_low = random.choice([3, 3])  # at least x low delay values
    num_high = num_of_replicas - num_low
    selected_low = random.choices(q_low, k=num_low)
    selected_high = random.choices(q_high, k=num_high)
    final_selection = selected_low + selected_high
    random.shuffle(final_selection)
    return final_selection


def embedding(policy, num_of_replicas, embed_dict):  # Does the embedding and final server selection
    flow_list = list(policy.keys())[::-1]  # Reverse Order -> First decider comes first
    current_state = [0] * num_of_replicas
    last_embed = dict.fromkeys(flow_list)

    for i in flow_list:
        replica_embed = policy[i][tuple(current_state)]
        current_state[replica_embed - 1] += 1
        embed_dict[i].append(replica_embed)
        last_embed[i] = replica_embed
    return embed_dict, last_embed


def is_equilibrium(replica_list, previous_belief_list):
    threshold = 0.02
    current_belief_list = [replica.belief for replica in replica_list.values()]
    differences = [abs(b - a) for a, b in zip(previous_belief_list, current_belief_list)]
    if all(diff < threshold for diff in differences):
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


def pdf_cal(s, priors=None):
    """
    Computes posterior-ish probabilities for truncated normal states.
    Sampling model: resample N(mu, sigma) until x >= 0.
    """
    states = {
        2: (0, np.sqrt(0.5)),  # good state
        1: (0, np.sqrt(3.0))  # bad state
    }

    likelihoods = {}
    for st, (mu, sigma) in states.items():
        a, b = 0, np.inf  # truncate at zero
        tn = truncnorm(a / sigma, b / sigma, loc=mu, scale=sigma)
        likelihoods[st] = tn.pdf(s)

    # vectorize
    keys = list(states.keys())
    vals = np.array([likelihoods[k] for k in keys], dtype=float)

    # priors (optional)
    if priors is not None:
        pri = np.array([priors.get(k, 1.0) for k in keys])
        vals *= pri

    # normalize → posterior-ish
    total = vals.sum()
    if total == 0:
        post = np.ones_like(vals) / len(vals)
    else:
        post = vals / total

    post_dict = dict(zip(keys, post))

    # best state
    best_state = keys[int(np.argmax(post))]

    # print("Posterior-ish:", post_dict)
    # print("Best state:", best_state)

    return best_state


def aggregate_utility_total(utility_grid, last_embed, agg_util):
    value_counts = Counter(last_embed.values())
    for rep, congestion in value_counts.items():
        u = congestion * utility_grid.loc[rep, congestion]
        agg_util += u
    return agg_util


def aggregate_utility_per_flow(last_embed, utility_grid, agg_util_per_flow):
    last_embed_n = {int(k.replace('f_', '')): v for k, v in last_embed.items()}
    value_counts = Counter(last_embed.values())
    for flow, rep in last_embed_n.items():
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
