# claude.py
def link_utility(sa, ra, sb, rb, loads_by_stage, grids_by_stage, N, replica_list):
    """
    Immediate utility for choosing (sa,ra) and (sb,rb) given CURRENT loads.
    You can change the deduction/penalty logic freely here.

    Args:
      sa, ra: chosen stage and replica in first stage
      sb, rb: chosen stage and replica in second stage
      loads_by_stage: dict[int -> np.ndarray], current loads per stage (NOT yet incremented)
      grids_by_stage: dict[stage] -> (U_matrix, df, replicas_in_stage)
                      U_matrix shape = (R, N), where col 'n' = utility at load (n+1)
      N: number of flows (for clamping load index)

    Returns:
      immediate total utility (float)
    """
    link_latency = {(4, 4): 3, (4, 3): 4, (4, 2): 5, (4, 1): 6, (3, 3): 7, (3, 2): 8, (3, 1): 9, (2, 2): 10, (2, 1): 11,
                    (1, 1): 12, (3, 4): 4, (2, 4): 5, (1, 4): 6, (2, 3): 8, (1, 3): 9, (1, 2): 11}

    Ua, _, _ = grids_by_stage[sa]
    Ub, _, _ = grids_by_stage[sb]

    na = int(loads_by_stage[sa][ra - 1])  # current congestion at (sa,ra)
    nb = int(loads_by_stage[sb][rb - 1])  # current congestion at (sb,rb)
    ua = Ua[ra - 1, min(na, N - 1)]  # utility if this player joins (load -> na+1)
    ub = Ub[rb - 1, min(nb, N - 1)]

    # -----------------------------
    # ✍️ YOUR CUSTOM DEDUCTION HERE
    # Example 1 (old behavior): 1/3 deduction of the sum  →  (2/3)*(ua+ub)
    # total = (2.0 / 3.0) * (ua + ub)

    # Example 2 (state-dependent penalty): subtract alpha*(na+nb)
    # alpha = 0.25
    # total = ua + ub - alpha * (na + nb)

    # Example 3 (ID-based rule): special pairing penalty for (sa,ra) with (sb,rb)
    # if (sa, ra, sb, rb) in {(1,3,2,2), (2,5,3,1)}:
    #     total = ua + ub - 2.0
    # else:
    #     total = ua + ub

    # DEFAULT: keep your earlier “2/3 * (ua + ub)” unless you change it.
    state_1 = replica_list[(sa, ra)].state
    state_2 = replica_list[(sb, rb)].state
    latency = link_latency[(state_1, state_2)]
    total = (ua + ub) - latency
    # -----------------------------

    return float(total)


# claude.py
import numpy as np
import pandas as pd
from functools import lru_cache
from itertools import combinations, product


def _draw_from_belief_vec(belief_vec, size):
    """
    Same spirit as your sampling: 4-state mixture with belief order [s1,s2,s3,Good]
    We sample 'size' times and return a 1D array of q samples.
    """
    b = np.asarray(belief_vec, dtype=float)
    b = b / b.sum()  # safety
    # map belief -> four normals (scaled like your earlier vectorized version)
    comps = np.random.choice(4, p=[b[3], b[2], b[1], b[0]], size=size)
    # Means/vars mirror the already-used choices in your decoupled vectorized function.
    means = np.array([3, 6, 10, 15], dtype=float)
    stds = np.array([np.sqrt(0.5), np.sqrt(1.0), np.sqrt(2.0), np.sqrt(4.0)], dtype=float)
    return np.random.normal(means[comps], stds[comps])


def build_utility_grids_budgeted(flow_list, replica_list, num_of_stages, num_of_replicas, n_mc=30):
    """
    Returns:
      grids_by_stage: dict[stage] -> (utility_grid_matrix, pandas_df, replicas_in_stage)
         - utility_grid_matrix: shape (R, N), rows=replicas (1..R), cols=congestion load (1..N)
         - pandas_df: same info as DataFrame (index=replica_id, columns=1..N)
         - replicas_in_stage: list of Replica objects in stage order
    """
    N = len(flow_list)
    loads = np.arange(1, N + 1)
    grids_by_stage = {}

    for stage in range(1, num_of_stages + 1):
        replicas = [rep for ((st, _), rep) in replica_list.items() if st == stage]
        replicas.sort(key=lambda r: r.replica)  # stable row ordering: 1..R
        R = len(replicas)

        U = np.zeros((R, N), dtype=float)
        # Build per-replica q sample sets (MC, vectorized mean via your eval)
        q_samples = [_draw_from_belief_vec(rep.belief, n_mc) for rep in replicas]

        # Fill U[r, n-1] = expected utility if current agent joins at load = n
        for r_idx, rep in enumerate(replicas):
            q_list = q_samples[r_idx]  # length n_mc
            # still call your Replica.eval_util to respect the exact kernel
            U[r_idx, :] = np.array([rep.eval_util(load, q_list) for load in loads], dtype=float)

        df = pd.DataFrame(U, index=[rep.replica for rep in replicas], columns=loads)
        grids_by_stage[stage] = (U, df, replicas)

    return grids_by_stage


# claude.py
# --- Greedy Myopic version (no lookahead) ---
def backward_budgeted_memoized(flow_list, replica_list, num_of_stages, num_of_replicas):
    """
    Greedy Myopic (no lookahead, no link_utility):
      - For each flow, choose two different stages and one replica in each.
      - Immediate utility = Ua[ra, load_a] + Ub[rb, load_b], pulled directly from
        precomputed utility grids using current congestion indices.
      - Returns a dict-like policy so main.py keeps working unchanged.
    """
    import numpy as np
    from itertools import combinations

    N = len(flow_list)

    # Build per-stage utility grids (unchanged)
    grids_by_stage = build_utility_grids_budgeted(
        flow_list=flow_list,
        replica_list=replica_list,
        num_of_stages=num_of_stages,
        num_of_replicas=num_of_replicas,
        n_mc=30
    )

    # Helpers
    def flat_to_per_stage(loads_tuple):
        arr = np.asarray(loads_tuple, dtype=int)
        chunks = np.array_split(arr, num_of_stages)
        return {s + 1: chunks[s].copy() for s in range(num_of_stages)}  # stages 1..S

    # Stage -> replica ids (row order matches grids)
    stage_rep_ids = {
        s: [rep.replica for rep in grids_by_stage[s][2]]
        for s in range(1, num_of_stages + 1)
    }

    stage_pairs = list(combinations(range(1, num_of_stages + 1), 2))

    class GreedyPolicyDict:
        def __getitem__(self, key):
            loads_tuple = tuple(key)
            per_stage = flat_to_per_stage(loads_tuple)

            best_val = -float("inf")
            best_act = None

            for (sa, sb) in stage_pairs:
                Ua, _, _ = grids_by_stage[sa]
                Ub, _, _ = grids_by_stage[sb]
                for ra in stage_rep_ids[sa]:
                    for rb in stage_rep_ids[sb]:
                        # Current congestion at each replica (before this flow joins)
                        na = int(per_stage[sa][ra - 1])
                        nb = int(per_stage[sb][rb - 1])
                        # Column index is clamped to [0, N-1]; loads are 1..N in grids
                        ua = Ua[ra - 1, min(na, N - 1)]
                        ub = Ub[rb - 1, min(nb, N - 1)]
                        total = ua + ub  # purely grid-based, congestion-indexed

                        if (total > best_val) or (
                            total == best_val and best_act is not None and
                            ((sa, ra, sb, rb) < (best_act[0][0], best_act[0][1], best_act[1][0], best_act[1][1]))
                        ):
                            best_val = total
                            best_act = ((sa, ra), (sb, rb))

            if best_act is None:
                sa, sb = stage_pairs[0]
                best_act = ((sa, stage_rep_ids[sa][0]), (sb, stage_rep_ids[sb][0]))

            return best_act

        def get(self, key, default=None):
            try:
                return self.__getitem__(key)
            except Exception:
                return default

    return GreedyPolicyDict(), grids_by_stage




# claude.py
def embedding_budgeted(policy, num_of_stages, num_of_replicas, flow_list):
    """
    Forward simulation:
    - Global loads over all stages and replicas.
    - For each flow, query policy[current_loads] → ((s1,r1),(s2,r2))
    - Increment those two replica loads and record the choices.

    Returns:
      embed_log: dict flow -> list of (stage, replica) chosen (length=2)
      final_loads_tuple: flattened tuple of loads after assigning all flows
    """
    # global loads: stage-major blocks
    per_stage = {s: np.zeros(num_of_replicas, dtype=int) for s in range(1, num_of_stages + 1)}

    def flatten(ps): return tuple(np.concatenate([ps[s] for s in range(1, num_of_stages + 1)]).tolist())

    embed_log = {f: [] for f in flow_list}

    for f in flow_list:
        choice = policy[flatten(per_stage)]
        (sa, ra), (sb, rb) = choice

        # update loads
        per_stage[sa][ra - 1] += 1
        per_stage[sb][rb - 1] += 1

        embed_log[f] = [(sa, ra), (sb, rb)]

    return embed_log, flatten(per_stage)
