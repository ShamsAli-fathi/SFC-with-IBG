import copy
import json

import pytest

from IBG_Hybrid.contracts import ReplicaChoice
from IBG_Hybrid.posterior_mirror import (
    HYBRID_POSTERIOR_MIRROR_SCHEMA,
    HybridPosteriorMirrorHttpClient,
    posterior_mirror_provenance,
)
from scripts.hybrid_posterior_mirror_summary import main, summarize_trace


def _snapshot(slot_id, beliefs, *, run_id="controller-pod-uid"):
    import httpx

    from IBG_Hybrid.posterior_mirror import build_canonical_posterior_update

    def receive(request):
        document = json.loads(request.content)
        canonical = build_canonical_posterior_update(
            run_id=document["run_id"],
            slot_id=document["slot_id"],
            choice=ReplicaChoice(document["stage"], document["replica"]),
            posterior=document["posterior"],
        )
        return httpx.Response(200, json=canonical.receipt.model_dump(mode="json"))

    client = HybridPosteriorMirrorHttpClient(
        "http://mirror.test",
        run_id=run_id,
        transport=httpx.MockTransport(receive),
    )
    try:
        return client.mirror_slot(
            slot_id=slot_id,
            beliefs_after=beliefs,
            updated_choices=tuple(beliefs),
        )
    finally:
        client.close()


def _trace(path):
    beliefs = {
        ReplicaChoice(1, 1): (0.4, 0.3, 0.2, 0.1),
        ReplicaChoice(2, 1): (0.1, 0.2, 0.3, 0.4),
    }
    first = _snapshot(41, beliefs)
    second = _snapshot(42, beliefs)
    recorded_beliefs = {
        f"{choice.stage}:{choice.replica}": list(posterior)
        for choice, posterior in beliefs.items()
    }
    observations = [
        {"stage": choice.stage, "replica": choice.replica}
        for choice in beliefs
    ]
    provenance = posterior_mirror_provenance(True)
    events = [
        {
            "event": "run_started",
            "configuration": {
                "num_flows": 2,
                "num_stages": 3,
                "num_replicas": 1,
                "stage_budget": 2,
            },
            "posterior_mirror_configuration": provenance,
        },
        {
            "event": "iteration_completed",
            "iteration": 1,
            "slot_id": 41,
            "beliefs_after": recorded_beliefs,
            "observations": observations,
            "posterior_mirror": first,
            "posterior_mirror_configuration": provenance,
        },
        {
            "event": "iteration_completed",
            "iteration": 2,
            "slot_id": 42,
            "beliefs_after": recorded_beliefs,
            "observations": observations,
            "posterior_mirror": second,
            "posterior_mirror_configuration": provenance,
        },
        {
            "event": "run_completed",
            "iterations": 2,
            "posterior_mirror_configuration": provenance,
        },
    ]
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    return events


def test_summary_reports_per_timeslot_totals_median_p95_and_boundary(tmp_path):
    path = tmp_path / "trace.jsonl"
    events = _trace(path)

    report = summarize_trace(path)

    vector = report["metrics"]["posterior_vector_payload_bytes"]
    expected = [
        events[1]["posterior_mirror"]["payload_bytes"]["posterior_vectors"],
        events[2]["posterior_mirror"]["payload_bytes"]["posterior_vectors"],
    ]
    assert vector == {
        "per_timeslot": expected,
        "total": sum(expected),
        "median": float(expected[0]),
        "p95": float(expected[0]),
    }
    bodies = report["metrics"]["posterior_application_body_bytes"]
    assert bodies["total"] == sum(bodies["per_timeslot"])
    messages = report["metrics"]["posterior_update_messages"]
    assert messages["per_timeslot"] == [2, 2]
    assert messages["total"] == 4
    assert "non-authoritative" in report["measurement_boundary"]
    assert "wire overhead" in report["measurement_boundary"]


def test_summary_rejects_disabled_missing_malformed_and_run_id_drift(tmp_path):
    path = tmp_path / "trace.jsonl"
    events = _trace(path)

    disabled = copy.deepcopy(events)
    for event in disabled:
        event["posterior_mirror_configuration"] = posterior_mirror_provenance(False)
    path.write_text("".join(json.dumps(event) + "\n" for event in disabled))
    with pytest.raises(ValueError, match="drifted"):
        summarize_trace(path)

    missing = copy.deepcopy(events)
    missing[2].pop("posterior_mirror")
    path.write_text("".join(json.dumps(event) + "\n" for event in missing))
    with pytest.raises(ValueError, match="lacks enabled"):
        summarize_trace(path)

    malformed = copy.deepcopy(events)
    malformed[1]["posterior_mirror"]["messages"]["posterior_updates"] += 1
    path.write_text("".join(json.dumps(event) + "\n" for event in malformed))
    with pytest.raises(ValueError, match="does not match"):
        summarize_trace(path)

    drifted = copy.deepcopy(events)
    beliefs = {
        ReplicaChoice(*(int(item) for item in identity.split(":"))): tuple(
            posterior
        )
        for identity, posterior in drifted[2]["beliefs_after"].items()
    }
    drifted[2]["posterior_mirror"] = _snapshot(
        42, beliefs, run_id="different-run"
    )
    path.write_text("".join(json.dumps(event) + "\n" for event in drifted))
    with pytest.raises(ValueError, match="run identity drifted"):
        summarize_trace(path)


def test_summary_cli_emits_versioned_hybrid_mirror_report(tmp_path, capsys):
    path = tmp_path / "trace.jsonl"
    _trace(path)

    assert main([str(path)]) == 0
    prefix, payload = capsys.readouterr().out.strip().split("=", 1)
    assert prefix == "HYBRID_POSTERIOR_MIRROR_SUMMARY"
    report = json.loads(payload)
    assert report["posterior_mirror_schema"] == HYBRID_POSTERIOR_MIRROR_SCHEMA
    assert len(report["runs"]) == 1
