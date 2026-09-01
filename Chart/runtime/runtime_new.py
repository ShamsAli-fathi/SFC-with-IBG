import matplotlib
matplotlib.use('TkAgg')  # or 'Qt5Agg', 'Agg'

import matplotlib.pyplot as plt
import numpy as np

# Data
labels = ["Greedy Myopic", "IBG-Hybrid", "DRL\n(200 Episodes)"]
values = [1, 3, 10]
bar_colors = ["lightcoral", "moccasin", "lightgreen"]
y_texts = ["1.57 Sec", "2.89 Sec", "> 190 Sec"]

x = np.arange(len(labels))

fig, ax = plt.subplots()

# Bars
plt.title("Runtime per slot on large-scale topology: IBG-Hybrid vs. Baselines")
ax.bar(x, values, color=bar_colors, edgecolor="black")

# X axis
ax.set_xticks(x, labels)

# Remove y-axis label and ticks
ax.set_ylabel("")
ax.set_yticks([])

# Clean spines
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# Custom Y-axis texts aligned with bar heights
for v, txt in zip(values, y_texts):
    ax.text(
        -0.02, v, txt,
        transform=ax.get_yaxis_transform(),
        ha="right", va="center"
    )

# Padding so left text is visible
plt.tight_layout()
plt.show()