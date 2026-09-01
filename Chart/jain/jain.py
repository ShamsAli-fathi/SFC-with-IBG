#!/usr/bin/env python3
"""Render this folder's Jain-fairness CSV exports with optional baselines.

By default the current primary export is the single ``*_IBG.csv`` file beside
this script, with one run-ID column per experiment and one row per completed
iteration. This script plots the mean across available IBG-Exact run columns
and, when more than one run is present, its per-iteration min--max range.
Historical MILP, DRL, and Greedy files beside the script are optional: absent
files are skipped, while explicitly supplied files retain their legacy
plotting semantics.
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
DEFAULT_INPUT = SCRIPT_DIR / "jain_index_hybrid.csv"
DEFAULT_OUTPUT = SCRIPT_DIR / "jain_index_hybrid.png"
DEFAULT_TITLE = "Jain Fairness Index Throughout Timeslots: IBG-Hybrid"
LEGACY_BASELINES = {
    "milp": "jain_index_milp.csv",
    "drl": "jain_index_drl.csv",
    "greedy": "jain_index_greedy.csv",
}


def resolve_primary_input(path=None):
    """Return an explicit input or this plot folder's one ``*_IBG.csv`` file."""
    if path is not None:
        return Path(path)
    if DEFAULT_INPUT.is_file():
        return DEFAULT_INPUT
    matches = sorted(SCRIPT_DIR.glob(PRIMARY_INPUT_PATTERN))
    if not matches:
        raise FileNotFoundError(
            f"no Jain IBG CSV matching {PRIMARY_INPUT_PATTERN!r} in {SCRIPT_DIR}; "
            "supply --input to select a file explicitly"
        )
    if len(matches) > 1:
        names = ", ".join(candidate.name for candidate in matches)
        raise ValueError(
            f"multiple Jain IBG CSV files in {SCRIPT_DIR}: {names}; "
            "supply --input to select one explicitly"
        )
    return matches[0]


def load_jain_runs(path):
    """Return numeric current-format Jain runs, preserving run columns."""
    try:
        frame = pd.read_csv(path)
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Jain CSV not found: {path}") from error
    if frame.empty:
        raise ValueError(f"Jain CSV has no completed iterations: {path}")

    numeric = frame.apply(pd.to_numeric, errors="coerce")
    numeric = numeric.dropna(axis=1, how="all")
    if numeric.empty:
        raise ValueError(f"Jain CSV has no numeric run columns: {path}")
    if (numeric < 0).any().any() or (numeric > 1).any().any():
        raise ValueError(f"Jain CSV contains values outside [0, 1]: {path}")
    return numeric


def _load_legacy_numeric(path):
    frame = pd.read_csv(path, header=None)
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    numeric = numeric.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if numeric.empty:
        raise ValueError(f"baseline Jain CSV has no numeric values: {path}")
    if (numeric < 0).any().any() or (numeric > 1).any().any():
        raise ValueError(f"baseline Jain CSV contains values outside [0, 1]: {path}")
    return numeric


def _resolve_optional_baseline(path, filename):
    if path is not None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"requested Jain baseline not found: {path}")
        return path
    candidate = SCRIPT_DIR / filename
    if candidate.exists():
        return candidate
    return None


def load_optional_baselines(input_path, *, milp=None, drl=None, greedy=None):
    """Load supplied or discovered legacy baselines, skipping absent files."""
    requested = {"milp": milp, "drl": drl, "greedy": greedy}
    baselines = {}
    for name, path in requested.items():
        source = _resolve_optional_baseline(
            path,
            LEGACY_BASELINES[name],
        )
        if source is None:
            continue
        numeric = _load_legacy_numeric(source)
        if name == "milp":
            values = numeric.to_numpy(dtype=float)
            baselines[name] = {"kind": "constant", "value": float(np.nanmean(values))}
        elif name == "drl":
            baselines[name] = {
                "kind": "series",
                "values": numeric.iloc[0].dropna().to_numpy(dtype=float),
            }
        else:
            # The historical Greedy CSV carries a leading index column.
            values = numeric.iloc[:, 1:] if numeric.shape[1] > 1 else numeric
            baselines[name] = {
                "kind": "series",
                "values": values.mean(axis=1, skipna=True).to_numpy(dtype=float),
            }
    return baselines


def render_jain_plot(frame, output_path, *, baselines=None, title=DEFAULT_TITLE):
    """Plot the IBG-Hybrid Jain mean/range and any supplied baselines."""
    baselines = baselines or {}
    iterations = np.arange(1, len(frame) + 1)
    mean = frame.mean(axis=1, skipna=True)
    lower = frame.min(axis=1, skipna=True)
    upper = frame.max(axis=1, skipna=True)

    figure, axis = plt.subplots(figsize=(12, 6))
    axis.plot(
        iterations,
        mean,
        color="orange",
        linewidth=2,
        label=(
            "IBG-Hybrid"
            if len(frame.columns) == 1
            else f"IBG-Hybrid mean across {len(frame.columns)} runs"
        ),
    )
    if len(frame.columns) > 1:
        axis.fill_between(
            iterations,
            lower,
            upper,
            color="orange",
            alpha=0.2,
            label="IBG-Hybrid min--max across runs",
        )
    # MILP, DRL, and Greedy comparison plots remain intentionally disabled:
    # their Jain-index CSV inputs are not currently provided.
    # axis.axhline(..., label="MILP")
    # axis.plot(..., label="DRL")
    # axis.plot(..., label="Greedy Myopic")
    axis.set_ylim(0.8, 1.0)
    axis.set_xlabel("Timeslot")
    axis.set_ylabel("Jain fairness index")
    axis.set_title(title)
    axis.set_xlim(iterations[0], iterations[-1])
    axis.xaxis.set_major_locator(MaxNLocator(integer=True))
    axis.grid(True, alpha=0.5)
    axis.legend(loc="lower right")
    figure.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    return output_path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Plot current Jain-fairness CSV exports."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="primary CSV (default: the one *_IBG.csv file beside this script)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--milp", type=Path, default=None)
    parser.add_argument("--drl", type=Path, default=None)
    parser.add_argument("--greedy", type=Path, default=None)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    input_path = resolve_primary_input(args.input)
    runs = load_jain_runs(input_path)
    # Baseline loading remains disabled until its corresponding CSVs are supplied.
    baselines = {}
    output = render_jain_plot(
        runs,
        args.output,
        baselines=baselines,
        title=args.title,
    )
    print(
        f"JAIN_PLOT={output} iterations={len(runs)} "
        f"run_columns={len(runs.columns)} baselines={','.join(sorted(baselines)) or 'none'}"
    )


if __name__ == "__main__":
    main()
