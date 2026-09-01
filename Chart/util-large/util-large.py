import matplotlib
matplotlib.use('TkAgg')  # or 'Qt5Agg', 'Agg'

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def read_with_index_row(path, has_index_col=True):
    df = pd.read_csv(path, header=None)
    df = df.iloc[1:].copy()
    if has_index_col and df.shape[1] > 1:
        idx = pd.to_numeric(df.iloc[:, 0], errors='coerce')
        if idx.notna().all():
            df.index = idx
        df = df.drop(df.columns[0], axis=1)
    df = df.apply(pd.to_numeric, errors='coerce')
    return df

# Load datasets (unchanged handling)
df_ibg = read_with_index_row("aggregate_utility_IBG.csv", True)
df_greedy = read_with_index_row("aggregate_utility_greedy.csv", True)
df_milp = read_with_index_row("aggregate_utility_milp.csv", False)
df_drl = read_with_index_row("aggregate_utility_drl.csv", False)

# Compute stats
mean_ibg = df_ibg.mean(axis=1).to_numpy()
std_ibg = df_ibg.std(axis=1).to_numpy()

mean_greedy = df_greedy.mean(axis=1).to_numpy()
std_greedy = df_greedy.std(axis=1).to_numpy()

milp_vals = df_milp.values.ravel()
milp_vals = milp_vals[np.isfinite(milp_vals)]
milp_mean = milp_vals.mean()

drl_vals = df_drl.values.ravel()
drl_vals_clean = drl_vals[np.isfinite(drl_vals)]
drl_mean = drl_vals_clean.mean()

# Trim IBG & Greedy to 60
trim_len = 60
mean_ibg_60 = mean_ibg[:trim_len]
std_ibg_60 = std_ibg[:trim_len]

mean_greedy_60 = mean_greedy[:trim_len]
std_greedy_60 = std_greedy[:trim_len]

x_iter = np.arange(trim_len)

# Plot (style preserved)
fig, ax1 = plt.subplots(figsize=(12, 6))

# IBG-Hybrid
ax1.plot(x_iter, mean_ibg_60, color="orange", linewidth=2, label="IBG-Hybrid")
ax1.fill_between(
    x_iter,
    mean_ibg_60 - std_ibg_60,
    mean_ibg_60 + std_ibg_60,
    color="orange",
    alpha=0.25,
    label="±1 Std Dev (IBG-Hybrid)"
)

# Greedy Myopic
ax1.plot(x_iter, mean_greedy_60, color="red", linewidth=2, label="Greedy Myopic")
ax1.fill_between(
    x_iter,
    mean_greedy_60 - std_greedy_60,
    mean_greedy_60 + std_greedy_60,
    color="red",
    alpha=0.2,
    label="±1 Std Dev (Greedy Myopic)"
)

ax1.set_xlabel("Timeslot")
ax1.set_ylabel("Aggregated Utility")
ax1.grid(True, alpha=0.5)

# MILP mean as horizontal line
ax1.axhline(
    milp_mean,
    linestyle="--",
    linewidth=2,
    color="tab:blue",
    label=f'MILP ({milp_mean:.2f})'
)

# =======================
# DRL: plot all CSV values
# X-axis = columns, Y-axis = values
# =======================
drl_matrix = df_drl.to_numpy()

for i in range(drl_matrix.shape[0]):
    ax1.plot(
        np.arange(drl_matrix.shape[1]),
        drl_matrix[i],
        color="green",
        alpha=0.5
    )

# single legend entry for DRL
ax1.plot([], [], color="green", label="DRL")

ax1.legend(loc="lower right")
plt.title("Aggregate Utility of IBG-Hybrid vs. Baselines on large-scale topology")
plt.tight_layout()

# plt.savefig("ibg_hybrid_milp_mean_drl_original_style.png", dpi=200, bbox_inches="tight")
plt.show()
