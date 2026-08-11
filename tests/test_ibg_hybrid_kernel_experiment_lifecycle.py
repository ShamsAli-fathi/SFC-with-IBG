import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from IBG_Hybrid import kernel_controller_cli
from IBG_Hybrid import kernel_phase4_validation as lifecycle
from IBG_Hybrid.console_output import format_hybrid_replica_beliefs
from IBG_Hybrid.contracts import ReplicaChoice
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


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_production_loop_rejects_invalid_iteration_bounds(value):
    with pytest.raises(ValueError, match="positive integer"):
        lifecycle.run_kernel_experiment(
            object(), object(), first_slot=1, max_iterations=value
        )


@pytest.mark.parametrize(
    ("reached", "expected"),
    [
        (True, "Equilibrium reached after 1 iteration(s)."),
        (False, "Equilibrium not reached after 5 iteration(s)."),
    ],
)
def test_controller_cli_selects_production_lifecycle_and_reports_final_status(
    monkeypatch, capsys, reached, expected
):
    monkeypatch.setenv("HYBRID_CONTROLLER_LIFECYCLE", "experiment")
    monkeypatch.setenv("SLOT_ID", "4")
    monkeypatch.setenv("MAX_ITERATIONS", "5")
    controller = SimpleNamespace(
        beliefs={ReplicaChoice(1, 1): (0.25, 0.25, 0.25, 0.25)}
    )
    monkeypatch.setattr(
        kernel_controller_cli,
        "_controller_from_environment",
        lambda **kwargs: (controller, object()),
    )
    monkeypatch.setattr(
        kernel_controller_cli,
        "format_hybrid_slot_metrics",
        lambda slot, iteration: f"Iteration {iteration} (slot {slot.slot_id})",
    )

    def fake_experiment(controller, inputs, **kwargs):
        assert kwargs["first_slot"] == 4
        assert kwargs["max_iterations"] == 5
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
