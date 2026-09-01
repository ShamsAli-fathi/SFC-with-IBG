import matplotlib
matplotlib.use('TkAgg')  # or 'Qt5Agg', 'Agg'

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def read_with_index_row(csv_file, index_is_col=False):
    """
    Reads a CSV file and sets the first row as the header (column names).
    If index_is_col is True, also set the first column as an index.
    """
    df = pd.read_csv(csv_file, header=0)
    if index_is_col:
        df.set_index(df.columns[0], inplace=True)
    return df


# Read CSV files
df_ibg = read_with_index_row("aggregate_utility_ibg.csv", False)
df_greedy = read_with_index_row("aggregate_utility_greedy.csv", False)
df_drl = read_with_index_row("new_drl.csv", False)
df_milp = read_with_index_row("aggregate_utility_milp.csv", False)


# Compute aggregated mean and std across all timeslots for IBG-Hybrid and Greedy Myopic
mean_ibg = df_ibg.mean(axis=0).to_numpy()
std_ibg = df_ibg.std(axis=0).to_numpy()

mean_greedy = df_greedy.mean(axis=0).to_numpy()
std_greedy = df_greedy.std(axis=0).to_numpy()

# DRL: we might want the mean as reference, but main goal is plotting all values.
drl_vals = df_drl.values.ravel()
drl_vals_clean = drl_vals[np.isfinite(drl_vals)]
drl_mean = drl_vals_clean.mean()

# MILP: single mean value (assuming any NaNs need to be ignored)
milp_vals = df_milp.values.ravel()
milp_vals_clean = milp_vals[np.isfinite(milp_vals)]
milp_mean = milp_vals_clean.mean()

trim_len = min(len(mean_ibg), len(mean_greedy))
mean_ibg_60 = mean_ibg[:trim_len]
std_ibg_60 = std_ibg[:trim_len]
mean_greedy_60 = mean_greedy[:trim_len]
std_greedy_60 = std_greedy[:trim_len]

x_iter = np.arange(trim_len)

# Plot (style preserved)
fig, ax1 = plt.subplots(figsize=(12, 6))

# =======================
# DRL: plot all CSV values
# X-axis = columns, Y-axis = values
# =======================
# X values from CSV header
x_vals = df_drl.columns.astype(float)

# Y values
drl_matrix = df_drl.to_numpy()

for i in range(drl_matrix.shape[0]):
    ax1.plot(
        x_vals,
        drl_matrix[i],
        color="green",
        alpha=0.9
    )
ax1.set_xticks(x_vals)

ax1.set_xlabel("Episodes")
ax1.set_ylabel("Aggregated Utility")
ax1.grid(True, alpha=0.5)

# single legend entry for DRL
ax1.plot([], [], color="green", label="DRL")

ax1.legend(loc="lower right")
plt.title("Aggregated Utility Convergence of DRL Throughout 10000 Episodes")
plt.tight_layout()

# plt.savefig("drl_only_large_topology.png", dpi=200, bbox_inches="tight")
plt.show()
