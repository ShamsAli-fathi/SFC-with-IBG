import matplotlib
matplotlib.use('TkAgg')  # or 'Qt5Agg', 'Agg'

import matplotlib.pyplot as plt
import numpy as np

# Data (your byte comparison applied)
labels = ["IBG-Hybrid", "DRL\n(200 Episodes)"]
values = [4868, 4040541707]
bar_colors = ["moccasin", "lightgreen"]
y_texts = ["4.87 × 10³ Bytes", "4.04 × 10⁹ Bytes"]

x = np.arange(len(labels))

fig, ax = plt.subplots()

# Bars
plt.title("Total Data Footprint in a timeslot (Log Scale): IBG-Hybrid vs. DRL")
ax.bar(x, values, color=bar_colors, edgecolor="black")

# Logarithmic Y-axis
ax.set_yscale("log")

# X axis
ax.set_xticks(x, labels)

# Remove y-axis label and ticks
ax.set_ylabel("Bytes (log scale)")

# Clean spines
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# Custom Y-axis texts aligned with bar heights
for i, (v, txt) in enumerate(zip(values, y_texts)):
    ax.text(
        i, v, txt,
        ha="center", va="bottom"
    )

plt.tight_layout()
plt.show()
