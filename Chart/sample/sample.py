import matplotlib
matplotlib.use("TkAgg")  # Use GUI backend (TkAgg) — must be before importing pyplot

import matplotlib.pyplot as plt
import numpy as np

# Data
labels = [10, 30, 50]
values = [1252, 1391, 1410]

# Categorical positions (equal spacing)
x_pos = np.arange(len(labels))

colors = plt.cm.cividis(np.linspace(0.3, 0.8, len(labels)))

plt.figure()
plt.bar(x_pos, values, color=colors, width=0.6)

# Horizontal guide lines to y-axis
for xi, yi in zip(x_pos, values):
    plt.hlines(
        y=yi,
        xmin=-0.5,
        xmax=xi,
        colors='gray',
        linestyles='dashed',
        linewidth=1,
        zorder=0
    )

plt.xlabel("Monte Carlo Samples (S)")
plt.ylabel("Aggregated Utility")

# Categorical ticks
plt.xticks(x_pos, labels)

# Clean limits
plt.xlim(-0.5, len(labels) - 0.5)
plt.title("Sensitivity to Monte Carlo samples (S) in Monte Carlo Rollouts")
plt.tight_layout()

plt.show()
