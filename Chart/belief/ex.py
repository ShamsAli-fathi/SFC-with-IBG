import matplotlib
matplotlib.use('TkAgg')  # or 'Qt5Agg', 'Agg'

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import ast

# --- Config ---
csv_path = "replica_results.csv"   # or "/mnt/data/replica_results.csv"
replica1_col = "(1, 4)"
replica2_col = "(2, 18)"
ma_window = 5
title = "Posterior Trend For Excellent State \nReplcias Throughout Timeslots: IBG-Hybrid"

def parse_prob_vector(cell):
    if pd.isna(cell):
        return []
    s = str(cell).strip()

    # Remove np.float64 wrappers: np.float64(0.208) -> 0.208
    s = s.replace("np.float64(", "").replace(")", "")

    # Now it's a normal Python list string -> parse it
    return ast.literal_eval(s)

def fourth_prob_series(df, col):
    vecs = df[col].apply(parse_prob_vector)
    return vecs.apply(lambda v: v[3] if len(v) >= 4 else np.nan).to_numpy(dtype=float)

# --- Load + Extract ---
df = pd.read_csv(csv_path)

y1 = fourth_prob_series(df, replica1_col)
y2 = fourth_prob_series(df, replica2_col)

x = np.arange(len(df))

# Moving average (centered)
y1_smooth = pd.Series(y1).rolling(window=ma_window, center=True, min_periods=1).mean().to_numpy()
y2_smooth = pd.Series(y2).rolling(window=ma_window, center=True, min_periods=1).mean().to_numpy()

# --- Plot ---
plt.figure()
plt.plot(x, y1_smooth, label=f"Replica 1")
plt.plot(x, y2_smooth, label=f"Replica 2")

plt.title(title)
plt.xlabel("Timeslot")
plt.ylabel("Excellent State Posterior")
plt.grid(True, alpha=0.5)
plt.legend(loc="lower right")
plt.tight_layout()
plt.show()
