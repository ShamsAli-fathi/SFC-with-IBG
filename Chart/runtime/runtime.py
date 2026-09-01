import matplotlib
matplotlib.use('TkAgg')  # or 'Qt5Agg', 'Agg'

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Data
mean_ibg = 2.8914
mean_milp = 5.9478

labels = ["IBG-Hybrid", "MILP"]
means = [mean_ibg, mean_milp]

plt.figure(figsize=(8,5))
x = np.arange(len(labels))

plt.bar(
    x, means,
    color=["lightgreen", "lightpink"],
    edgecolor="black"
)

plt.xticks(x, labels)
plt.ylabel("Time (seconds)")
plt.title("Runtime per slot on large-scale topology: IBG-Hybrid vs. MILP")
plt.grid(True, linestyle="--", alpha=0.6, axis="y")

# Annotate bars
for xi, m in zip(x, means):
    plt.text(xi, m, f"{m:.4f} s", ha="center", va="bottom", fontsize=10)

plt.show()