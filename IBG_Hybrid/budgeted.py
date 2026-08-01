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


# Active Hybrid cardinality budget.  The current planner and embedding path
# represent exactly two distinct selected stages, so changing this value also
# requires generalizing those two-stage data structures and tests.
HYBRID_STAGE_BUDGET = 2


def require_hybrid_stage_budget(stage_budget):
    """Validate the active, deliberately non-configurable Hybrid budget."""

    if isinstance(stage_budget, bool) or not isinstance(stage_budget, int):
        raise TypeError("stage_budget must be an integer")
    if stage_budget != HYBRID_STAGE_BUDGET:
        raise ValueError(
            "the active Hybrid action model supports exactly "
            f"L={HYBRID_STAGE_BUDGET}; changing L requires deliberate "
            "planner, embedding, traffic, replay, and test changes"
        )
    return HYBRID_STAGE_BUDGET


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
def backward_budgeted_rollout(
    flow_list,
    replica_list,
    num_of_stages,
    num_of_replicas,
    D=1,         # rollout depth
    C=8,         # Top-C replicas per stage (branching)
    X=8,         # Top-X joint actions per state (branching)
    S=50,        # <-- NEW: number of Monte Carlo continuations
    eps=0.10,    # <-- NEW: epsilon for epsilon-greedy continuation policy
    stage_budget=HYBRID_STAGE_BUDGET,
):
    """
    Budgeted (L=HYBRID_STAGE_BUDGET) planner with MC rollouts:
      - Immediate value: ua + ub from utility grids (no link term here).
      - Branching: Top-C per stage -> Top-X joint actions per state.
      - Continuation: For each candidate, average S epsilon-greedy continuations of length D.
    Returns:
      (policy_mapping_like, grids_by_stage)
      where policy[state_tuple] -> ((sa, ra), (sb, rb))
    """
    import numpy as np
    from functools import lru_cache
    from itertools import combinations

    N = len(flow_list)
    require_hybrid_stage_budget(stage_budget)
    if num_of_stages <= stage_budget:
        raise ValueError(
            "Hybrid requires more available stages than its selected-stage "
            "budget so one stage can be bypassed"
        )
    rng = np.random.default_rng()

    # --- Build per-stage utility grids (belief-based MC), unchanged ---
    grids_by_stage = build_utility_grids_budgeted(
        flow_list=flow_list,
        replica_list=replica_list,
        num_of_stages=num_of_stages,
        num_of_replicas=num_of_replicas,
        n_mc=30,
    )

    # --- Helpers: state conversions ---
    def flat_to_per_stage(loads_tuple):
        arr = np.asarray(loads_tuple, dtype=int)
        chunks = np.split(arr, num_of_stages)
        # dict: stage -> np.array of length num_of_replicas
        return {s + 1: chunks[s] for s in range(num_of_stages)}

    def per_stage_to_flat(stage_loads_dict):
        arrs = [np.asarray(stage_loads_dict[s], dtype=int) for s in range(1, num_of_stages + 1)]
        return tuple(np.concatenate(arrs, axis=0).tolist())

    # --- Immediate value kernel (ua + ub only) ---
    def imm_ua_plus_ub(sa, ra, sb, rb, loads_by_stage):
        Ua, _, _ = grids_by_stage[sa]
        Ub, _, _ = grids_by_stage[sb]
        na = int(loads_by_stage[sa][ra - 1])
        nb = int(loads_by_stage[sb][rb - 1])
        ua = Ua[ra - 1, min(na, N - 1)]
        ub = Ub[rb - 1, min(nb, N - 1)]
        return float(ua + ub)

    # --- Stage metadata ---
    stage_pairs = list(
        combinations(range(1, num_of_stages + 1), stage_budget)
    )
    stage_rep_objs = {s: grids_by_stage[s][2] for s in range(1, num_of_stages + 1)}
    stage_U = {s: grids_by_stage[s][0] for s in range(1, num_of_stages + 1)}
    stage_rep_ids_full = {s: [rep.replica for rep in stage_rep_objs[s]] for s in range(1, num_of_stages + 1)}

    # --- 1) Top-C pruning per stage (for branching) ---
    stage_candidates = {}
    for s in range(1, num_of_stages + 1):
        U = stage_U[s]
        reps = stage_rep_objs[s]
        scores = [(U[r_idx, 0], r_idx) for r_idx in range(U.shape[0])]
        scores.sort(reverse=True, key=lambda x: x[0])
        chosen = scores[: min(C, len(scores))]
        if chosen:
            stage_candidates[s] = [reps[r_idx].replica for _, r_idx in chosen]
        else:
            stage_candidates[s] = [rep.replica for rep in reps]

    # --- Fast greedy (full action space), memoized per state ---
    greedy_cache = {}
    def greedy_action_full(per_stage):
        key = per_stage_to_flat(per_stage)
        cached = greedy_cache.get(key)
        if cached is not None:
            return cached
        best_val, best_act = -float("inf"), None
        for (sa, sb) in stage_pairs:
            Ua = stage_U[sa]; Ub = stage_U[sb]
            ra_ids = np.asarray(stage_rep_ids_full[sa], dtype=int)
            rb_ids = np.asarray(stage_rep_ids_full[sb], dtype=int)
            na_vec = np.minimum(per_stage[sa][ra_ids - 1], N - 1)
            nb_vec = np.minimum(per_stage[sb][rb_ids - 1], N - 1)
            ua_vec = Ua[ra_ids - 1, na_vec]
            ub_vec = Ub[rb_ids - 1, nb_vec]
            S_mat = ua_vec[:, None] + ub_vec[None, :]
            i_flat = int(np.argmax(S_mat))
            i_ra, i_rb = divmod(i_flat, rb_ids.size)
            val = float(S_mat[i_ra, i_rb])
            if val > best_val:
                best_val = val
                best_act = ((sa, int(ra_ids[i_ra])), (sb, int(rb_ids[i_rb])))
        greedy_cache[key] = (best_act, best_val)
        return greedy_cache[key]

    # --- Top-X branching set per state (on pruned space), memoized ---
    topx_cache = {}
    def select_top_actions(per_stage):
        key = per_stage_to_flat(per_stage)
        cached = topx_cache.get(key)
        if cached is not None:
            return list(cached)

        cand_list = []
        for (sa, sb) in stage_pairs:
            for ra in stage_candidates[sa]:
                for rb in stage_candidates[sb]:
                    cand_list.append(((sa, ra), (sb, rb)))

        vals = []
        for ((sa, ra), (sb, rb)) in cand_list:
            vals.append(imm_ua_plus_ub(sa, ra, sb, rb, per_stage))
        vals = np.asarray(vals, dtype=float)

        if len(cand_list) > X:
            idx = np.argpartition(vals, -X)[-X:]
            idx = idx[np.argsort(vals[idx])[::-1]]
            selected = [cand_list[i] for i in idx]
        else:
            order = np.argsort(vals)[::-1]
            selected = [cand_list[i] for i in order]

        topx_cache[key] = selected
        return list(selected)

    def branch_set_with_default(per_stage):
        # dominance-safe: ensure the full greedy act is available too
        topX = select_top_actions(per_stage)
        g_act, _ = greedy_action_full(per_stage)
        if g_act not in topX:
            topX.append(g_act)
        return topX

    # --- MC continuation value (epsilon-greedy), depth >= 0 ---
    def continuation_value_mc(start_action, per_stage, depth):
        if depth <= 0:
            return 0.0

        acc = 0.0
        for _ in range(S):
            # Copy state and apply the chosen candidate first
            lds = {s: per_stage[s].copy() for s in per_stage}
            (sa, ra), (sb, rb) = start_action
            total = imm_ua_plus_ub(sa, ra, sb, rb, lds)
            lds[sa][ra - 1] += 1
            lds[sb][rb - 1] += 1

            # Simulate remaining steps
            for __ in range(depth - 1):
                if rng.random() < (1.0 - eps):
                    # Greedy over FULL space
                    act, _ = greedy_action_full(lds)
                else:
                    # Random from Top-X (on pruned space)
                    cands = branch_set_with_default(lds)
                    act = cands[rng.integers(low=0, high=len(cands))]

                (s1, r1), (s2, r2) = act
                total += imm_ua_plus_ub(s1, r1, s2, r2, lds)
                lds[s1][r1 - 1] += 1
                lds[s2][r2 - 1] += 1

            acc += total

        return acc / float(S)

    # --- Deterministic greedy tail used when depth==0 (memoized) ---
    @lru_cache(maxsize=None)
    def greedy_tail_value(loads_tuple):
        per_stage = flat_to_per_stage(loads_tuple)
        loads_arr = np.asarray(loads_tuple, dtype=int)
        players_assigned = int(loads_arr.sum()) // 2
        if players_assigned >= N:
            return 0.0
        total = 0.0
        lds = {s: per_stage[s].copy() for s in per_stage}
        for _ in range(players_assigned, N):
            (s1r1, s2r2), _ = greedy_action_full(lds)
            (s1, r1), (s2, r2) = s1r1, s2r2
            total += imm_ua_plus_ub(s1, r1, s2, r2, lds)
            lds[s1][r1 - 1] += 1
            lds[s2][r2 - 1] += 1
        return float(total)

    # --- Policy wrapper: mapping-like object; key = flattened loads tuple ---
    class RolloutPolicyDict:
        def __getitem__(self, key):
            # key is a flattened tuple of loads
            loads_tuple = tuple(key)
            per_stage = flat_to_per_stage(loads_tuple)

            # Evaluate candidates via MC continuation averaging
            best_val = -float("inf")
            best_act = None
            for act in branch_set_with_default(per_stage):
                (sa, ra), (sb, rb) = act
                imm = imm_ua_plus_ub(sa, ra, sb, rb, per_stage)

                # If no lookahead requested, use greedy tail value
                if D <= 0 or S <= 1:
                    # Apply act then greedy to the end
                    per_stage[sa][ra - 1] += 1
                    per_stage[sb][rb - 1] += 1
                    cont = greedy_tail_value(per_stage_to_flat(per_stage))
                    per_stage[sa][ra - 1] -= 1
                    per_stage[sb][rb - 1] -= 1
                else:
                    cont = continuation_value_mc(act, per_stage, D)

                total = imm + cont
                if total > best_val:
                    best_val = total
                    best_act = act

            return best_act

        def get(self, key, default=None):
            try:
                return self.__getitem__(key)
            except Exception:
                return default

    return RolloutPolicyDict(), grids_by_stage





# claude.py
def embedding_budgeted(
    policy,
    num_of_stages,
    num_of_replicas,
    flow_list,
    stage_budget=HYBRID_STAGE_BUDGET,
):
    """
    Forward simulation:
    - Global loads over all stages and replicas.
    - For each flow, query policy[current_loads] → ((s1,r1),(s2,r2))
    - Increment those two replica loads and record the choices.

    Returns:
      embed_log: dict flow -> list of (stage, replica) chosen (length=2)
      final_loads_tuple: flattened tuple of loads after assigning all flows
    """
    require_hybrid_stage_budget(stage_budget)
    if num_of_stages <= stage_budget:
        raise ValueError(
            "Hybrid requires more available stages than its selected-stage "
            "budget so one stage can be bypassed"
        )

    # global loads: stage-major blocks
    per_stage = {s: np.zeros(num_of_replicas, dtype=int) for s in range(1, num_of_stages + 1)}

    def flatten(ps): return tuple(np.concatenate([ps[s] for s in range(1, num_of_stages + 1)]).tolist())

    embed_log = {f: [] for f in flow_list}

    for f in flow_list:
        choice = policy[flatten(per_stage)]
        if len(choice) != stage_budget:
            raise ValueError(
                f"policy returned {len(choice)} choices; expected L={stage_budget}"
            )
        (sa, ra), (sb, rb) = choice
        if sa == sb:
            raise ValueError("Hybrid policy choices must use distinct stages")
        if not (1 <= sa <= num_of_stages and 1 <= sb <= num_of_stages):
            raise ValueError("Hybrid policy returned an invalid stage ID")
        if not (1 <= ra <= num_of_replicas and 1 <= rb <= num_of_replicas):
            raise ValueError("Hybrid policy returned an invalid replica ID")

        # update loads
        per_stage[sa][ra - 1] += 1
        per_stage[sb][rb - 1] += 1

        embed_log[f] = [(sa, ra), (sb, rb)]

    return embed_log, flatten(per_stage)

from collections import Counter

def latency(embed_log, flow_list, replica_list):
    """
    Order-independent latency:
    base link latency + congestion from *all* other flows that chose either replica.
    """
    link_latency = {
        (4, 4): 3, (4, 3): 4, (4, 2): 9, (4, 1): 13,
        (3, 3): 7, (3, 2): 13, (3, 1): 15,
        (2, 2): 9, (2, 1): 25,
        (1, 1): 25,
        (3, 4): 4, (2, 4): 9, (1, 4): 13,
        (2, 3): 13, (1, 3): 15,
        (1, 2): 25,
    }

    # 1) Count total selections per (stage, replica) over ALL flows
    totals = Counter()
    for f, ((sa, ra), (sb, rb)) in embed_log.items():
        totals[(sa, ra)] += 1
        totals[(sb, rb)] += 1

    # 2) Per-flow latency = base + (others on sa,ra) + (others on sb,rb)
    per_flow_latency = {}
    for f, ((sa, ra), (sb, rb)) in embed_log.items():
        s1 = replica_list[(sa, ra)].state
        s2 = replica_list[(sb, rb)].state
        base = link_latency[(s1, s2)]

        # subtract this flow's own two selections (one on each replica)
        congestion = (totals[(sa, ra)] - 1) + (totals[(sb, rb)] - 1)

        # same weight as your current code (1x); tweak if you want a stronger penalty
        per_flow_latency[f] = base + 3 * congestion

    return per_flow_latency
