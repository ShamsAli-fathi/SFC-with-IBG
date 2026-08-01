def backward_d_memoized_simple(flow_list, replica_list, likelihood, stage, num_of_replicas):
    import numpy as np
    import pandas as pd
    from functools import lru_cache

    # ----------------------------------------
    # 1. Draw q values (unchanged logic)
    # ----------------------------------------
    def draw(belief):
        belief_temp = np.array(belief)
        belief_temp = belief_temp / belief_temp.sum()
        return np.random.choice(
            [np.random.normal(3, np.sqrt(0.5)),
             np.random.normal(6, np.sqrt(1)),
              np.random.normal(10, np.sqrt(2)),
             np.random.normal(15, np.sqrt(4))],
            p=[belief_temp[3], belief_temp[2], belief_temp[1], belief_temp[0]]
        )

    # ----------------------------------------
    # 2. Build utility_grid (vectorized)
    # rows = replicas in this stage
    # cols = congestion level 1..N
    # ----------------------------------------
    replicas_in_stage = []
    q_values = []
    for idx, rep in replica_list.items():
        if rep.stage == stage:
            replicas_in_stage.append(rep)
            # 30 MC draws, vectorized mean
            samples = np.array([draw(rep.belief) for _ in range(30)])
            q_values.append(samples)

    R_stage = len(replicas_in_stage)
    N = len(flow_list)

    # congestion levels 1..N as a numpy array
    loads = np.arange(1, N + 1)

    # build matrix utility_grid_mat shape = (R_stage, N)
    utility_grid_mat = np.zeros((R_stage, N))

    for r_index, rep in enumerate(replicas_in_stage):
        q = q_values[r_index]
        # vectorized eval_util over all loads
        utility_grid_mat[r_index, :] = np.array([rep.eval_util(load, q) for load in loads])

    # convert to DataFrame to keep your original structure
    utility_grid = pd.DataFrame(
        utility_grid_mat,
        index=[rep.replica for rep in replicas_in_stage],
        columns=loads
    )

    # ----------------------------------------
    # 3. Vectorized backward induction per replica
    # decisions[j][i][n] = 0 or 1
    # ----------------------------------------

    # decisions is stored as:
    # decisions[j] = 2D numpy array of shape (N+1, N)
    # rows: i (player index) = 1..N
    # cols: n (congestion)   = 0..N-1
    # Only entries with n <= i-1 are valid.

    decisions = {}

    for r_idx, rep in enumerate(replicas_in_stage):
        j = rep.replica

        # utility_grid_mat[r_idx, :] holds utilities for loads 1..N
        util = utility_grid_mat[r_idx, :]  # shape (N,)

        # For congestion n, utility is util[n] because util[n] corresponds to load = n+1
        # Build a matrix of shape (N, N) where each row i uses util[0..i-1], and zeros after that
        # Then decisions = (util > 0)
        util_expanded = np.tile(util, (N, 1))  # shape (N,N)
        n_indices = np.arange(N)
        i_indices = np.arange(1, N + 1).reshape(-1, 1)

        # mask for valid states (n <= i-1)
        valid_mask = n_indices <= (i_indices - 1)

        # decision matrix initialized to 0
        dec_mat = np.zeros((N, N), dtype=int)

        # apply decision only on valid (i,n)
        dec_mat[valid_mask] = (util_expanded[valid_mask] > 0).astype(int)

        decisions[j] = dec_mat

    # ----------------------------------------
    # 4. Policy lookup: loads → best replica
    # Uses memoized function for speed
    # ----------------------------------------
    @lru_cache(None)
    def policy_state(loads_tuple):
        loads = np.array(loads_tuple)
        total_assigned = loads.sum()

        if total_assigned >= N:
            return 0

        # current player index i (1-based)
        i = total_assigned + 1

        best_replica = 0
        best_value = -1e18

        # vectorized lookup over all replicas in this stage
        for r_idx, rep in enumerate(replicas_in_stage):
            j = rep.replica
            n = loads[rep.replica - 1]

            # invalid state
            if n > i - 1:
                continue

            # decision for this replica
            if decisions[j][i - 1, n] == 1:
                u = utility_grid_mat[r_idx, n]   # utility at load = n+1
                if u > best_value:
                    best_value = u
                    best_replica = j

        if best_value <= 0:
            return 0
        return best_replica

    # wrapper so embedding() stays unchanged
    class BRPolicyDict:
        def __getitem__(self, key):
            return policy_state(tuple(key))

        def get(self, key, default=0):
            return policy_state(tuple(key))

    return BRPolicyDict(), utility_grid
