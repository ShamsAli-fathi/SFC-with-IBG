#!/usr/bin/env python3
"""Plot controller/solver memory footprint from sibling IBG trace summaries."""

import argparse
import csv
import json
from pathlib import Path
import statistics
import sys

import matplotlib.pyplot as plt
import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
IBG_DIR = ROOT / "IBG"
if str(IBG_DIR) not in sys.path:
    sys.path.insert(0, str(IBG_DIR))

from solver_resource import validate_solver_resource_snapshot


IBG_CSV = HERE / "solver_resource_IBG.csv"
OUTPUT = HERE / "solver_resource.png"
MEBIBYTE = 1024 * 1024
IBG_ORANGE = "#ff7f0e"
IBG_LIGHT_ORANGE = "#ffbb78"


def trace_row(trace_path):
    events = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    started = [event for event in events if event.get("event") == "run_started"]
    iterations = [
        event for event in events if event.get("event") == "iteration_completed"
    ]
    completed = [event for event in events if event.get("event") == "run_completed"]
    if len(started) != 1 or not iterations or len(completed) != 1:
        raise ValueError(f"trace is not a completed experiment: {trace_path}")
    if started[0].get("memory_diagnostics") is not True:
        raise ValueError(f"trace was not launched with --memory 1: {trace_path}")

    configuration = started[0]["configuration"]
    stages = int(configuration["stages"])
    snapshots = [
        validate_solver_resource_snapshot(
            event["summary"]["solver_resource"],
            expected_stages=stages,
        )
        for event in iterations
    ]
    return {
        "trace": trace_path.name,
        "flows": int(configuration["flows"]),
        "stages": stages,
        "replicas_per_stage": int(configuration["replicas_per_stage"]),
        "iterations": len(iterations),
        "baseline_rss_mib": statistics.fmean(
            item["rss_bytes"]["before_admission"] / MEBIBYTE
            for item in snapshots
        ),
        "peak_incremental_working_memory_mib": statistics.fmean(
            item["rss_bytes"]["peak_incremental_working_memory"] / MEBIBYTE
            for item in snapshots
        ),
        "peak_rss_mib": statistics.fmean(
            item["rss_bytes"]["peak_during_slot"] / MEBIBYTE
            for item in snapshots
        ),
        "peak_memo_entries": statistics.fmean(
            item["exact_policy"]["peak_memo_entries"] for item in snapshots
        ),
    }


def write_rows(trace_paths):
    rows = [trace_row(path) for path in trace_paths]
    fields = list(rows[0])
    with IBG_CSV.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def read_rows():
    if not IBG_CSV.exists():
        raise FileNotFoundError(
            f"missing {IBG_CSV.name}; refresh it with --traces <trace.jsonl>"
        )
    with IBG_CSV.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError(f"{IBG_CSV.name} has no runs")
    required = {
        "baseline_rss_mib",
        "peak_incremental_working_memory_mib",
        "peak_rss_mib",
        "peak_memo_entries",
    }
    if not required.issubset(rows[0]):
        raise ValueError(f"{IBG_CSV.name} has an unsupported schema")
    return rows


def mean_and_std(rows, field):
    values = [float(row[field]) for row in rows]
    return statistics.fmean(values), statistics.pstdev(values)


def plot(rows):
    baseline_mean, baseline_std = mean_and_std(rows, "baseline_rss_mib")
    incremental_mean, incremental_std = mean_and_std(
        rows,
        "peak_incremental_working_memory_mib",
    )
    peak_mean, _ = mean_and_std(rows, "peak_rss_mib")
    memo_mean, _ = mean_and_std(rows, "peak_memo_entries")

    figure, axis = plt.subplots(figsize=(12, 6))
    x = np.array([0])
    axis.bar(
        x,
        [baseline_mean],
        width=0.55,
        color=IBG_ORANGE,
        label="Baseline controller RSS",
        yerr=[baseline_std] if len(rows) > 1 else None,
        capsize=4,
    )
    axis.bar(
        x,
        [incremental_mean],
        bottom=[baseline_mean],
        width=0.55,
        color=IBG_LIGHT_ORANGE,
        label="Peak incremental working memory",
        yerr=[incremental_std] if len(rows) > 1 else None,
        capsize=4,
    )
    for index in (1, 2, 3):
        axis.text(
            index,
            peak_mean * 0.04,
            "N/A",
            ha="center",
            va="bottom",
        )
    axis.set_xticks(
        [0, 1, 2, 3],
        ["IBG-Exact", "Baseline 1", "Baseline 2", "Baseline 3"],
    )
    axis.set_ylabel("Controller memory (MiB)")
    axis.set_title("Controller/solver memory footprint: IBG-Exact")
    axis.set_xlim(-0.55, 3.55)
    axis.set_ylim(0, max(peak_mean * 1.12, 1.0))
    axis.grid(axis="y", linestyle="--", alpha=0.35)
    axis.legend(loc="upper right")
    axis.text(
        0,
        peak_mean,
        f"Peak cache: {memo_mean:,.0f} entries",
        ha="center",
        va="bottom",
    )
    figure.tight_layout()
    figure.savefig(OUTPUT, dpi=300)
    plt.close(figure)
    return OUTPUT


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Plot stacked controller/solver memory from sibling IBG CSV."
    )
    parser.add_argument(
        "--traces",
        nargs="+",
        type=Path,
        help="completed --memory 1 JSONL traces to refresh solver_resource_IBG.csv",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    rows = write_rows(args.traces) if args.traces else read_rows()
    output = plot(rows)
    print(f"Wrote {IBG_CSV}")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
