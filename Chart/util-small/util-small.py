"""Plot small-scale aggregate-utility runs from local CSV inputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MaxNLocator


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = SCRIPT_DIR / "realized_end_to_end_utility.png"
DEFAULT_TITLE = "Aggregated Realized End-to-End Utility of IBG-Exact on small-scale topology"


def load_utility_runs(path: Path) -> pd.DataFrame:
    """Load current headered IBG run columns without treating one as an index."""
    runs = pd.read_csv(path).apply(pd.to_numeric, errors="coerce")
    runs = runs.dropna(axis=1, how="all").dropna(axis=0, how="all")
    if runs.empty:
        raise ValueError(
            f"realized-end-to-end-utility CSV has no numeric run values: {path}"
        )
    return runs


def resolve_primary_input() -> Path:
    candidates = sorted(SCRIPT_DIR.glob("*_IBG.csv"))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(
            f"no IBG CSV found beside the script in {SCRIPT_DIR}; "
            "add realized_end_to_end_utility_IBG.csv or pass --input"
        )
    raise ValueError(
        "multiple realized-end-to-end-utility IBG CSV files found beside the script; "
        "pass --input to select one"
    )


def load_optional_milp(path: Path | None = None) -> np.ndarray | None:
    """Load an optional legacy MILP series from this plot's own folder."""
    source = (
        path
        if path is not None
        else SCRIPT_DIR / "realized_end_to_end_utility_milp.csv"
    )
    if not source.exists():
        return None
    values = pd.read_csv(source, header=None).apply(pd.to_numeric, errors="coerce")
    series = values.to_numpy().ravel()
    series = series[np.isfinite(series)]
    if not len(series):
        raise ValueError(f"MILP CSV has no numeric values: {source}")
    return series


def render_utility_plot(
    runs: pd.DataFrame,
    output: Path,
    *,
    milp: np.ndarray | None = None,
    title: str = DEFAULT_TITLE,
) -> Path:
    """Render the original IBG curve and its run-to-run standard-deviation band."""
    mean_ibg = runs.mean(axis=1, skipna=True)
    std_ibg = runs.std(axis=1, skipna=True)
    limit = min(70, len(mean_ibg))
    mean_ibg = mean_ibg.iloc[:limit].rolling(window=5, min_periods=1).mean()
    std_ibg = std_ibg.iloc[:limit].rolling(window=5, min_periods=1).mean()
    x_ibg = np.arange(limit)

    figure, axis = plt.subplots(figsize=(10, 5))
    axis.plot(x_ibg, mean_ibg.values, label="IBG-Exact", linewidth=2, color="orange")
    axis.fill_between(
        x_ibg,
        (mean_ibg - std_ibg).values,
        (mean_ibg + std_ibg).values,
        alpha=0.2,
        label="±1 Std Dev (IBG-Exact)",
        color="orange",
    )
    axis.set_xlabel("Timeslot")
    axis.set_ylabel("Realized End-to-End Utility")
    axis.xaxis.set_major_locator(MaxNLocator(integer=True))
    axis.set_ylim(2500, 3500)
    axis.grid(True, alpha=0.5)

    if milp is not None:
        milp_avg = float(np.mean(milp))
        axis.axhline(
            y=milp_avg,
            linestyle="--",
            linewidth=2,
            label=f"MILP ({milp_avg:.2f})",
        )

    axis.legend(loc="lower right")
    axis.set_title(title)
    figure.tight_layout()
    figure.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, help="headered IBG realized-end-to-end-utility CSV"
    )
    parser.add_argument(
        "--milp", type=Path, help="optional MILP series CSV (defaults beside this script)"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> Path:
    args = parse_args(argv)
    source = args.input if args.input is not None else resolve_primary_input()
    return render_utility_plot(
        load_utility_runs(source),
        args.output,
        milp=load_optional_milp(args.milp),
        title=args.title,
    )


if __name__ == "__main__":
    main()
