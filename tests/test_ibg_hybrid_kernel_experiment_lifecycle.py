import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from IBG_Hybrid import kernel_controller_cli
from IBG_Hybrid import kernel_phase4_validation as lifecycle
from IBG_Hybrid.console_output import format_hybrid_replica_beliefs
from IBG_Hybrid.contracts import ReplicaChoice
from IBG_Hybrid.control_plane_footprint import HYBRID_CONTROL_PLANE_DATA_SCHEMA
from scripts import run_hybrid_kernel_phase4 as host_runner


ROOT = Path(__file__).resolve().parents[1]


def test_replica_belief_snapshot_matches_exact_table_style_without_hidden_state():
    text = format_hybrid_replica_beliefs(
        "Initial replica state",
        {
            ReplicaChoice(2, 1): (0.1, 0.2, 0.3, 0.4),
            ReplicaChoice(1, 2): (0.25, 0.25, 0.25, 0.25),
            ReplicaChoice(1, 1): (1.0, 0.0, 0.0, 0.0),
        },
    )
    assert text == (
        "Initial replica state\n"
        "Stage  Replica  Belief\n"
        "    1        1  [1.000, 0.000, 0.000, 0.000]\n"
        "    1        2  [0.250, 0.250, 0.250, 0.250]\n"
        "    2        1  [0.100, 0.200, 0.300, 0.400]"
    )
    assert "State  Capacity" not in text
    assert "hidden" not in text.lower()


def _outcome(slot_id, *, beliefs_before, beliefs_after, equilibrium):
    return SimpleNamespace(
        slot=SimpleNamespace(
            slot_id=slot_id,
            beliefs_before=beliefs_before,
            beliefs_after=beliefs_after,
            metrics=SimpleNamespace(equilibrium=equilibrium),
        )
    )


def test_production_loop_prints_before_next_slot_and_stops_at_equilibrium(
    monkeypatch,
):
    events = []
    outcomes = [
        _outcome(
            7,
            beliefs_before={"replica": (0.25,) * 4},
            beliefs_after={"replica": (0.30, 0.25, 0.25, 0.20)},
            equilibrium=False,
        ),
        _outcome(
            8,
            beliefs_before={"replica": (0.30, 0.25, 0.25, 0.20)},
            beliefs_after={"replica": (0.31, 0.25, 0.24, 0.20)},
            equilibrium=True,
        ),
        _outcome(
            9,
            beliefs_before={"replica": (0.31, 0.25, 0.24, 0.20)},
            beliefs_after={"replica": (0.31, 0.25, 0.24, 0.20)},
            equilibrium=True,
        ),
    ]

    class Controller:
        requests = 0

        def run_slot(self, slot_id):
            if slot_id == 8:
                assert events[-1] == "printed-1-7"
            self.requests += 1
            events.append(f"run-{slot_id}")
            return outcomes.pop(0)

    monkeypatch.setattr(
        lifecycle,
        "_slot_evidence",
        lambda **kwargs: {"slot_id": kwargs["outcome"].slot.slot_id},
    )
    controller = Controller()
    result = lifecycle.run_kernel_experiment(
        controller,
        object(),
        first_slot=7,
        max_iterations=100,
        on_slot_completed=lambda iteration, slot, item: events.append(
            f"printed-{iteration}-{slot.slot_id}"
        ),
    )

    assert result.reached_equilibrium is True
    assert result.iterations_completed == 2
    assert (result.first_slot, result.last_slot) == (7, 8)
    assert controller.requests == result.iterations_completed
    assert events == ["run-7", "printed-1-7", "run-8", "printed-2-8"]


def test_production_loop_reaches_limit_and_rejects_belief_discontinuity(
    monkeypatch,
):
    monkeypatch.setattr(
        lifecycle,
        "_slot_evidence",
        lambda **kwargs: {"slot_id": kwargs["outcome"].slot.slot_id},
    )
    belief_states = [
        {"replica": (0.25,) * 4},
        {"replica": (0.30, 0.25, 0.25, 0.20)},
        {"replica": (0.31, 0.25, 0.24, 0.20)},
        {"replica": (0.32, 0.24, 0.24, 0.20)},
    ]

    class Controller:
        def __init__(self, *, drift=False):
            self.calls = 0
            self.drift = drift

        def run_slot(self, slot_id):
            index = self.calls
            self.calls += 1
            before = belief_states[index]
            if self.drift and index == 1:
                before = {"replica": (1.0, 0.0, 0.0, 0.0)}
            return _outcome(
                slot_id,
                beliefs_before=before,
                beliefs_after=belief_states[index + 1],
                equilibrium=False,
            )

    controller = Controller()
    result = lifecycle.run_kernel_experiment(
        controller,
        object(),
        first_slot=1,
        max_iterations=3,
    )
    assert result.reached_equilibrium is False
    assert result.iterations_completed == 3
    assert controller.calls == 3

    with pytest.raises(RuntimeError, match="retain beliefs"):
        lifecycle.run_kernel_experiment(
            Controller(drift=True),
            object(),
            first_slot=1,
            max_iterations=3,
        )


def test_production_parity_replay_defaults_off_and_can_be_enabled(monkeypatch):
    calls = []

    def fake_slot_evidence(**kwargs):
        enabled = kwargs["parity_replay_enabled"]
        calls.append(enabled)
        evidence = {
            "slot_id": kwargs["outcome"].slot.slot_id,
            "pure_kernel_replay_performed": enabled,
        }
        if enabled:
            evidence["pure_kernel_replay_parity"] = True
        return evidence

    monkeypatch.setattr(lifecycle, "_slot_evidence", fake_slot_evidence)

    class Controller:
        def run_slot(self, slot_id):
            return _outcome(
                slot_id,
                beliefs_before={"replica": (0.25,) * 4},
                beliefs_after={"replica": (0.25,) * 4},
                equilibrium=True,
            )

    disabled = lifecycle.run_kernel_experiment(
        Controller(), object(), max_iterations=1
    )
    enabled = lifecycle.run_kernel_experiment(
        Controller(),
        object(),
        max_iterations=1,
        parity_replay_enabled=True,
    )

    assert calls == [False, True]
    assert disabled.evidence[0]["pure_kernel_replay_performed"] is False
    assert "pure_kernel_replay_parity" not in disabled.evidence[0]
    assert enabled.evidence[0]["pure_kernel_replay_performed"] is True
    assert enabled.evidence[0]["pure_kernel_replay_parity"] is True


def test_enabled_production_parity_replay_fails_closed(monkeypatch):
    monkeypatch.setattr(
        lifecycle,
        "_slot_evidence",
        lambda **kwargs: {
            "slot_id": kwargs["outcome"].slot.slot_id,
            "pure_kernel_replay_performed": True,
            "pure_kernel_replay_parity": False,
        },
    )

    class Controller:
        def run_slot(self, slot_id):
            return _outcome(
                slot_id,
                beliefs_before={"replica": (0.25,) * 4},
                beliefs_after={"replica": (0.25,) * 4},
                equilibrium=True,
            )

    with pytest.raises(RuntimeError, match="parity replay failed"):
        lifecycle.run_kernel_experiment(
            Controller(),
            object(),
            max_iterations=1,
            parity_replay_enabled=True,
        )


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_production_loop_rejects_invalid_iteration_bounds(value):
    with pytest.raises(ValueError, match="positive integer"):
        lifecycle.run_kernel_experiment(
            object(), object(), first_slot=1, max_iterations=value
        )


@pytest.mark.parametrize(
    ("reached", "expected", "parity_setting", "expected_parity"),
    [
        (True, "Equilibrium reached after 1 iteration(s).", None, False),
        (False, "Equilibrium not reached after 5 iteration(s).", "1", True),
    ],
)
def test_controller_cli_selects_production_lifecycle_and_reports_final_status(
    monkeypatch, capsys, reached, expected, parity_setting, expected_parity
):
    monkeypatch.setenv("HYBRID_CONTROLLER_LIFECYCLE", "experiment")
    monkeypatch.setenv("SLOT_ID", "4")
    monkeypatch.setenv("MAX_ITERATIONS", "5")
    monkeypatch.setenv("HYBRID_POLICY_ROOT_SEED", "987654321")
    if parity_setting is not None:
        monkeypatch.setenv("HYBRID_PARITY_REPLAY", parity_setting)
    close_calls = []
    controller = SimpleNamespace(
        beliefs={ReplicaChoice(1, 1): (0.25, 0.25, 0.25, 0.25)},
        close=lambda: close_calls.append("closed"),
    )
    controller_arguments = {}

    def fake_controller_from_environment(**kwargs):
        controller_arguments.update(kwargs)
        return controller, object()

    monkeypatch.setattr(
        kernel_controller_cli,
        "_controller_from_environment",
        fake_controller_from_environment,
    )
    monkeypatch.setattr(
        kernel_controller_cli,
        "format_hybrid_slot_metrics",
        lambda slot, iteration: f"Iteration {iteration} (slot {slot.slot_id})",
    )

    def fake_experiment(controller, inputs, **kwargs):
        assert kwargs["first_slot"] == 4
        assert kwargs["max_iterations"] == 5
        assert kwargs["parity_replay_enabled"] is expected_parity
        kwargs["on_slot_completed"](
            1,
            SimpleNamespace(slot_id=4),
            {"slot_id": 4},
        )
        controller.beliefs = {
            ReplicaChoice(1, 1): (0.4, 0.3, 0.2, 0.1)
        }
        return SimpleNamespace(
            reached_equilibrium=reached,
            iterations_completed=1 if reached else 5,
        )

    monkeypatch.setattr(
        kernel_controller_cli, "run_kernel_experiment", fake_experiment
    )
    monkeypatch.setattr(
        kernel_controller_cli,
        "run_small_live_gate",
        lambda *args, **kwargs: pytest.fail("production used validation gate"),
    )

    assert kernel_controller_cli.main([]) == 0
    output = capsys.readouterr().out
    assert "Iteration 1 (slot 4)" in output
    assert expected in output
    assert "HYBRID_SLOT_EVIDENCE=" in output
    assert output.count("Initial replica state") == 1
    assert output.count("Final replica state") == 1
    assert "[0.250, 0.250, 0.250, 0.250]" in output
    assert "[0.400, 0.300, 0.200, 0.100]" in output
    assert output.index("Initial replica state") < output.index("Iteration 1")
    assert output.index(expected) < output.index("Final replica state")
    assert "State  Capacity" not in output
    assert controller_arguments["policy_root_seed"] == 987654321
    assert close_calls == ["closed"]


def test_production_cli_requires_positive_dimensions_and_iteration_limit():
    parsed = host_runner.parse_args(
        [
            "run",
            "--skip-build",
            "--flows",
            "10",
            "--stages",
            "3",
            "--replicas",
            "5",
            "--rollout-batch-size",
            "2",
            "--profile-seed",
            "42",
            "--max-iterations",
            "100",
        ]
    )
    assert parsed.action == "run"
    assert (
        parsed.requested_flows,
        parsed.requested_stages,
        parsed.requested_replicas,
        parsed.profile_seed,
        parsed.max_iterations,
    ) == (10, 3, 5, 42, 100)
    assert parsed.trace_dir == host_runner.DEFAULT_HYBRID_TRACE_DIR
    assert parsed.parity_replay == 0

    replay_enabled = host_runner.parse_args(
        [
            "run",
            "--flow", "10",
            "--stage", "3",
            "--replica", "5",
            "--profile-seed", "42",
            "--max-iterations", "100",
            "--parity-replay", "1",
        ]
    )
    assert replay_enabled.parity_replay == 1

    series = host_runner.parse_args(
        [
            "run",
            "--flow", "10",
            "--stage", "3",
            "--replica", "5",
            "--runs", "3",
            "--max-iterations", "100",
        ]
    )
    assert series.runs == 3
    assert series.profile_seed is None

    for invalid_series in (
        [
            "run", "--flow", "10", "--stage", "3", "--replica", "5",
            "--runs", "3", "--profile-seed", "42",
            "--max-iterations", "100",
        ],
        [
            "run", "--flow", "10", "--stage", "3", "--replica", "5",
            "--runs", "3", "--refresh-runtime-profiles",
            "--max-iterations", "100",
        ],
    ):
        with pytest.raises(SystemExit):
            host_runner.parse_args(invalid_series)

    for arguments in (
        ["run", "--flow", "1", "--stage", "3", "--replica", "1"],
        [
            "run",
            "--flow",
            "1",
            "--stage",
            "3",
            "--replica",
            "1",
            "--max-iterations",
            "0",
        ],
    ):
        with pytest.raises(SystemExit):
            host_runner.parse_args(arguments)

    commands = []
    with pytest.raises(RuntimeError, match="exactly three stages"):
        host_runner.run_experiment(
            requested_flows=10,
            requested_stages=4,
            requested_replicas=5,
            max_iterations=100,
            execute=lambda command, capture: commands.append(command) or "",
        )
    assert commands == []

    with pytest.raises(RuntimeError, match="positive integer"):
        host_runner.run_experiment(
            requested_flows=10,
            requested_stages=3,
            requested_replicas=5,
            max_iterations=0,
            execute=lambda command, capture: commands.append(command) or "",
        )
    assert commands == []


def _control_plane_snapshot(value=100):
    payload = {
        "kubernetes_discovery_tx": 0,
        "kubernetes_discovery_rx": value,
        "route_command_tx": value + 1,
        "selected_telemetry_rx": value + 2,
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


def _trace_slot(slot_id, *, equilibrium=False, root_seed=2050, footprint=False):
    item = {
        "slot_id": slot_id,
        "root_seed": root_seed,
        "configuration": {
            "num_flows": 2,
            "num_stages": 3,
            "num_replicas": 1,
            "stage_budget": 2,
        },
        "policy_mode": "lookahead",
        "mc_workers": None,
        "placements": [
            {"flow_id": 1, "measured_pair_ms": 4.25},
            {"flow_id": 2, "measured_pair_ms": 7.5},
        ],
        "observations": [{"flow_id": flow_id, "stage": stage}
                         for flow_id in (1, 2) for stage in (1, 3)],
        "beliefs_before": {"1:1": [0.25, 0.25, 0.25, 0.25]},
        "beliefs_after": {"1:1": [0.25, 0.25, 0.25, 0.25]},
        "pure_kernel_replay_performed": False,
        "metrics": {
            "elapsed_seconds": 0.25,
            "end_to_end_sla_violations": 1,
            "end_to_end_sla_excess_ms": 80.1 - 80.0,
            "sla_latency_threshold_ms": 80.0,
            "raw_end_to_end_latency_ms_per_flow": [[1, 80.0], [2, 80.1]],
            "raw_end_to_end_reference_utility": 17.5,
            "jain_fairness": 0.9,
            "equilibrium": equilibrium,
        },
    }
    if footprint:
        item["control_plane"] = _control_plane_snapshot(slot_id + 100)
    return item


def test_production_trace_persists_lifecycle_and_each_flow_pair(tmp_path):
    output = "\n".join(
        json.dumps(item) for item in (_trace_slot(4), _trace_slot(5, equilibrium=True))
    )
    trace_path = host_runner._persist_hybrid_experiment_trace(
        output,
        trace_dir=tmp_path,
        requested_flows=2,
        requested_stages=3,
        requested_replicas=1,
        max_iterations=10,
    )

    assert trace_path.parent == tmp_path
    assert trace_path.name.startswith("ibg-hybrid-experiment-")
    events = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["event"] for event in events] == [
        "run_started",
        "iteration_completed",
        "iteration_completed",
        "run_completed",
    ]
    assert events[1]["iteration"] == 1
    assert events[1]["slot_id"] == 4
    assert events[0]["trace_contract_version"] == (
        "ibg-hybrid-experiment-jsonl-v3"
    )
    assert events[0]["parity_replay_enabled"] is False
    assert events[1]["pure_kernel_replay_performed"] is False
    assert "pure_kernel_replay_parity" not in events[1]
    assert events[-1]["parity_replay_enabled"] is False
    assert events[1]["metrics"]["end_to_end_sla_violations"] == 1
    assert events[1]["metrics"]["end_to_end_sla_excess_ms"] == pytest.approx(
        0.1
    )
    assert "physical_only_sla_violations" not in events[1]["metrics"]
    assert {
        placement["flow_id"]: placement["measured_pair_ms"]
        for placement in events[1]["placements"]
    } == {1: 4.25, 2: 7.5}
    assert events[-1]["reached_equilibrium"] is True
    assert events[-1]["iterations"] == 2


def test_production_trace_records_enabled_parity_replay(tmp_path):
    slot = _trace_slot(1, equilibrium=True)
    slot["pure_kernel_replay_performed"] = True
    slot["pure_kernel_replay_parity"] = True

    trace_path = host_runner._persist_hybrid_experiment_trace(
        json.dumps(slot),
        trace_dir=tmp_path,
        requested_flows=2,
        requested_stages=3,
        requested_replicas=1,
        max_iterations=1,
        parity_replay_enabled=True,
    )

    events = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert all(event["parity_replay_enabled"] is True for event in events)
    assert events[1]["pure_kernel_replay_performed"] is True
    assert events[1]["pure_kernel_replay_parity"] is True


@pytest.mark.parametrize(
    ("enabled", "performed", "parity", "message"),
    [
        (False, True, True, "provenance"),
        (False, False, True, "disabled parity-replay result"),
        (True, False, None, "provenance"),
        (True, True, False, "did not pass"),
    ],
)
def test_production_trace_rejects_parity_replay_drift(
    tmp_path, enabled, performed, parity, message
):
    slot = _trace_slot(1)
    slot["pure_kernel_replay_performed"] = performed
    if parity is not None:
        slot["pure_kernel_replay_parity"] = parity

    with pytest.raises(RuntimeError, match=message):
        host_runner._persist_hybrid_experiment_trace(
            json.dumps(slot),
            trace_dir=tmp_path,
            requested_flows=2,
            requested_stages=3,
            requested_replicas=1,
            max_iterations=1,
            parity_replay_enabled=enabled,
        )
    assert list(tmp_path.iterdir()) == []


def test_production_trace_rejects_incorrect_end_to_end_sla_count(tmp_path):
    slot = _trace_slot(1)
    slot["metrics"]["end_to_end_sla_violations"] = 0

    with pytest.raises(RuntimeError, match="end-to-end SLA count"):
        host_runner._persist_hybrid_experiment_trace(
            json.dumps(slot),
            trace_dir=tmp_path,
            requested_flows=2,
            requested_stages=3,
            requested_replicas=1,
            max_iterations=1,
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "invalid_excess",
    (-1.0, float("nan"), float("inf")),
)
def test_production_trace_rejects_invalid_end_to_end_sla_excess(
    tmp_path,
    invalid_excess,
):
    slot = _trace_slot(1)
    slot["metrics"]["end_to_end_sla_excess_ms"] = invalid_excess

    with pytest.raises(RuntimeError, match="invalid slot metrics"):
        host_runner._persist_hybrid_experiment_trace(
            json.dumps(slot),
            trace_dir=tmp_path,
            requested_flows=2,
            requested_stages=3,
            requested_replicas=1,
            max_iterations=1,
        )
    assert list(tmp_path.iterdir()) == []


def test_production_trace_rejects_incorrect_end_to_end_sla_excess(tmp_path):
    slot = _trace_slot(1)
    slot["metrics"]["end_to_end_sla_excess_ms"] = 0.2

    with pytest.raises(RuntimeError, match="end-to-end SLA excess"):
        host_runner._persist_hybrid_experiment_trace(
            json.dumps(slot),
            trace_dir=tmp_path,
            requested_flows=2,
            requested_stages=3,
            requested_replicas=1,
            max_iterations=1,
        )
    assert list(tmp_path.iterdir()) == []


def test_production_trace_rejects_threshold_drift_and_incomplete_raw_coverage(
    tmp_path,
):
    drifted = _trace_slot(1)
    drifted["metrics"]["sla_latency_threshold_ms"] = 81.0
    incomplete = _trace_slot(1)
    incomplete["metrics"]["raw_end_to_end_latency_ms_per_flow"].pop()

    for slot in (drifted, incomplete):
        with pytest.raises(RuntimeError, match="invalid slot metrics"):
            host_runner._persist_hybrid_experiment_trace(
                json.dumps(slot),
                trace_dir=tmp_path,
                requested_flows=2,
                requested_stages=3,
                requested_replicas=1,
                max_iterations=1,
            )
    assert list(tmp_path.iterdir()) == []


def test_production_trace_rejects_missing_excess_and_legacy_sla_field(tmp_path):
    missing = _trace_slot(1)
    del missing["metrics"]["end_to_end_sla_excess_ms"]
    legacy = _trace_slot(1)
    legacy["metrics"]["physical_only_sla_violations"] = 0

    for slot in (missing, legacy):
        with pytest.raises(RuntimeError, match="invalid slot metrics"):
            host_runner._persist_hybrid_experiment_trace(
                json.dumps(slot),
                trace_dir=tmp_path,
                requested_flows=2,
                requested_stages=3,
                requested_replicas=1,
                max_iterations=1,
            )
    assert list(tmp_path.iterdir()) == []


def test_production_main_without_csv_does_not_export_quality_csv(
    monkeypatch,
    tmp_path,
):
    output = json.dumps(_trace_slot(1, equilibrium=True)) + "\n"
    monkeypatch.setattr(host_runner, "run_experiment", lambda **kwargs: output)

    def unexpected_export(*args, **kwargs):
        raise AssertionError("CSV export must remain disabled")

    monkeypatch.setattr(host_runner, "export_hybrid_csv", unexpected_export)

    assert host_runner.main(
        [
            "run",
            "--flow", "2",
            "--stage", "3",
            "--replica", "1",
            "--profile-seed", "42",
            "--max-iterations", "1",
            "--trace-dir", str(tmp_path),
        ]
    ) == 0
    assert not (
        tmp_path
        / "figures"
        / "IBG_hybrid"
        / "end_to_end_sla_excess_ms.csv"
    ).exists()


def test_production_trace_rejects_missing_per_flow_pair(tmp_path):
    slot = _trace_slot(1)
    del slot["placements"][1]["measured_pair_ms"]
    with pytest.raises(RuntimeError, match="measured-pair evidence"):
        host_runner._persist_hybrid_experiment_trace(
            json.dumps(slot),
            trace_dir=tmp_path,
            requested_flows=2,
            requested_stages=3,
            requested_replicas=1,
            max_iterations=1,
        )
    assert list(tmp_path.iterdir()) == []


def test_trace_footprint_activation_is_strict_and_persists_only_when_enabled(tmp_path):
    enabled_slot = _trace_slot(1, equilibrium=True, footprint=True)
    disabled_slot = _trace_slot(1, equilibrium=True)

    with pytest.raises(RuntimeError, match="contains disabled"):
        host_runner._persist_hybrid_experiment_trace(
            json.dumps(enabled_slot),
            trace_dir=tmp_path,
            requested_flows=2,
            requested_stages=3,
            requested_replicas=1,
            max_iterations=1,
        )
    with pytest.raises(RuntimeError, match="lacks enabled"):
        host_runner._persist_hybrid_experiment_trace(
            json.dumps(disabled_slot),
            trace_dir=tmp_path,
            requested_flows=2,
            requested_stages=3,
            requested_replicas=1,
            max_iterations=1,
            control_plane_footprint_enabled=True,
        )
    assert not list(tmp_path.iterdir())

    trace_path = host_runner._persist_hybrid_experiment_trace(
        json.dumps(enabled_slot),
        trace_dir=tmp_path,
        requested_flows=2,
        requested_stages=3,
        requested_replicas=1,
        max_iterations=1,
        control_plane_footprint_enabled=True,
    )
    events = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert events[1]["control_plane"] == enabled_slot["control_plane"]
    assert "control_plane" not in events[0]
    assert "control_plane" not in events[-1]


def test_production_main_saves_trace_and_prints_path(monkeypatch, tmp_path, capsys):
    slot = _trace_slot(1, equilibrium=True, footprint=True)
    slot["pure_kernel_replay_performed"] = True
    slot["pure_kernel_replay_parity"] = True
    output = json.dumps(slot) + "\n"
    run_arguments = {}

    def fake_run_experiment(**kwargs):
        run_arguments.update(kwargs)
        return output

    monkeypatch.setattr(host_runner, "run_experiment", fake_run_experiment)
    exported = []

    def fake_export(trace_path):
        exported.append(trace_path)
        return tuple(
            tmp_path / "figures" / name
            for name in host_runner.HYBRID_CSV_FILENAMES
        )

    monkeypatch.setattr(host_runner, "export_hybrid_csv", fake_export)

    assert host_runner.main(
        [
            "run",
            "--flow", "2",
            "--stage", "3",
            "--replica", "1",
            "--profile-seed", "42",
            "--max-iterations", "5",
            "--trace-dir", str(tmp_path),
            "--csv", "1",
            "--parity-replay", "1",
        ]
    ) == 0
    traces = list(tmp_path.glob("ibg-hybrid-experiment-*.jsonl"))
    assert len(traces) == 1
    assert exported == traces
    assert run_arguments["control_plane_footprint_enabled"] is True
    assert run_arguments["parity_replay_enabled"] is True
    events = [json.loads(line) for line in traces[0].read_text().splitlines()]
    assert all(event["parity_replay_enabled"] is True for event in events)
    assert f"Detailed Hybrid JSONL trace: {traces[0]}" in capsys.readouterr().out


def test_random_series_reuses_environment_and_generates_unique_run_seeds(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        host_runner,
        "_resolve_random_series_profile_seed",
        lambda execute: 42,
    )
    generated = iter((101, 202, 303))
    monkeypatch.setattr(
        host_runner.secrets,
        "randbits",
        lambda bits: next(generated),
    )
    calls = []

    def fake_run_experiment(**kwargs):
        calls.append(kwargs)
        slot = _trace_slot(
            kwargs["first_slot_id"],
            equilibrium=True,
            root_seed=kwargs["policy_root_seed"],
            footprint=kwargs["control_plane_footprint_enabled"],
        )
        slot["pure_kernel_replay_performed"] = kwargs[
            "parity_replay_enabled"
        ]
        if kwargs["parity_replay_enabled"]:
            slot["pure_kernel_replay_parity"] = True
        return json.dumps(slot) + "\n"

    monkeypatch.setattr(host_runner, "run_experiment", fake_run_experiment)
    traces = host_runner.run_experiment_series(
        runs=3,
        trace_dir=tmp_path,
        skip_build=False,
        requested_flows=2,
        requested_stages=3,
        requested_replicas=1,
        rollout_batch_size=1,
        max_iterations=5,
        csv_enabled=True,
        parity_replay_enabled=True,
        csv_output_dir=tmp_path / "figures",
    )

    assert len(traces) == 3
    assert [call["profile_seed"] for call in calls] == [42, 42, 42]
    assert [call["policy_root_seed"] for call in calls] == [101, 202, 303]
    assert [call["first_slot_id"] for call in calls] == [101, 202, 303]
    assert [call["skip_build"] for call in calls] == [False, True, True]
    assert all(call["parity_replay_enabled"] is True for call in calls)
    assert [path.name.rsplit("-", 1)[-1] for path in traces] == [
        "run001.jsonl",
        "run002.jsonl",
        "run003.jsonl",
    ]
    for index, (trace, seed) in enumerate(zip(traces, (101, 202, 303)), start=1):
        events = [
            json.loads(line)
            for line in trace.read_text(encoding="utf-8").splitlines()
        ]
        assert events[0]["experiment_seed"] == seed
        assert events[0]["series_run_index"] == index
        assert events[0]["series_run_count"] == 3
        assert events[1]["slot_id"] == seed
        assert all(event["parity_replay_enabled"] is True for event in events)
        assert events[1]["pure_kernel_replay_parity"] is True
        assert events[-1]["experiment_seed"] == seed
    assert len(
        {
            json.loads(trace.read_text(encoding="utf-8").splitlines()[0])[
                "series_id"
            ]
            for trace in traces
        }
    ) == 1
    output = capsys.readouterr().out
    assert "experiment-seeds=automatic-system-random" in output
    with (tmp_path / "figures" / "aggregate_utility.csv").open(
        encoding="utf-8"
    ) as source:
        assert len(source.readline().strip().split(",")) == 3
    with (tmp_path / "figures" / "replica_results.csv").open(
        encoding="utf-8"
    ) as source:
        assert len(source.read().splitlines()) == 7


def test_series_profile_seed_reuses_existing_seeded_environment(monkeypatch):
    monkeypatch.setattr(
        host_runner,
        "_kind_clusters",
        lambda execute: {host_runner.CLUSTER_NAME},
    )
    monkeypatch.setattr(host_runner, "preflight", lambda execute: None)
    runtime = host_runner._profile_boundary(
        1,
        requested_flows=2,
        requested_stages=3,
        profile_seed=42,
    ).runtime_document
    monkeypatch.setattr(
        host_runner,
        "_deployed_profile_documents",
        lambda execute: (runtime, {}),
    )

    def execute(command, capture):
        assert command == host_runner._kubectl(
            "get", "namespaces", "-o", "json"
        )
        return json.dumps(
            {"items": [{"metadata": {"name": host_runner.HYBRID_NAMESPACE}}]}
        )

    assert host_runner._resolve_random_series_profile_seed(execute) == 42


def test_random_seed_generation_rejects_zero_and_duplicates(monkeypatch):
    generated = iter((0, 77, 77, 88))
    monkeypatch.setattr(
        host_runner.secrets,
        "randbits",
        lambda bits: next(generated),
    )
    first = host_runner._random_positive_seed()
    second = host_runner._random_positive_seed(excluded={first})
    assert (first, second) == (77, 88)


def test_series_profile_seed_is_random_for_a_fresh_cluster(monkeypatch):
    monkeypatch.setattr(
        host_runner,
        "_kind_clusters",
        lambda execute: set(),
    )
    monkeypatch.setattr(
        host_runner.secrets,
        "randbits",
        lambda bits: 123456789,
    )
    assert host_runner._resolve_random_series_profile_seed(
        lambda command, capture: ""
    ) == 123456789


def test_production_main_routes_runs_to_automatic_series(monkeypatch, tmp_path):
    captured = {}

    def fake_series(**kwargs):
        captured.update(kwargs)
        return ()

    monkeypatch.setattr(host_runner, "run_experiment_series", fake_series)
    assert host_runner.main(
        [
            "run",
            "--flow", "2",
            "--stage", "3",
            "--replica", "1",
            "--runs", "4",
            "--max-iterations", "5",
            "--trace-dir", str(tmp_path),
            "--csv", "1",
        ]
    ) == 0
    assert captured["runs"] == 4
    assert captured["trace_dir"] == tmp_path
    assert captured["csv_enabled"] is True
    assert "profile_seed" not in captured


def test_run_experiment_forwards_optional_instrumentation_to_job_lifecycle(
    monkeypatch,
):
    captured = {}

    def fake_run_small(**kwargs):
        captured.update(kwargs)
        return "evidence"

    monkeypatch.setattr(host_runner, "run_small", fake_run_small)
    assert host_runner.run_experiment(
        requested_flows=2,
        requested_stages=3,
        requested_replicas=1,
        max_iterations=2,
        control_plane_footprint_enabled=True,
        parity_replay_enabled=True,
    ) == "evidence"
    assert captured["production_experiment"] is True
    assert captured["control_plane_footprint_enabled"] is True
    assert captured["parity_replay_enabled"] is True

def test_production_job_receives_iteration_limit_without_gate_deadline(tmp_path):
    applied = {}
    template = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": host_runner.DYNAMIC_CONTROLLER_JOB_NAME,
            "namespace": host_runner.HYBRID_NAMESPACE,
        },
        "spec": {
            "activeDeadlineSeconds": 600,
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "controller",
                            "env": [{"name": "SLOT_ID", "value": "1"}],
                        }
                    ]
                }
            },
        },
    }

    def execute(command, capture_output):
        if "create" in command:
            return json.dumps(template)
        if "apply" in command:
            manifest = Path(command[command.index("-f") + 1])
            applied.update(json.loads(manifest.read_text(encoding="utf-8")))
        return ""

    host_runner._apply_controller_job(
        execute,
        controller_job=host_runner.DYNAMIC_CONTROLLER_JOB,
        controller_job_name=host_runner.DYNAMIC_CONTROLLER_JOB_NAME,
        arguments=None,
        environment={
            "HYBRID_CONTROLLER_LIFECYCLE": "experiment",
            "MAX_ITERATIONS": "100",
        },
        remove_active_deadline=True,
    )

    assert "activeDeadlineSeconds" not in applied["spec"]
    container = applied["spec"]["template"]["spec"]["containers"][0]
    assert {item["name"]: item["value"] for item in container["env"]} == {
        "SLOT_ID": "1",
        "HYBRID_CONTROLLER_LIFECYCLE": "experiment",
        "MAX_ITERATIONS": "100",
    }


def test_dynamic_job_template_is_a_historical_gate_not_a_production_limit():
    text = host_runner.DYNAMIC_CONTROLLER_JOB.read_text(encoding="utf-8")
    assert "MAX_ITERATIONS" not in text
    assert "HYBRID_CONTROLLER_LIFECYCLE" not in text
