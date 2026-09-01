#!/usr/bin/env python3
"""Render the moving-average small-scale SLA-violation view.

The primary IBG CSV and optional MILP baseline live beside this script.  The
plot intentionally retains the original moving-average presentation, text,
and visual theme while accepting the current headered run-column CSV format.
"""

import argparse
import os
from pathlib import Path
import tempfile

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "ibg-matplotlib"),
)

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PRIMARY_INPUT_PATTERN = "*_IBG.csv"
MILP_FILENAME = "sla_violations_milp.csv"
DEFAULT_OUTPUT = SCRIPT_DIR / "sla_violations_IBGExact_vs_MILP_updatedMILP.png"
DEFAULT_TITLE = "SLA Violations: IBG-Exact (Moving Average)"
DEFAULT_WINDOW = 5
DEFAULT_LIMIT = 50


def resolve_primary_input(path=None):
    """Return an explicit input or this folder's single ``*_IBG.csv`` file."""
    if path is not None:
        return Path(path)
    matches = sorted(SCRIPT_DIR.glob(PRIMARY_INPUT_PATTERN))
    if not matches:
        raise FileNotFoundError(
            f"no SLA IBG CSV matching {PRIMARY_INPUT_PATTERN!r} in {SCRIPT_DIR}; "
            "supply --input to select a file explicitly"
        )
    if len(matches) > 1:
        names = ", ".join(candidate.name for candidate in matches)
        raise ValueError(
            f"multiple SLA IBG CSV files in {SCRIPT_DIR}: {names}; "
            "supply --input to select one explicitly"
        )
    return matches[0]


def load_sla_runs(path):
    """Return current-format non-negative SLA-violation run columns."""
    try:
        frame = pd.read_csv(path)
    except FileNotFoundError as error:
        raise FileNotFoundError(f"SLA CSV not found: {path}") from error
    if frame.empty:
        raise ValueError(f"SLA CSV has no completed iterations: {path}")
    numeric = frame.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    if numeric.empty:
        raise ValueError(f"SLA CSV has no numeric run columns: {path}")
    if (numeric < 0).any().any():
        raise ValueError(f"SLA CSV contains negative violation counts: {path}")
    return numeric


def load_optional_milp(path=None):
    """Load the legacy MILP file when supplied or present beside this script."""
    source = Path(path) if path is not None else SCRIPT_DIR / MILP_FILENAME
    if not source.exists():
        if path is not None:
            raise FileNotFoundError(f"requested SLA MILP baseline not found: {source}")
        return None
    frame = pd.read_csv(source, header=None)
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    numeric = numeric.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if numeric.empty:
        raise ValueError(f"SLA MILP baseline has no numeric values: {source}")
    return numeric


def render_sla_plot(
    runs,
    output_path,
    *,
    milp=None,
    window=DEFAULT_WINDOW,
    limit=DEFAULT_LIMIT,
    title=DEFAULT_TITLE,
):
    """Render the original 50-slot, five-sample moving-average view."""
    if window <= 0:
        raise ValueError("moving-average window must be positive")
    if limit <= 0:
        raise ValueError("plot limit must be positive")

    mean_ibg = runs.mean(axis=1, skipna=True).iloc[:limit]
    moving_average = mean_ibg.rolling(window=window, min_periods=1).mean()
    timeslots = np.arange(len(mean_ibg))

    figure, axis = plt.subplots(figsize=(12, 6))
    axis.plot(
        timeslots,
        moving_average.values,
        label="IBG-Exact",
        color="orange",
        linewidth=2,
    )
    if milp is not None:
        # Preserve the original version-2 presentation: available MILP input
        # is represented by its forced zero reference line.
        axis.plot(
            timeslots,
            np.zeros_like(timeslots, dtype=float),
            linestyle="--",
            linewidth=2,
            label="MILP",
        )

    ymax = int(np.nanmax(mean_ibg.values) if len(mean_ibg) else 0) + 1
    axis.set_yticks(np.arange(0, ymax + 1, 1))
    axis.set_xlabel("Timeslot")
    axis.set_ylabel("SLA Violations (ms)")
    axis.grid(True, alpha=0.5)
    axis.legend(loc="upper right")
    axis.set_title(title)
    axis.xaxis.set_major_locator(MaxNLocator(integer=True))
    axis.yaxis.set_major_locator(MaxNLocator(integer=True))
    figure.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    return output_path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Plot the moving-average small-scale SLA-violation export."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="primary CSV (default: the one *_IBG.csv file beside this script)",
    )
    parser.add_argument("--milp", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    input_path = resolve_primary_input(args.input)
    output = render_sla_plot(
        load_sla_runs(input_path),
        args.output,
        milp=load_optional_milp(args.milp),
        window=args.window,
        limit=args.limit,
        title=args.title,
    )
    print(f"SLA_SMALL_PLOT={output}")


if __name__ == "__main__":
    main()
