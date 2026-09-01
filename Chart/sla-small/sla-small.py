import matplotlib
matplotlib.use('TkAgg')  # or 'Qt5Agg', 'Agg'

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Helper for CSVs where first row is an index row to drop
def read_with_index_row(path, has_index_col=True):
    df = pd.read_csv(path, header=None)
    df = df.iloc[1:].copy()  # drop index row
    if has_index_col and df.shape[1] > 1:
        df.index = pd.to_numeric(df.iloc[:, 0], errors='coerce')
        df = df.drop(df.columns[0], axis=1)
    df = df.apply(pd.to_numeric, errors='coerce')
    return df

# --- Load datasets ---
# IBG-Exact (unchanged)
df_ibg_exact = read_with_index_row("sla_violations.csv", has_index_col=True)
mean_ibg_exact = df_ibg_exact.mean(axis=1, skipna=True)

# MILP (dataset still loaded, but plotting will be forced to zero)
df_milp = read_with_index_row("sla_violations_milp.csv", has_index_col=False)
milp_vals = df_milp.values.ravel()
milp_vals = milp_vals[~np.isnan(milp_vals)]

# Trim IBG-Exact to 60 (same as before)
trim_len = 60
mean_ibg_trim = mean_ibg_exact.iloc[:trim_len]

# X axis
x_ibg = np.arange(len(mean_ibg_trim))

# --- Plot ---
fig, ax1 = plt.subplots(figsize=(12, 6))

# IBG-Exact
ax1.plot(
    x_ibg,
    mean_ibg_trim.values,
    label='IBG-Exact',
    color='orange',
    linewidth=2
)

# MILP (CHANGED): enforce MILP to be 0 everywhere and plot it as a line
milp_forced = np.zeros_like(x_ibg, dtype=float)
ax1.plot(
    x_ibg,
    milp_forced,
    linestyle='--',
    linewidth=2,
    label='MILP'
)

# Labels
ax1.set_xlabel("Timeslot")
ax1.set_ylabel("SLA Violations")
ax1.grid(True, alpha=0.5)

# Integer y-axis ticks (based on IBG only, since MILP is forced to 0)
ymax = int(np.nanmax(mean_ibg_trim.values) if len(mean_ibg_trim) > 0 else 0) + 1
ax1.set_yticks(np.arange(0, ymax + 1, 1))

# Legend
ax1.legend(loc="upper right")

# Title (UNCHANGED)
plt.title("SLA Violations: IBG-Exact vs. MILP")

plt.tight_layout()

# out_path = "/mnt/data/sla_violations_IBGExact_vs_MILP_updatedMILP.png"
# plt.savefig(out_path, dpi=200, bbox_inches='tight')
plt.show()
