import matplotlib
matplotlib.use("TkAgg")  # Use GUI backend (TkAgg) — must be before importing pyplot

import matplotlib.pyplot as plt
import numpy as np

x = [3, 4, 5, 6, 7, 8]
y = [1089, 1217, 1343, 1391, 1405, 1411]

# Soft colormap
colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(x)))

plt.figure()
bars = plt.bar(x, y, color=colors)

# Draw horizontal lines back to the y-axis
for xi, yi in zip(x, y):
    plt.hlines(y=yi, xmin=0, xmax=xi, colors='gray', linestyles='dashed')

plt.xlabel("Candidate Set Size (C)")
plt.ylabel("Aggregated Utility")
plt.xlim(2.5, 8.5)
plt.title("Sensitivity to candidate set size (C) in Pruning")
plt.tight_layout()
plt.show()
