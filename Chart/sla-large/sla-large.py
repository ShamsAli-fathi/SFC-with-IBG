import matplotlib
matplotlib.use("TkAgg")  # Use GUI backend (TkAgg) — must be before importing pyplot

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Helper to read CSVs
def read_with_index_row(path, has_index_col=True):
    df = pd.read_csv(path, header=None)
    df = df.iloc[1:].copy()
    if has_index_col and df.shape[1] > 1:
        df.index = pd.to_numeric(df.iloc[:, 0], errors='coerce')
        df = df.drop(df.columns[0], axis=1)
    df = df.apply(pd.to_numeric, errors='coerce')
    return df

# Load datasets
df_ibg = read_with_index_row("sla_violations.csv", has_index_col=True)
mean_ibg = df_ibg.mean(axis=1, skipna=True)

df_milp = read_with_index_row("sla_violations_milp.csv", has_index_col=False)
milp_vals = df_milp.values.ravel()
milp_vals = milp_vals[~np.isnan(milp_vals)]
milp_avg = np.mean(milp_vals)

df_greedy = read_with_index_row("sla_violations_greedy.csv", has_index_col=True)
mean_greedy = df_greedy.mean(axis=1, skipna=True)

df_drl = read_with_index_row("sla_violations_drl.csv", has_index_col=False)

# Trim
trim_len = 60
mean_ibg_trim = mean_ibg.iloc[:trim_len]
mean_greedy_trim = mean_greedy.iloc[:trim_len]

# X axes
x_ibg = np.arange(len(mean_ibg_trim))
x_greedy = np.arange(len(mean_greedy_trim))

# Plot
fig, ax1 = plt.subplots(figsize=(12, 6))

ax1.plot(x_ibg, mean_ibg_trim.values, label='IBG-Hybrid', linewidth=2, color='orange')
ax1.plot(x_greedy, mean_greedy_trim.values, label='Greedy Myopic', linewidth=2, color='red')

# =======================
# DRL: moving average
# =======================
drl_matrix = df_drl.to_numpy()
window = 5  # moving average window

for i in range(drl_matrix.shape[0]):
    y = drl_matrix[i]
    y_ma = (
        pd.Series(y)
        .rolling(window=window, min_periods=1)
        .mean()
        .to_numpy()
    )

    ax1.plot(
        np.arange(drl_matrix.shape[1]),
        y_ma,
        color='green',
        alpha=0.5
    )

# single legend entry for DRL
ax1.plot([], [], color='green', label='DRL (Moving Average)')

ax1.set_xlabel("Timeslot")
ax1.set_ylabel("SLA Violations")
ax1.grid(True, alpha=0.5)

series_max = np.nanmax([
    mean_ibg_trim.max(),
    mean_greedy_trim.max(),
    milp_vals.max() if len(milp_vals) > 0 else 0,
    np.nanmax(drl_matrix)
])
ax1.set_yticks(np.arange(0, int(series_max) + 2, 1))

ax1.axhline(
    0,
    linestyle='--',
    linewidth=2,
    color='tab:blue',
    label='MILP'
)
ax1.legend(loc="upper right")

# REQUIRED TITLE
plt.title("SLA Violations: IBG-Hybrid vs. Baselines")

plt.tight_layout()

# plt.savefig("sla_violations_drl_raw_version.png", dpi=200, bbox_inches='tight')
plt.show()
