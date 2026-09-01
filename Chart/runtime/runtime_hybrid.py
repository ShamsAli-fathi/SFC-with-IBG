"""Render completed IBG-Hybrid timeslot wall time as a box plot."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parents[1]
INPUT_PATH = REPOSITORY_ROOT / "figures" / "IBG_hybrid" / "time.csv"
OUTPUT_PATH = SCRIPT_DIR / "runtime_hybrid.png"
IBG_ORANGE = "#ff7f0e"
TITLE = "Completed Timeslot Runtime: IBG-Hybrid"


def load_timeslot_seconds(path: Path) -> np.ndarray:
    """Read one Hybrid time series, ignoring its run-hash metadata row."""
    values = pd.to_numeric(pd.read_csv(path, header=None).iloc[:, 0], errors="coerce")
    values = values.dropna().to_numpy(dtype=float)
    if not len(values):
        raise ValueError(f"no numeric timeslot values found in {path}")
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError(f"timeslot values must be finite and nonnegative: {path}")
    return values


def main() -> Path:
    timeslot_seconds = load_timeslot_seconds(INPUT_PATH)
    figure, axis = plt.subplots(figsize=(12, 6))
    box = axis.boxplot(
        timeslot_seconds,
        patch_artist=True,
        tick_labels=["IBG-Hybrid"],
        medianprops={"color": "black", "linewidth": 2},
        whiskerprops={"color": IBG_ORANGE, "linewidth": 1.5},
        capprops={"color": IBG_ORANGE, "linewidth": 1.5},
        flierprops={"markerfacecolor": IBG_ORANGE, "markeredgecolor": IBG_ORANGE},
    )
    for patch in box["boxes"]:
        patch.set(facecolor=IBG_ORANGE, alpha=0.75)
    axis.set_xlabel("")
    axis.set_ylabel("Completed timeslot wall time (s)")
    axis.set_title(TITLE)
    axis.grid(True, axis="y", alpha=0.5)
    figure.tight_layout()
    figure.savefig(OUTPUT_PATH, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return OUTPUT_PATH


if __name__ == "__main__":
    main()
