import json
import csv
from types import SimpleNamespace

import scripts.run_experiment as launcher
from scripts.run_experiment import (
    csv_run_hash,
    export_legacy_csv,
    follow_logs,
    network_impairment_from_args,
    parse_args,
    remove_stale_stage_resources,
    render_event,
    run_experiment_series,
    run_identifier,
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


def test_datapath_flag_defaults_to_kernel_and_accepts_planned_dpdk_vpp():
    assert parse_args([]).datapath_mode == "kernel"
    assert parse_args(["--datapath", "dpdk-vpp"]).datapath_mode == "dpdk-vpp"
    assert parse_args(["--dpdk-preflight-only"]).dpdk_preflight_only is True


def test_csv_flag_is_disabled_by_default_and_accepts_zero_or_one():
    assert parse_args([]).csv == 0
    assert parse_args(["--csv", "0"]).csv == 0
    assert parse_args(["--csv", "1"]).csv == 1


def test_memory_flag_is_opt_in_and_accepts_zero_or_one():
    assert parse_args([]).memory == 0
    assert parse_args(["--memory", "0"]).memory == 0
    assert parse_args(["--memory", "1"]).memory == 1


def test_netem_is_opt_in_and_uses_explicit_delay_jitter_values():
    default = network_impairment_from_args(parse_args([]))
    enabled = network_impairment_from_args(
        parse_args(
            [
                "--netem",
                "1",
                "--netem-delay-ms",
                "12",
                "--netem-jitter-ms",
                "4",
            ]
        )
    )

    assert default.enabled is False
    assert default.delay_ms == 0
    assert default.jitter_ms == 0
    assert enabled.enabled is True
    assert enabled.delay_ms == 12
    assert enabled.jitter_ms == 4


def test_runs_flag_defaults_to_one_and_accepts_requested_count():
    assert parse_args([]).num_of_runs == 1
    assert parse_args(["--runs", "5"]).num_of_runs == 5


def test_diagnostic_flags_keep_the_default_and_allow_controlled_ab_mode():
    default = parse_args([])
    diagnostic = parse_args(
        [
            "--learning-signal-mode",
            "physical-only-diagnostic-v1",
            "--forwarder-cgroup-diagnostics",
            "--forwarding-path-diagnostics",
        ]
    )

    assert default.learning_signal_mode == "separated-v1"
    assert default.forwarder_cgroup_diagnostics is False
    assert default.forwarding_path_diagnostics is False
    assert diagnostic.learning_signal_mode == "physical-only-diagnostic-v1"
    assert diagnostic.forwarder_cgroup_diagnostics is True
    assert diagnostic.forwarding_path_diagnostics is True


def test_outcome_latency_mode_defaults_to_physical_and_can_restore_pair_cost():
    assert parse_args([]).outcome_latency_mode == "physical-only-v1"
    assert (
        parse_args(
            ["--outcome-latency-mode", "physical-plus-pair-v1"]
        ).outcome_latency_mode
        == "physical-plus-pair-v1"
    )


def test_multi_run_identifiers_are_unique_while_single_run_stays_compatible():
    timestamp = "20260715T190000Z"

    assert run_identifier(timestamp, 1, 1) == timestamp
    assert run_identifier(timestamp, 1, 5) == f"{timestamp}-run001"
    assert run_identifier(timestamp, 5, 5) == f"{timestamp}-run005"


def test_run_series_starts_each_requested_run_and_keeps_separate_traces(
    monkeypatch,
    tmp_path,
):
    args = parse_args(
        ["--runs", "3", "--skip-build", "--trace-dir", str(tmp_path)]
    )
    started = []
    traces = []

    monkeypatch.setattr(
        launcher,
        "start_experiment_job",
        lambda *arguments, **kwargs: started.append((arguments, kwargs)),
    )
    monkeypatch.setattr(
        launcher,
        "follow_logs",
        lambda context, trace_path, timeout: traces.append(trace_path),
    )
    monkeypatch.setattr(
        launcher,
        "datetime",
        SimpleNamespace(
            now=lambda timezone: SimpleNamespace(
                strftime=lambda format: "20260715T190000Z"
            )
        ),
    )

    result = run_experiment_series(args, "kind-ibg", {"kind": "test"})

    assert len(started) == 3
    assert result == traces
    assert [path.name for path in traces] == [
        "ibg-experiment-20260715T190000Z-run001.jsonl",
        "ibg-experiment-20260715T190000Z-run002.jsonl",
        "ibg-experiment-20260715T190000Z-run003.jsonl",
    ]


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


def test_export_csv_writes_active_and_reference_utility_views_for_current_trace(
    tmp_path,
):
    trace_path = tmp_path / "trace.jsonl"
    output_dir = tmp_path / "csv"
    metrics = {
        "elapsed_seconds": 0.3,
        "sla_violations": 1,
        "aggregate_utility_total": -2.5,
        "realized_utility_total": 30.0,
        "physical_utility_total": 30.0,
        "end_to_end_utility_total": 12.0,
        "jain_fairness": 0.9,
    }
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
                "metrics": metrics,
                "beliefs": {"1:1": [0.1, 0.2, 0.3, 0.4]},
            },
        },
        {"event": "run_completed", "iterations": 1},
    ]
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    paths = export_legacy_csv(trace_path, output_dir, "test-run")

    assert {path.name for path in paths} >= {
        "realized_utility.csv",
        "physical_processing_utility.csv",
        "realized_end_to_end_utility.csv",
    }
    with (output_dir / "realized_utility.csv").open(newline="") as source:
        assert list(csv.DictReader(source)) == [{"test-run": "30.0"}]
    with (output_dir / "realized_end_to_end_utility.csv").open(
        newline=""
    ) as source:
        assert list(csv.DictReader(source)) == [{"test-run": "12.0"}]


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


def test_export_legacy_csv_writes_logical_learning_footprint_when_recorded(
    tmp_path,
):
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
                "learning_signal": {"logical_payload_bytes": 1200},
            },
        },
        {
            "event": "iteration_completed",
            "summary": {
                "metrics": {
                    "elapsed_seconds": 0.2,
                    "sla_violations": 1,
                    "aggregate_utility_total": 2.0,
                    "realized_utility_total": 1.5,
                    "jain_fairness": 0.9,
                },
                "beliefs": {"1:1": [0.2, 0.3, 0.2, 0.3]},
                "learning_signal": {"logical_payload_bytes": 1300},
            },
        },
        {"event": "run_completed", "iterations": 2},
    ]
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    paths = export_legacy_csv(trace_path, output_dir, "test-run")

    assert paths[-1].name == "logical_learning_footprint.csv"
    with paths[-1].open(newline="") as source:
        assert list(csv.DictReader(source)) == [
            {"test-run": "1200"},
            {"test-run": "1300"},
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
        datapath_mode="kernel",
        environment_metadata={"kubernetes_server": "v1.35.0"},
    )

    container = applied["spec"]["template"]["spec"]["containers"][0]
    environment = {item["name"]: item["value"] for item in container["env"]}
    assert environment["NUM_STAGES"] == "4"
    assert environment["EXPECTED_REPLICAS"] == "6"
    assert environment["NUM_FLOWS"] == "5"
    assert environment["DATAPATH_MODE"] == "kernel"
    assert environment["LEARNING_SIGNAL_MODE"] == "separated-v1"
    assert environment["OUTCOME_LATENCY_MODE"] == "physical-only-v1"
    assert environment["FORWARDER_CGROUP_DIAGNOSTICS"] == "false"
    assert environment["FORWARDING_PATH_DIAGNOSTICS"] == "false"
    assert environment["SOLVER_RESOURCE_DIAGNOSTICS"] == "false"
    assert json.loads(environment["NETWORK_IMPAIRMENT"]) == {
        "schema": "netem_v1",
        "enabled": False,
        "delay_ms": 0.0,
        "jitter_ms": 0.0,
        "distribution": "normal",
        "interface": "eth0",
        "scope": "replica-pod-egress",
    }
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
