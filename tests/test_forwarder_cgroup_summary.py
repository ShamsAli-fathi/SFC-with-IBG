import json

import pytest

from scripts.forwarder_cgroup_summary import summarize_trace


def _snapshot(stage, replica_id, value):
    return {
        "stage": stage,
        "replica_id": replica_id,
        "pod_name": f"stage-{stage}-{replica_id - 1}",
        "cgroup_version": "v2",
        "usage_usec": value,
        "nr_periods": value,
        "nr_throttled": value,
        "throttled_usec": value,
        "quota_usec": 50_000,
        "period_usec": 100_000,
        "weight": 6,
    }


def _forwarder(stage, replica_id, before, after):
    return {
        "stage": stage,
        "replica_id": replica_id,
        "pod_name": f"stage-{stage}-{replica_id - 1}",
        "endpoint": f"http://stage-{stage}-{replica_id - 1}",
        "route_requests": 1,
        "source_pair_requests": 1 if stage == 1 else 0,
        "before": _snapshot(stage, replica_id, before),
        "after": _snapshot(stage, replica_id, after),
        "usage_usec_delta": after - before,
        "periods_delta": after - before,
        "throttled_periods_delta": after - before,
        "throttled_usec_delta": after - before,
    }


def _events():
    forwarders = [_forwarder(1, 1, 10, 15), _forwarder(2, 2, 20, 23)]
    return [
        {
            "event": "run_started",
            "forwarder_cgroup_diagnostics": True,
            "learning_signal_mode": "separated-v1",
            "configuration": {"stages": 2, "replicas_per_stage": 2, "flows": 1},
        },
        {
            "event": "iteration_completed",
            "slot_id": 1,
            "summary": {
                "placements": [
                    {"stage": 1, "flow_id": 1, "replica_id": 1},
                    {"stage": 2, "flow_id": 1, "replica_id": 2},
                ],
                "traffic": {
                    "forwarder_cgroup": {
                        "schema_version": "forwarder_cgroup_v1",
                        "selection_scope": "selected_forwarders_only",
                        "before_snapshot_elapsed_ms": 1.0,
                        "after_snapshot_elapsed_ms": 2.0,
                        "snapshot_elapsed_ms": 3.0,
                        "forwarders": forwarders,
                        "totals": {
                            "usage_usec_delta": 8,
                            "periods_delta": 8,
                            "throttled_periods_delta": 8,
                            "throttled_usec_delta": 8,
                        },
                    }
                },
            },
        },
    ]


def test_forwarder_cgroup_summary_validates_selected_slot_deltas(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in _events()),
        encoding="utf-8",
    )

    summary = summarize_trace(path)

    assert summary["learning_signal_mode"] == "separated-v1"
    assert summary["slots"] == [
        {
            "slot_id": 1,
            "selected_forwarders": 2,
            "usage_ms": 0.008,
            "throttled_periods": 8,
            "throttled_ms": 0.008,
            "snapshot_elapsed_ms": 3.0,
        }
    ]


def test_forwarder_cgroup_summary_rejects_inconsistent_totals(tmp_path):
    events = _events()
    events[1]["summary"]["traffic"]["forwarder_cgroup"]["totals"][
        "throttled_usec_delta"
    ] = 9
    path = tmp_path / "trace.jsonl"
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="totals do not match"):
        summarize_trace(path)
