import matplotlib
matplotlib.use("TkAgg")  # Use GUI backend (TkAgg) — must be before importing pyplot

import pandas as pd
import matplotlib.pyplot as plt

# Load CSV
df = pd.read_csv(r"D:\Uni\Thesis\Payanname\py\thesis\IBG\results.csv")

# Calculate average iterations
avg_iterations = df["Iterations"].mean()

# Plot
plt.figure(figsize=(8, 5))
plt.plot(
    df.index + 1,
    df["Iterations"],
    marker='o',
    color="#ff7f0e",           # orange
    label="Iterations per Run"
)
plt.axhline(
    y=avg_iterations,
    color="#ff0000",           # red
    linestyle='--',
    linewidth=2,
    label="Average"
)

# Labels and formatting
plt.title("Decoupled - 5 stages, 6 replicas, 7 flows")
plt.xlabel("Run Number")
plt.ylabel("Iterations")
plt.legend()
plt.grid(True)

# Show plot
plt.show()
