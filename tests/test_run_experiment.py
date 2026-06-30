import json
from types import SimpleNamespace

import scripts.run_experiment as launcher
from scripts.run_experiment import follow_logs, render_event, set_env


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


def test_render_event_prints_iteration_details(capsys):
    render_event(
        {
            "event": "iteration_completed",
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
