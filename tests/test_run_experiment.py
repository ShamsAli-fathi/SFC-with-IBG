import json
import csv
from types import SimpleNamespace

import scripts.run_experiment as launcher
from scripts.run_experiment import (
    csv_run_hash,
    export_legacy_csv,
    follow_logs,
    parse_args,
    remove_stale_stage_resources,
    render_event,
    set_env,
    start_experiment_job,
)


def test_csv_run_hash_is_six_hex_characters_and_provenance_stable():
    first = csv_run_hash("20260715T140501Z", 2050, 12, 3, 5)

    assert len(first) == 6
    assert set(first) <= set("0123456789abcdef")
    assert first == csv_run_hash("20260715T140501Z", 2050, 12, 3, 5)
    assert first != csv_run_hash("20260715T140501Z", 2051, 12, 3, 5)


def test_set_env_replaces_field_refs_and_adds_new_values():
    container = {
        "env": [
            {
                "name": "POD_NAMESPACE",
                "valueFrom": {"fieldRef": {"fieldPath": "metadata.namespace"}},
            }
        ]
    }

    set_env(container, "POD_NAMESPACE", "ibg-testbed")
    set_env(container, "MAX_ITERATIONS", 50)

    assert container["env"] == [
        {"name": "POD_NAMESPACE", "value": "ibg-testbed"},
        {"name": "MAX_ITERATIONS", "value": "50"},
    ]


def test_dimension_flags_accept_singular_and_plural_names():
    singular = parse_args(["--flow", "4", "--stage", "2", "--replica", "6"])
    plural = parse_args(["--flows", "5", "--stages", "4", "--replicas", "2"])

    assert (
        singular.num_of_flows,
        singular.num_of_stages,
        singular.num_of_replicas,
    ) == (4, 2, 6)
    assert (
        plural.num_of_flows,
        plural.num_of_stages,
        plural.num_of_replicas,
    ) == (5, 4, 2)


def test_csv_flag_is_disabled_by_default_and_accepts_zero_or_one():
    assert parse_args([]).csv == 0
    assert parse_args(["--csv", "0"]).csv == 0
    assert parse_args(["--csv", "1"]).csv == 1


def test_csv_output_defaults_to_the_ignored_project_figures_directory():
    assert launcher.CSV_OUTPUT_DIR == launcher.ROOT / "figures"


def test_export_legacy_csv_writes_all_reports(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    output_dir = tmp_path / "csv"
    events = [
        {
            "event": "run_started",
            "initial_replicas": [
                {"stage": 1, "replica_id": 1, "belief": [0.25] * 4},
                {"stage": 1, "replica_id": 2, "belief": [0.25] * 4},
            ],
        },
        {
            "event": "iteration_completed",
            "summary": {
                "metrics": {
                    "elapsed_seconds": 0.3,
                    "sla_violations": 1,
                    "aggregate_utility_total": -2.5,
                    "realized_utility_total": -3.5,
                    "jain_fairness": 0.9,
                },
                "beliefs": {
                    "1:1": [0.1, 0.2, 0.3, 0.4],
                    "1:2": [0.4, 0.3, 0.2, 0.1],
                },
            },
        },
        {
            "event": "run_completed",
            "iterations": 1,
            "reached_equilibrium": True,
        },
    ]
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    paths = export_legacy_csv(trace_path, output_dir, "test-run")

    assert {path.name for path in paths} == {
        "time.csv",
        "sla_violations.csv",
        "aggregate_utility.csv",
        "realized_end_to_end_utility.csv",
        "jain_index.csv",
        "replica_results.csv",
    }
    with (output_dir / "aggregate_utility.csv").open(newline="") as source:
        assert list(csv.DictReader(source)) == [{"test-run": "-2.5"}]
    with (output_dir / "realized_end_to_end_utility.csv").open(
        newline=""
    ) as source:
        assert list(csv.DictReader(source)) == [{"test-run": "-3.5"}]
    with (output_dir / "replica_results.csv").open(newline="") as source:
        beliefs = list(csv.DictReader(source))
    assert len(beliefs) == 2
    assert json.loads(beliefs[0]["(1, 1)"]) == [0.25] * 4
    assert json.loads(beliefs[1]["(1, 2)"]) == [0.4, 0.3, 0.2, 0.1]


def test_export_legacy_csv_appends_a_new_metric_column(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    output_dir = tmp_path / "csv"
    events = [
        {
            "event": "run_started",
            "initial_replicas": [
                {"stage": 1, "replica_id": 1, "belief": [0.25] * 4},
            ],
        },
        {
            "event": "iteration_completed",
            "summary": {
                "metrics": {
                    "elapsed_seconds": 0.1,
                    "sla_violations": 0,
                    "aggregate_utility_total": 1.0,
                    "realized_utility_total": 0.5,
                    "jain_fairness": 1.0,
                },
                "beliefs": {"1:1": [0.1, 0.2, 0.3, 0.4]},
            },
        },
        {"event": "run_completed", "iterations": 1},
    ]
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    export_legacy_csv(trace_path, output_dir, "first")
    export_legacy_csv(trace_path, output_dir, "second")

    with (output_dir / "time.csv").open(newline="") as source:
        assert list(csv.DictReader(source)) == [
            {"first": "0.1", "second": "0.1"}
        ]


def test_experiment_job_receives_requested_dimensions(monkeypatch):
    job = {
        "metadata": {"name": "ibg-controller"},
        "spec": {
            "activeDeadlineSeconds": 180,
            "template": {"spec": {"containers": [{"env": []}]}},
        },
    }
    applied = {}

    def fake_run(command, **kwargs):
        if "create" in command:
            return SimpleNamespace(stdout=json.dumps(job))
        if command[-1] == "-":
            applied.update(json.loads(kwargs["input_text"]))
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(launcher, "run", fake_run)

    start_experiment_job(
        "kind-ibg",
        2050,
        50,
        600,
        num_of_stages=4,
        num_of_replicas=6,
        num_of_flows=5,
        environment_metadata={"kubernetes_server": "v1.35.0"},
    )

    container = applied["spec"]["template"]["spec"]["containers"][0]
    environment = {item["name"]: item["value"] for item in container["env"]}
    assert environment["NUM_STAGES"] == "4"
    assert environment["EXPECTED_REPLICAS"] == "6"
    assert environment["NUM_FLOWS"] == "5"
    assert environment["DATAPATH_MODE"] == "kernel"
    assert environment["RUNTIME_IMAGE"] == launcher.IMAGE
    assert json.loads(environment["EXPERIMENT_ENVIRONMENT"]) == {
        "kubernetes_server": "v1.35.0"
    }


def test_stale_stage_cleanup_removes_only_stages_above_request(monkeypatch):
    calls = []
    items = [
        {"kind": "StatefulSet", "metadata": {"name": "stage-1"}},
        {"kind": "StatefulSet", "metadata": {"name": "stage-4"}},
        {"kind": "Service", "metadata": {"name": "stage-4"}},
        {"kind": "Service", "metadata": {"name": "flow-generator"}},
    ]

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=json.dumps({"items": items}))

    monkeypatch.setattr(launcher, "run", fake_run)

    remove_stale_stage_resources("kind-ibg", 3)

    delete = next(command for command in calls if "delete" in command)
    assert "statefulset/stage-4" in delete
    assert "service/stage-4" in delete
    assert "statefulset/stage-1" not in delete


def test_render_event_prints_iteration_details(capsys):
    render_event(
        {
            "event": "iteration_completed",
            "datapath_mode": "kernel",
            "iteration": 2,
            "slot_id": 2,
            "max_belief_delta": 0.02,
            "summary": {
                "flow_order_by_stage": {"1": [2, 1, 3]},
                "placements": [
                    {"stage": 1, "flow_id": 1, "replica_id": 2},
                ],
                "observations": [
                    {
                        "stage": 1,
                        "flow_id": 1,
                        "replica_id": 2,
                        "congestion": 1,
                        "signal": 2,
                        "measured_latency_ms": 45.2,
                    }
                ],
                "metrics": {
                    "aggregate_utility_total": -1.25,
                    "sla_violations": 0,
                    "jain_fairness": 0.95,
                    "elapsed_seconds": 0.3,
                    "equilibrium": 1,
                },
            },
        }
    )

    output = capsys.readouterr().out
    assert "Iteration 2" in output
    assert "f1->r2" in output
    assert "max belief delta=0.020" in output
    assert "equilibrium=yes" in output


def test_follow_logs_polls_completed_pod_and_writes_jsonl(monkeypatch, tmp_path):
    event = {"event": "test_event", "value": 7}

    def fake_run(command, **kwargs):
        if "logs" in command:
            return SimpleNamespace(
                returncode=0,
                stdout=f"IBG_EVENT={json.dumps(event)}\n",
                stderr="",
            )
        if "pod/ibg-experiment-test" in command:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "status": {
                            "containerStatuses": [
                                {
                                    "state": {
                                        "terminated": {"exitCode": 0}
                                    }
                                }
                            ]
                        }
                    }
                ),
                stderr="",
            )
        if "job/ibg-experiment" in command and "wait" in command:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "job" in command and "ibg-experiment" in command:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"status": {"succeeded": 1}}),
                stderr="",
            )
        raise AssertionError(command)

    monkeypatch.setattr(
        launcher,
        "wait_for_controller_pod",
        lambda context, timeout: "ibg-experiment-test",
    )
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    trace_path = tmp_path / "trace.jsonl"

    follow_logs("kind-ibg", trace_path, timeout=1)

    assert json.loads(trace_path.read_text()) == event
