import matplotlib
matplotlib.use('TkAgg')  # or 'Qt5Agg', 'Agg'

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

import matplotlib.pyplot as plt

# Define your text legend entries
legend_text = [
    "C1: SFC Rules Push",
"C2: Status Reporting",
"C3: SF Statistics",
"C4: Proxy Feedback"
]

# Create a figure with no axes
fig, ax = plt.subplots(figsize=(5, 2))

# Remove axes
ax.axis('off')

# Add text as legend (positioned manually)
for i, text in enumerate(legend_text):
    ax.text(0.05, 1 - i * 0.2, text, transform=ax.transAxes, fontsize=12,
            verticalalignment='center', horizontalalignment='left',
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray", alpha=0.7))

# Adjust layout
plt.tight_layout()
plt.show()