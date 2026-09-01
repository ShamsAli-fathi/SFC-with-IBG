"""Plot the available IBG-Hybrid aggregate utility by timeslot."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_PATH = SCRIPT_DIR / "aggregate_utility_hybrid_20_runs.csv"
OUTPUT_PATH = SCRIPT_DIR / "aggregate_utility_hybrid.png"
MILP_UTILITY = 5304.29
MOVING_AVERAGE_WINDOW = 5


def load_aggregate_utility_runs(path: Path) -> pd.DataFrame:
    """Read the generated Hybrid utility runs, retaining all run columns."""
    runs = pd.read_csv(path).apply(pd.to_numeric, errors="coerce")
    runs = runs.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if runs.empty:
        raise ValueError(f"no numeric aggregate-utility values found in {path}")
    return runs


def main() -> Path:
    aggregate_utility_runs = load_aggregate_utility_runs(INPUT_PATH)
    mean_utility = (
        aggregate_utility_runs.mean(axis=1)
        .rolling(window=MOVING_AVERAGE_WINDOW, min_periods=1)
        .mean()
        .to_numpy()
    )
    standard_deviation = (
        aggregate_utility_runs.std(axis=1, ddof=1)
        .rolling(window=MOVING_AVERAGE_WINDOW, min_periods=1)
        .mean()
        .to_numpy()
    )
    timeslots = np.arange(1, len(mean_utility) + 1)

    figure, axis = plt.subplots(figsize=(12, 6))
    axis.plot(
        timeslots,
        mean_utility,
        color="orange",
        linewidth=2,
        marker="o",
        label=(
            f"IBG-Hybrid ({MOVING_AVERAGE_WINDOW}-Timeslot Moving Average, "
            "20 runs)"
        ),
    )
    axis.fill_between(
        timeslots,
        mean_utility - standard_deviation,
        mean_utility + standard_deviation,
        color="orange",
        alpha=0.25,
        label=f"±1 Std Dev ({MOVING_AVERAGE_WINDOW}-Timeslot Moving Average)",
    )

    # Greedy and DRL comparison plots remain intentionally disabled:
    # their aggregate-utility CSV inputs are not currently provided.
    # axis.plot(..., label="Greedy Myopic")
    # axis.plot(..., label="DRL")
    axis.axhline(
        MILP_UTILITY,
        color="tab:blue",
        linestyle="--",
        linewidth=2,
        label=f"MILP ({MILP_UTILITY:.2f})",
    )

    axis.set_xlabel("Timeslot")
    axis.set_ylabel("End-to-End Utility")
    axis.set_title("End-to-End Utility Throughout Timeslots: IBG-Hybrid vs. MILP")
    axis.set_xlim(timeslots[0], timeslots[-1])
    axis.grid(True, alpha=0.5)
    axis.legend(loc="best")
    figure.tight_layout()
    figure.savefig(OUTPUT_PATH, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return OUTPUT_PATH


if __name__ == "__main__":
    main()
