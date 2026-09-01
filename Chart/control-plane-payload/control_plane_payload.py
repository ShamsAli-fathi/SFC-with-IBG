"""Plot mean controller-boundary payload overhead from the latest IBG traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
RUNS_DIR = ROOT / "runs"
DEFAULT_CSV = SCRIPT_DIR / "control_plane_payload_IBG.csv"
DEFAULT_OUTPUT = SCRIPT_DIR / "control_plane_payload.png"
DEFAULT_TITLE = "Control-Plane Payload Overhead on Small-Scale Topology: IBG-Exact"
IBG_ORANGE = "#ff7f0e"
DISCOVERY_COLOR = "#1f77b4"
ROUTE_COMMAND_COLOR = "#7f7f7f"


def completed_iterations(path: Path) -> list[dict]:
    iterations = []
    completed = 0
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("event") == "iteration_completed":
                iterations.append(event)
            elif event.get("event") == "run_completed":
                completed += 1
    if completed != 1:
        return []
    return iterations


def matching_traces(last_n: int, flows: int, stages: int, replicas: int) -> list[tuple[Path, list[dict]]]:
    matches = []
    for path in sorted(RUNS_DIR.glob("ibg-experiment-*.jsonl")):
        iterations = completed_iterations(path)
        if not iterations:
            continue
        first = iterations[0]
        configuration = first.get("configuration", {})
        if (
            first.get("datapath_mode") == "kernel"
            and configuration.get("flows") == flows
            and configuration.get("stages") == stages
            and configuration.get("replicas_per_stage") == replicas
            and all("control_plane" in event.get("summary", {}) for event in iterations)
        ):
            matches.append((path, iterations))
    if len(matches) < last_n:
        raise ValueError(
            f"requested {last_n} completed matching traces, found {len(matches)} in {RUNS_DIR}"
        )
    return matches[-last_n:]


def capture_latest(csv_path: Path, last_n: int, flows: int, stages: int, replicas: int) -> pd.DataFrame:
    rows = []
    for run_index, (path, iterations) in enumerate(
        matching_traces(last_n, flows, stages, replicas), start=1
    ):
        for event in iterations:
            payload = event["summary"]["control_plane"]["payload_bytes"]
            rows.append(
                {
                    "run": run_index,
                    "trace": path.name,
                    "timeslot": event["iteration"],
                    "payload_bytes": payload["total"],
                    "kubernetes_discovery_rx_bytes": payload["kubernetes_discovery_rx"],
                    "route_command_tx_bytes": payload["route_command_tx"],
                    "selected_telemetry_rx_bytes": payload["selected_telemetry_rx"],
                }
            )
    frame = pd.DataFrame(rows)
    frame.to_csv(csv_path, index=False)
    return frame


def load_samples(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"run", "trace", "timeslot", "payload_bytes"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"payload CSV is missing columns: {', '.join(sorted(missing))}")
    if frame.empty:
        raise ValueError("payload CSV has no samples")
    return frame


def aggregate(frame: pd.DataFrame) -> pd.Series:
    components = [
        "kubernetes_discovery_rx_bytes",
        "route_command_tx_bytes",
        "selected_telemetry_rx_bytes",
    ]
    if any(component not in frame.columns for component in components):
        raise ValueError("payload CSV is missing component columns; refresh it from traces")
    per_run = frame.groupby("run")[components + ["payload_bytes"]].mean()
    return pd.Series(
        {
            "discovery": per_run["kubernetes_discovery_rx_bytes"].mean(),
            "route_command": per_run["route_command_tx_bytes"].mean(),
            "selected_telemetry": per_run["selected_telemetry_rx_bytes"].mean(),
        }
    )


def render(frame: pd.DataFrame, output: Path, title: str) -> Path:
    summary = aggregate(frame)
    figure, axis = plt.subplots(figsize=(12, 6))
    discovery = float(summary["discovery"]) / 1000.0
    route_command = float(summary["route_command"]) / 1000.0
    selected_telemetry = float(summary["selected_telemetry"]) / 1000.0
    total = discovery + route_command + selected_telemetry
    axis.bar([0], [discovery], color=DISCOVERY_COLOR, label="Kubernetes discovery")
    axis.bar([0], [route_command], bottom=[discovery], color=ROUTE_COMMAND_COLOR, label="Route command")
    axis.bar(
        [0],
        [selected_telemetry],
        bottom=[discovery + route_command],
        color=IBG_ORANGE,
        label="Selected-route execution telemetry",
    )
    for index in (1, 2, 3):
        axis.text(index, total * 0.04, "N/A", ha="center", va="bottom")
    axis.set_title(title)
    axis.set_ylabel("Mean controller payload per slot (kB)")
    axis.set_xticks([0, 1, 2, 3], ["IBG-Exact", "Baseline 1", "Baseline 2", "Baseline 3"])
    axis.grid(True, axis="y", alpha=0.4)
    axis.legend(loc="best")
    figure.tight_layout()
    figure.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-last-n", type=int, help="capture the latest N matching completed traces")
    parser.add_argument("--flows", type=int, default=15)
    parser.add_argument("--stages", type=int, default=3)
    parser.add_argument("--replicas", type=int, default=8)
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> Path:
    args = parse_args(argv)
    if args.refresh_last_n is not None:
        if args.refresh_last_n < 1:
            raise ValueError("--refresh-last-n must be positive")
        frame = capture_latest(args.input, args.refresh_last_n, args.flows, args.stages, args.replicas)
    else:
        frame = load_samples(args.input)
    return render(frame, args.output, args.title)


if __name__ == "__main__":
    main()
