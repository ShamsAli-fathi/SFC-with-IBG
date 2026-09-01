"""Plot the available IBG-Hybrid end-to-end SLA excess by timeslot."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_PATH = SCRIPT_DIR / "end_to_end_sla_excess_ms_hybrid.csv"
OUTPUT_PATH = SCRIPT_DIR / "end_to_end_sla_excess_ms_hybrid.png"
MOVING_AVERAGE_WINDOW = 5


def load_sla_excess(path: Path) -> np.ndarray:
    """Read the single Hybrid SLA-excess series, ignoring its metadata row."""
    values = pd.to_numeric(pd.read_csv(path, header=None).iloc[:, 0], errors="coerce")
    values = values.dropna().to_numpy()
    if not len(values):
        raise ValueError(f"no numeric end-to-end SLA-excess values found in {path}")
    return values


def main() -> Path:
    sla_excess = load_sla_excess(INPUT_PATH)
    moving_average = (
        pd.Series(sla_excess)
        .rolling(window=MOVING_AVERAGE_WINDOW, min_periods=1)
        .mean()
        .to_numpy()
    )
    timeslots = np.arange(1, len(moving_average) + 1)

    figure, axis = plt.subplots(figsize=(12, 6))
    axis.plot(
        timeslots,
        moving_average,
        color="orange",
        linewidth=2,
        marker="o",
        label=f"IBG-Hybrid ({MOVING_AVERAGE_WINDOW}-Timeslot Moving Average)",
    )

    # Greedy, MILP, and DRL comparison plots remain intentionally disabled:
    # their end-to-end SLA-excess CSV inputs are not currently provided.
    # axis.plot(..., label="Greedy Myopic")
    # axis.axhline(..., label="MILP")
    # axis.plot(..., label="DRL")

    axis.set_xlabel("Timeslot")
    axis.set_ylabel("End-to-End SLA Excess (ms)")
    axis.set_title("End-to-End SLA Excess Throughout Timeslots: IBG-Hybrid")
    axis.set_xlim(timeslots[0], timeslots[-1])
    axis.grid(True, alpha=0.5)
    axis.legend(loc="best")
    figure.tight_layout()
    figure.savefig(OUTPUT_PATH, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return OUTPUT_PATH


if __name__ == "__main__":
    main()
