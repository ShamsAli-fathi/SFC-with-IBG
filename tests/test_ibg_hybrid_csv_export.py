import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from IBG_Hybrid.csv_storage import HybridCsvError
from IBG_Hybrid.control_plane_footprint import HYBRID_CONTROL_PLANE_DATA_SCHEMA
from IBG_Hybrid.header import create_belief_csv
from IBG_Hybrid.report import (
    csv_gen_SLA,
    csv_gen_jain,
    csv_gen_time,
    csv_gen_util,
)
from scripts import run_hybrid_kernel_phase4 as launcher


def _rows(path):
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def test_metric_helpers_preserve_wide_run_columns_and_unequal_lengths(tmp_path):
    functions = (
        (csv_gen_SLA, "end_to_end_sla_violations.csv", (1, 2, 3)),
        (csv_gen_util, "aggregate_utility.csv", (12.5, 13.5, 14.5)),
        (csv_gen_jain, "jain_index.csv", (0.8, 0.9, 1.0)),
        (csv_gen_time, "time.csv", (0.1, 0.2, 0.3)),
    )
    for function, filename, values in functions:
        path = tmp_path / filename
        path.touch()
        function(values[0], "run-a", path)
        function(values[1], "run-a", path)
        function(values[2], "run-b", path)
        assert _rows(path) == [
            {"run-a": str(float(values[0])) if function is not csv_gen_SLA else "1", "run-b": str(float(values[2])) if function is not csv_gen_SLA else "3"},
            {"run-a": str(float(values[1])) if function is not csv_gen_SLA else "2", "run-b": ""},
        ]


def test_metric_helpers_reject_invalid_semantics_without_writing(tmp_path):
    invalid = (
        (csv_gen_SLA, -1),
        (csv_gen_SLA, 1.5),
        (csv_gen_util, float("nan")),
        (csv_gen_jain, 1.1),
        (csv_gen_time, -0.1),
    )
    for index, (function, value) in enumerate(invalid):
        path = tmp_path / f"invalid-{index}.csv"
        with pytest.raises(HybridCsvError):
            function(value, "run-a", path)
        assert not path.exists()


def test_belief_helper_aligns_reordered_and_added_replica_columns(tmp_path):
    path = tmp_path / "replica_results.csv"
    create_belief_csv(
        {
            (1, 2): SimpleNamespace(belief=[0.4, 0.3, 0.2, 0.1]),
            (1, 1): SimpleNamespace(belief=[0.1, 0.2, 0.3, 0.4]),
        },
        path,
    )
    create_belief_csv(
        {
            (1, 2): [0.3, 0.3, 0.2, 0.2],
            (1, 1): [0.2, 0.2, 0.3, 0.3],
        },
        path,
    )
    create_belief_csv({(2, 1): [0.25] * 4}, path)

    rows = _rows(path)
    assert list(rows[0]) == ["(1, 1)", "(1, 2)", "(2, 1)"]
    assert json.loads(rows[0]["(1, 1)"]) == [0.1, 0.2, 0.3, 0.4]
    assert json.loads(rows[1]["(1, 1)"]) == [0.2, 0.2, 0.3, 0.3]
    assert rows[0]["(2, 1)"] == ""
    assert json.loads(rows[2]["(2, 1)"]) == [0.25] * 4


def _trace_events():
    beliefs0 = {"1:2": [0.25] * 4, "1:1": [0.25] * 4}
    beliefs1 = {"1:1": [0.1, 0.2, 0.3, 0.4], "1:2": [0.4, 0.3, 0.2, 0.1]}
    beliefs2 = {"1:1": [0.2, 0.2, 0.3, 0.3], "1:2": [0.3, 0.3, 0.2, 0.2]}
    return [
        {
            "event": "run_started",
            "trace_contract_version": launcher.HYBRID_TRACE_CONTRACT_VERSION,
            "configuration": {
                "num_flows": 2,
                "num_stages": 3,
                "num_replicas": 2,
                "stage_budget": 2,
            },
            "experiment_seed": 12345,
            "series_id": "20260815T150000.000000Z",
            "series_run_index": 1,
        },
        {
            "event": "iteration_completed",
            "trace_contract_version": launcher.HYBRID_TRACE_CONTRACT_VERSION,
            "iteration": 1,
            "beliefs_before": beliefs0,
            "beliefs_after": beliefs1,
            "metrics": {
                "elapsed_seconds": 0.2,
                "end_to_end_sla_violations": 1,
                "end_to_end_sla_excess_ms": 12.25,
                "aggregate_expected_utility": 999.0,
                "physical_realized_utility": 888.0,
                "raw_end_to_end_reference_utility": 77.5,
                "jain_fairness": 0.9,
            },
        },
        {
            "event": "iteration_completed",
            "trace_contract_version": launcher.HYBRID_TRACE_CONTRACT_VERSION,
            "iteration": 2,
            "beliefs_before": beliefs1,
            "beliefs_after": beliefs2,
            "metrics": {
                "elapsed_seconds": 0.3,
                "end_to_end_sla_violations": 0,
                "end_to_end_sla_excess_ms": 0.0,
                "aggregate_expected_utility": 998.0,
                "physical_realized_utility": 887.0,
                "raw_end_to_end_reference_utility": 78.5,
                "jain_fairness": 0.95,
            },
        },
        {
            "event": "run_completed",
            "trace_contract_version": launcher.HYBRID_TRACE_CONTRACT_VERSION,
            "iterations": 2,
        },
    ]


def _footprint(value):
    payload = {
        "kubernetes_discovery_tx": 0,
        "kubernetes_discovery_rx": value,
        "route_command_tx": value + 10,
        "selected_telemetry_rx": value + 20,
        "belief_tx": 0,
        "belief_rx": 0,
    }
    messages = {
        "kubernetes_discovery_tx": 1,
        "kubernetes_discovery_rx": 1,
        "route_command_tx": 1,
        "selected_telemetry_rx": 1,
        "belief_tx": 0,
        "belief_rx": 0,
    }
    return {
        "schema": HYBRID_CONTROL_PLANE_DATA_SCHEMA,
        "timing_ms": {
            "discovery": value / 100,
            "admission": value / 10,
            "feedback": value / 20,
            "active": value / 10 + value / 20,
            "data_plane_wait": value / 5,
        },
        "payload_bytes": {**payload, "total": sum(payload.values())},
        "messages": {**messages, "total": sum(messages.values())},
    }


def test_export_hybrid_csv_writes_only_requested_legacy_reports(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in _trace_events()),
        encoding="utf-8",
    )
    output_dir = tmp_path / "figures" / "IBG_hybrid"
    assert not output_dir.exists()

    paths = launcher.export_hybrid_csv(trace_path, output_dir)

    assert output_dir.is_dir()
    assert [path.name for path in paths] == list(launcher.HYBRID_CSV_FILENAMES)
    assert not (output_dir / "results.csv").exists()
    utility_rows = _rows(output_dir / "aggregate_utility.csv")
    run_id = next(iter(utility_rows[0]))
    assert [row[run_id] for row in utility_rows] == ["77.5", "78.5"]
    assert [
        row[run_id]
        for row in _rows(output_dir / "end_to_end_sla_violations.csv")
    ] == [
        "1",
        "0",
    ]
    assert not (output_dir / "sla_violations.csv").exists()
    assert [
        row[run_id]
        for row in _rows(output_dir / "end_to_end_sla_excess_ms.csv")
    ] == ["12.25", "0.0"]
    belief_rows = _rows(output_dir / "replica_results.csv")
    assert len(belief_rows) == 3
    assert list(belief_rows[0]) == ["(1, 1)", "(1, 2)"]
    assert json.loads(belief_rows[0]["(1, 1)"]) == [0.25] * 4
    assert json.loads(belief_rows[-1]["(1, 2)"]) == [0.3, 0.3, 0.2, 0.2]

    with pytest.raises(ValueError, match="already exists"):
        launcher.export_hybrid_csv(trace_path, output_dir)


def test_export_rejects_legacy_physical_only_sla_field(tmp_path):
    events = _trace_events()
    for event in events[1:3]:
        metrics = event["metrics"]
        metrics["physical_only_sla_violations"] = metrics.pop(
            "end_to_end_sla_violations"
        )
    trace_path = tmp_path / "legacy-trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    output_dir = tmp_path / "figures" / "IBG_hybrid"

    with pytest.raises(ValueError, match="lacks required metrics"):
        launcher.export_hybrid_csv(trace_path, output_dir)
    assert not output_dir.exists()


def test_export_rejects_invalid_sla_excess_before_writing(tmp_path):
    events = _trace_events()
    events[1]["metrics"]["end_to_end_sla_excess_ms"] = -0.1
    trace_path = tmp_path / "invalid-excess.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    output_dir = tmp_path / "figures" / "IBG_hybrid"

    with pytest.raises(ValueError, match="invalid metric value"):
        launcher.export_hybrid_csv(trace_path, output_dir)
    assert not output_dir.exists()


def test_export_rejects_historical_v2_trace_without_relabelling(tmp_path):
    events = _trace_events()
    for event in events:
        event["trace_contract_version"] = "ibg-hybrid-experiment-jsonl-v2"
    trace_path = tmp_path / "v2-trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    output_dir = tmp_path / "figures" / "IBG_hybrid"

    with pytest.raises(ValueError, match="active v3"):
        launcher.export_hybrid_csv(trace_path, output_dir)
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "contents",
    ("abc,abc\n1,2\n", "abc\n1,2\n"),
)
def test_export_rejects_malformed_sla_excess_csv_before_other_writes(
    tmp_path,
    contents,
):
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in _trace_events()),
        encoding="utf-8",
    )
    output_dir = tmp_path / "figures" / "IBG_hybrid"
    output_dir.mkdir(parents=True)
    (output_dir / "end_to_end_sla_excess_ms.csv").write_text(
        contents,
        encoding="utf-8",
    )

    with pytest.raises(HybridCsvError):
        launcher.export_hybrid_csv(trace_path, output_dir)
    assert not (output_dir / "time.csv").exists()


def test_production_cli_csv_is_explicit_and_defaults_off():
    assert launcher.HYBRID_CSV_OUTPUT_DIR == (
        launcher.ROOT / "figures" / "IBG_hybrid"
    )
    base = [
        "run",
        "--flow", "2",
        "--stage", "3",
        "--replica", "2",
        "--runs", "1",
        "--max-iterations", "2",
    ]
    assert launcher.parse_args(base).csv == 0
    assert launcher.parse_args([*base, "--csv", "1"]).csv == 1
    with pytest.raises(SystemExit):
        launcher.parse_args([*base, "--csv", "2"])


def test_footprint_export_creates_wall_time_and_data_csvs_per_category(tmp_path):
    events = _trace_events()
    events[1]["control_plane"] = _footprint(100)
    events[2]["control_plane"] = _footprint(200)
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    output_dir = tmp_path / "figures" / "IBG_hybrid"

    paths = launcher.export_hybrid_csv(trace_path, output_dir)

    footprint_dir = output_dir / "footprint"
    expected_names = [item[0] for item in launcher.HYBRID_FOOTPRINT_CSV_FIELDS]
    assert footprint_dir.is_dir()
    assert [path.name for path in paths[6:]] == expected_names
    assert sorted(path.name for path in footprint_dir.iterdir()) == sorted(expected_names)
    assert not any("cpu" in name for name in expected_names)
    admission_rows = _rows(footprint_dir / "admission_time_ms.csv")
    run_id = next(iter(admission_rows[0]))
    assert [row[run_id] for row in admission_rows] == ["10.0", "20.0"]
    wait_rows = _rows(footprint_dir / "data_plane_wait_ms.csv")
    assert [row[run_id] for row in wait_rows] == ["20.0", "40.0"]
    total_rows = _rows(footprint_dir / "control_plane_payload_total_bytes.csv")
    assert [row[run_id] for row in total_rows] == ["330", "630"]
    belief_rows = _rows(footprint_dir / "belief_exchange_total_bytes.csv")
    assert [row[run_id] for row in belief_rows] == ["0", "0"]
    message_rows = _rows(footprint_dir / "control_plane_messages_total.csv")
    assert [row[run_id] for row in message_rows] == ["4", "4"]
    assert len(paths) == 6 + len(expected_names)


def test_export_leaves_historical_sla_violations_csv_untouched(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in _trace_events()),
        encoding="utf-8",
    )
    output_dir = tmp_path / "figures" / "IBG_hybrid"
    output_dir.mkdir(parents=True)
    historical_path = output_dir / "sla_violations.csv"
    historical_contents = "legacy\n4\n"
    historical_path.write_text(historical_contents, encoding="utf-8")

    launcher.export_hybrid_csv(trace_path, output_dir)

    assert historical_path.read_text(encoding="utf-8") == historical_contents


def test_sla_excess_csv_preserves_wide_layout_and_blank_padding(tmp_path):
    first_events = _trace_events()
    second_events = _trace_events()
    second_events[0]["experiment_seed"] = 54321
    second_events[0]["series_run_index"] = 2
    second_events.pop(2)
    second_events[-1]["iterations"] = 1
    first_trace = tmp_path / "first.jsonl"
    second_trace = tmp_path / "second.jsonl"
    first_trace.write_text(
        "".join(json.dumps(event) + "\n" for event in first_events),
        encoding="utf-8",
    )
    second_trace.write_text(
        "".join(json.dumps(event) + "\n" for event in second_events),
        encoding="utf-8",
    )
    output_dir = tmp_path / "figures" / "IBG_hybrid"

    launcher.export_hybrid_csv(first_trace, output_dir)
    launcher.export_hybrid_csv(second_trace, output_dir)

    rows = _rows(output_dir / "end_to_end_sla_excess_ms.csv")
    assert len(rows) == 2
    first_run, second_run = rows[0]
    assert rows == [
        {first_run: "12.25", second_run: "12.25"},
        {first_run: "0.0", second_run: ""},
    ]


def test_sla_excess_csv_rejects_duplicate_run_hash_before_writing(tmp_path):
    events = _trace_events()
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    output_dir = tmp_path / "figures" / "IBG_hybrid"
    output_dir.mkdir(parents=True)
    run_id = launcher._hybrid_csv_run_hash(events[0])
    (output_dir / "end_to_end_sla_excess_ms.csv").write_text(
        f"{run_id}\n12.25\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="already exists"):
        launcher.export_hybrid_csv(trace_path, output_dir)
    assert not (output_dir / "time.csv").exists()


def test_footprint_export_rejects_mixed_slots_before_writing(tmp_path):
    events = _trace_events()
    events[1]["control_plane"] = _footprint(100)
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    output_dir = tmp_path / "figures" / "IBG_hybrid"

    with pytest.raises(ValueError, match="mixes enabled and disabled"):
        launcher.export_hybrid_csv(trace_path, output_dir)
    assert not output_dir.exists()


def test_footprint_export_rejects_duplicate_run_hash_before_legacy_writes(tmp_path):
    events = _trace_events()
    for index, event in enumerate(events[1:3], start=1):
        event["control_plane"] = _footprint(index * 100)
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    output_dir = tmp_path / "figures" / "IBG_hybrid"
    run_id = launcher._hybrid_csv_run_hash(events[0])
    footprint_path = output_dir / "footprint" / "belief_tx_bytes.csv"
    footprint_path.parent.mkdir(parents=True)
    footprint_path.write_text(f"{run_id}\n0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="already exists"):
        launcher.export_hybrid_csv(trace_path, output_dir)
    assert not (output_dir / "time.csv").exists()
