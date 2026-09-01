"""Summarize IBG-Hybrid application-body control-plane bytes with a box plot."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_PATH = SCRIPT_DIR / "control_plane_payload_total_bytes_hybrid.csv"
OUTPUT_PATH = SCRIPT_DIR / "control_plane_payload_total_bytes_hybrid.png"
IBG_ORANGE = "#ff7f0e"
TITLE = "Application-body Control-Plane Payload: IBG-Hybrid"
BYTES_PER_MEGABYTE = 1_000_000


def load_payload_bytes(path: Path) -> np.ndarray:
    """Read the one-column Hybrid payload series, ignoring its metadata row."""
    values = pd.to_numeric(pd.read_csv(path, header=None).iloc[:, 0], errors="coerce")
    values = values.dropna().to_numpy()
    if not len(values):
        raise ValueError(f"no numeric payload-byte values found in {path}")
    return values


def main() -> Path:
    payload_megabytes = load_payload_bytes(INPUT_PATH) / BYTES_PER_MEGABYTE
    figure, axis = plt.subplots(figsize=(12, 6))
    box = axis.boxplot(
        payload_megabytes,
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
    axis.set_ylabel("Application-body control-plane payload (MB)")
    axis.set_title(TITLE)
    axis.grid(True, axis="y", alpha=0.5)
    figure.tight_layout()
    figure.savefig(OUTPUT_PATH, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return OUTPUT_PATH


if __name__ == "__main__":
    main()
