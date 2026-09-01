"""Plot all four posterior-state trends for two selected IBG replicas."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "figures" / "IBG_hybrid" / "replica_results.csv"
DEFAULT_OUTPUT = SCRIPT_DIR / "belief_all_hybrid.png"
DEFAULT_TITLE = "State Posteriors of Excellent and Good Replicas Throughout Timeslots: IBG-Hybrid"
STATE_COLORS = ["#d62728", "#ff7f0e", "#1f77b4", "#2ca02c"]
STATE_LABELS = ["Degraded", "Bad", "Good", "Excellent"]
REPLICA_MARKERS = ["o", "*"]
DEFAULT_REPLICAS = ["(1, 5)", "(1, 9)"]
REPLICA_LABELS = ["Excellent Replica (1, 5)", "Good Replica (1, 9)"]


def parse_prob_vector(cell: object) -> list[float]:
    if pd.isna(cell):
        return []
    text = str(cell).strip().replace("np.float64(", "").replace(")", "")
    try:
        values = ast.literal_eval(text)
    except (SyntaxError, ValueError) as error:
        raise ValueError(f"invalid posterior vector: {cell!r}") from error
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError(f"expected four posterior values, got: {cell!r}")
    probabilities = [float(value) for value in values]
    if not np.isfinite(probabilities).all():
        raise ValueError(f"posterior vector contains a non-finite value: {cell!r}")
    return probabilities


def load_belief_runs(path: Path) -> pd.DataFrame:
    runs = pd.read_csv(path)
    if runs.empty or not len(runs.columns):
        raise ValueError(f"belief CSV has no replica columns: {path}")
    return runs


def resolve_primary_input() -> Path:
    if DEFAULT_INPUT.is_file():
        return DEFAULT_INPUT
    candidates = sorted(SCRIPT_DIR.glob("*_IBG.csv"))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(
            f"no default Hybrid CSV found at {DEFAULT_INPUT} and no IBG CSV found "
            f"beside the script in {SCRIPT_DIR}; pass --input"
        )
    raise ValueError(
        "multiple belief IBG CSV files found beside the script; "
        "pass --input to select one"
    )


def select_replicas(runs: pd.DataFrame, requested: list[str] | None = None) -> list[str]:
    replicas = requested if requested is not None else DEFAULT_REPLICAS
    if len(replicas) != 2:
        raise ValueError("select exactly two replica columns")
    missing = [replica for replica in replicas if replica not in runs.columns]
    if missing:
        raise ValueError(f"replica columns not found: {', '.join(missing)}")
    return replicas


def posterior_matrix(runs: pd.DataFrame, replica: str) -> np.ndarray:
    return np.asarray(
        [parse_prob_vector(value) for value in runs[replica]], dtype=float
    )


def render_all_beliefs(
    runs: pd.DataFrame,
    output: Path,
    *,
    replicas: list[str],
    title: str = DEFAULT_TITLE,
) -> Path:
    figure, axis = plt.subplots(figsize=(12, 6))
    timeslots = np.arange(len(runs))

    for replica_index, replica in enumerate(replicas):
        values = posterior_matrix(runs, replica)
        for state_index in range(4):
            axis.plot(
                timeslots,
                values[:, state_index],
                color=STATE_COLORS[state_index],
                marker=REPLICA_MARKERS[replica_index],
                markevery=5,
                linewidth=2,
                markersize=8,
            )

    legend_elements = [
        Line2D(
            [0],
            [0],
            marker=REPLICA_MARKERS[index],
            color="black",
            linestyle="None",
            label=REPLICA_LABELS[index],
        )
        for index in range(len(replicas))
    ] + [
        Line2D([0], [0], color=color, lw=2, label=label)
        for color, label in zip(STATE_COLORS, STATE_LABELS, strict=True)
    ]
    axis.legend(handles=legend_elements, loc="best")
    axis.set_title(title)
    axis.set_xlabel("Timeslot")
    axis.set_ylabel("State Posteriors")
    axis.xaxis.set_major_locator(MaxNLocator(integer=True))
    axis.margins(x=0.05)
    axis.grid(True, alpha=0.4)
    figure.tight_layout()
    figure.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="IBG replica-results CSV")
    parser.add_argument(
        "--replica",
        action="append",
        dest="replicas",
        help="replica column to plot (repeat exactly twice to override defaults)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> Path:
    args = parse_args(argv)
    source = args.input if args.input is not None else resolve_primary_input()
    runs = load_belief_runs(source)
    return render_all_beliefs(
        runs,
        args.output,
        replicas=select_replicas(runs, args.replicas),
        title=args.title,
    )


if __name__ == "__main__":
    main()
