"""Small host-side CSV table primitives for the retained Hybrid layouts."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping, Sequence


class HybridCsvError(ValueError):
    """Raised when a retained Hybrid CSV table is malformed or ambiguous."""


def read_csv_table(path: str | os.PathLike[str]) -> tuple[list[str], list[dict[str, str]]]:
    target = Path(path)
    if not target.exists() or target.stat().st_size == 0:
        return [], []
    with target.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            return [], []
        if any(not name for name in fieldnames) or len(set(fieldnames)) != len(
            fieldnames
        ):
            raise HybridCsvError(f"CSV has invalid or duplicate headers: {target}")
        rows = []
        for row_number, raw_row in enumerate(reader, start=2):
            if None in raw_row:
                raise HybridCsvError(
                    f"CSV row {row_number} has more values than headers: {target}"
                )
            rows.append(
                {
                    name: "" if raw_row.get(name) is None else str(raw_row[name])
                    for name in fieldnames
                }
            )
    return fieldnames, rows


def _write_csv_table(
    path: str | os.PathLike[str],
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as destination:
            temporary_name = destination.name
            writer = csv.DictWriter(destination, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def append_metric_value(
    path: str | os.PathLike[str], run_id: str, value: int | float
) -> None:
    """Append one value to a run column without changing the legacy layout."""

    if not isinstance(run_id, str) or not run_id or "\n" in run_id or "\r" in run_id:
        raise HybridCsvError("CSV run identifier must be a nonempty single line")
    fieldnames, rows = read_csv_table(path)
    if run_id not in fieldnames:
        fieldnames.append(run_id)
        if not rows:
            rows.append({name: "" for name in fieldnames})
        for row in rows:
            row.setdefault(run_id, "")
        target_index = 0
    else:
        target_index = next(
            (index for index, row in enumerate(rows) if row.get(run_id, "") == ""),
            len(rows),
        )
        if target_index == len(rows):
            rows.append({name: "" for name in fieldnames})
    rows[target_index][run_id] = value
    _write_csv_table(path, fieldnames, rows)


def append_belief_snapshot(
    path: str | os.PathLike[str], snapshot: Mapping[object, Sequence[float]]
) -> None:
    """Append one aligned replica-belief row in the retained wide layout."""

    serialized: dict[str, str] = {}
    for identity, belief in snapshot.items():
        name = str(identity)
        if not name or name in serialized:
            raise HybridCsvError("belief snapshot has an invalid replica identity")
        serialized[name] = json.dumps(list(belief))
    if not serialized:
        raise HybridCsvError("belief snapshot must not be empty")

    fieldnames, rows = read_csv_table(path)
    for name in serialized:
        if name not in fieldnames:
            fieldnames.append(name)
    for row in rows:
        for name in fieldnames:
            row.setdefault(name, "")
    rows.append(
        {name: serialized.get(name, "") for name in fieldnames}
    )
    _write_csv_table(path, fieldnames, rows)
