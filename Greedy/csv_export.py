"""Atomic host-side wide CSV export from one validated Greedy JSONL trace."""

from __future__ import annotations

import csv
import hashlib
import json
from math import isfinite
import os
from pathlib import Path
import tempfile
from typing import Mapping, Sequence

from .control_plane_footprint import GREEDY_CONTROL_PLANE_DATA_FIELDS
from .persistence import load_greedy_trace


DEFAULT_GREEDY_CSV_DIR = (
    Path(__file__).resolve().parents[1] / "figures" / "Greedy" / "v3"
)
GREEDY_CSV_FILENAMES = (
    "time.csv",
    "end_to_end_sla_violations.csv",
    "end_to_end_sla_excess_ms.csv",
    "aggregate_utility.csv",
    "jain_index.csv",
    "replica_results.csv",
)
GREEDY_CSV_POLICY_MARKER = ".greedy-csv-policy-contract.json"
GREEDY_FOOTPRINT_CSV_FIELDS = (
    ("discovery_time_ms.csv", "control_plane", "timing_ms", "discovery"),
    ("admission_time_ms.csv", "control_plane", "timing_ms", "admission"),
    ("feedback_time_ms.csv", "control_plane", "timing_ms", "feedback"),
    ("active_control_time_ms.csv", "control_plane", "timing_ms", "active"),
    ("data_plane_wait_ms.csv", "control_plane", "timing_ms", "data_plane_wait"),
    *((f"{name}_bytes.csv", "control_plane", "payload_bytes", name) for name in GREEDY_CONTROL_PLANE_DATA_FIELDS),
    ("belief_exchange_total_bytes.csv", "derived", "payload_bytes", "belief_exchange_total"),
    ("control_plane_payload_total_bytes.csv", "control_plane", "payload_bytes", "total"),
    *((f"{name}_messages.csv", "control_plane", "messages", name) for name in GREEDY_CONTROL_PLANE_DATA_FIELDS),
    ("belief_exchange_total_messages.csv", "derived", "messages", "belief_exchange_total"),
    ("control_plane_messages_total.csv", "control_plane", "messages", "total"),
    ("process_cpu_seconds.csv", "controller_resources", "", "process_cpu_seconds"),
    ("process_rss_bytes.csv", "controller_resources", "", "process_rss_bytes"),
    ("cpu_nr_throttled.csv", "controller_resources", "", "cgroup_cpu_nr_throttled"),
    ("cpu_throttled_usec.csv", "controller_resources", "", "cgroup_cpu_throttled_usec"),
)


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists() or path.stat().st_size == 0:
        return [], []
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        fields = list(reader.fieldnames or [])
        if not fields or any(not item for item in fields) or len(set(fields)) != len(fields):
            raise ValueError(f"Greedy CSV has invalid headers: {path}")
        rows = []
        for line, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"Greedy CSV row {line} exceeds its headers: {path}")
            rows.append({name: "" if row.get(name) is None else str(row[name]) for name in fields})
    return fields, rows


def _atomic_write(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as destination:
            temporary = destination.name
            writer = csv.DictWriter(destination, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def _ensure_csv_policy_contract(
    output_dir: Path,
    policy_contract_version: str,
    trace_contract_version: str,
) -> None:
    """Refuse retained columns from another or unversioned contract generation.

    The policy contract alone no longer separates generations: the Phase 8.3
    fairness correction changed the ``jain_index.csv`` series while leaving
    ``pure-greedy-budgeted-l2-v2`` in place.  Pin the trace contract as well so
    a predicted-fairness column can never be appended beside an end-to-end one.
    """

    if not isinstance(policy_contract_version, str) or not policy_contract_version:
        raise ValueError("Greedy CSV policy contract version is missing")
    if not isinstance(trace_contract_version, str) or not trace_contract_version:
        raise ValueError("Greedy CSV trace contract version is missing")
    expected = {
        "policy_contract_version": policy_contract_version,
        "trace_contract_version": trace_contract_version,
    }
    directory = Path(output_dir)
    marker = directory / GREEDY_CSV_POLICY_MARKER
    if marker.exists():
        try:
            document = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Greedy CSV policy marker is malformed") from error
        if not isinstance(document, Mapping):
            raise ValueError("Greedy CSV policy marker is malformed")
        if set(document) == {"policy_contract_version"}:
            raise ValueError(
                "Greedy CSV refuses predicted-fairness columns from a "
                "pre-Phase-8.3 marker"
            )
        if set(document) != set(expected):
            raise ValueError("Greedy CSV policy marker is malformed")
        if dict(document) != expected:
            raise ValueError(
                "Greedy CSV refuses mixed policy or trace contract columns"
            )
        return
    if directory.exists() and any(directory.rglob("*.csv")):
        raise ValueError("Greedy CSV refuses unversioned retained columns")
    directory.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="x", encoding="utf-8", dir=directory,
            prefix=f".{GREEDY_CSV_POLICY_MARKER}.", suffix=".tmp", delete=False,
        ) as destination:
            temporary = destination.name
            destination.write(
                json.dumps(expected, sort_keys=True, separators=(",", ":"))
            )
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, marker)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def _with_column(path: Path, run_id: str, values: Sequence[int | float]) -> tuple[list[str], list[dict[str, object]]]:
    fields, existing = _read(path)
    if run_id in fields:
        raise ValueError(f"Greedy CSV run identifier already exists in {path}: {run_id}")
    fields = [*fields, run_id]
    count = max(len(existing), len(values))
    rows = []
    for index in range(count):
        row: dict[str, object] = dict(existing[index]) if index < len(existing) else {name: "" for name in fields[:-1]}
        row[run_id] = values[index] if index < len(values) else ""
        rows.append(row)
    return fields, rows


def _run_column(started: Mapping[str, object]) -> str:
    value = f"{started['run_id']}|{started['root_seed']}|{json.dumps(started['configuration'], sort_keys=True)}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:6]


def export_greedy_csv(
    trace_path: Path,
    output_dir: Path = DEFAULT_GREEDY_CSV_DIR,
) -> tuple[Path, ...]:
    events = load_greedy_trace(Path(trace_path))
    started = events[0]
    iterations = events[1:-1]
    if started.get("csv_enabled") is not True:
        raise ValueError("Greedy CSV export requires a trace recorded with --csv 1")
    _ensure_csv_policy_contract(
        Path(output_dir),
        started.get("policy_contract_version"),
        started.get("trace_contract_version"),
    )
    run_id = _run_column(started)
    metrics = []
    for event in iterations:
        item = event["metrics"]
        phases = event["phase_timings_seconds"]
        row = (
            phases["admission_placement_seconds"]
            + phases["feedback_validation_seconds"],
            item["end_to_end_sla_violations"],
            item["end_to_end_sla_excess_ms"],
            item["raw_end_to_end_reference_utility"],
            item["jain_fairness"],
        )
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)) for value in row):
            raise ValueError("Greedy CSV trace contains an invalid metric")
        metrics.append(row)
    metric_paths = tuple(Path(output_dir) / name for name in GREEDY_CSV_FILENAMES[:5])
    prepared: list[tuple[Path, list[str], list[dict[str, object]]]] = []
    for index, path in enumerate(metric_paths):
        fields, rows = _with_column(path, run_id, [row[index] for row in metrics])
        prepared.append((path, fields, rows))
    footprint_dir = Path(output_dir) / "footprint"
    footprint_paths = []
    for filename, root, section, field in GREEDY_FOOTPRINT_CSV_FIELDS:
        path = footprint_dir / filename
        if root == "derived":
            values = [
                event["control_plane"][section]["belief_tx"]
                + event["control_plane"][section]["belief_rx"]
                for event in iterations
            ]
        else:
            values = [
                event[root][field] if not section else event[root][section][field]
                for event in iterations
            ]
        fields, rows = _with_column(path, run_id, values)
        prepared.append((path, fields, rows))
        footprint_paths.append(path)
    belief_path = Path(output_dir) / GREEDY_CSV_FILENAMES[5]
    belief_fields, belief_rows = _read(belief_path)
    snapshots = [iterations[0]["beliefs_before"], *(item["beliefs_after"] for item in iterations)]
    identities = sorted(snapshots[0], key=lambda item: tuple(int(value) for value in item.split(":")))
    if any(set(snapshot) != set(identities) for snapshot in snapshots):
        raise ValueError("Greedy CSV belief identities change within one run")
    for identity in identities:
        if identity not in belief_fields:
            belief_fields.append(identity)
    for row in belief_rows:
        for identity in belief_fields:
            row.setdefault(identity, "")
    for snapshot in snapshots:
        belief_rows.append(
            {
                identity: json.dumps(snapshot[identity], separators=(",", ":"))
                if identity in snapshot else ""
                for identity in belief_fields
            }
        )
    prepared.append((belief_path, belief_fields, belief_rows))
    # Every input and duplicate check completes before the first replacement.
    for path, fields, rows in prepared:
        _atomic_write(path, fields, rows)
    return (*metric_paths, belief_path, *footprint_paths)
