import json

import pytest

from scripts.solver_resource_summary import summarize_trace


def snapshot(baseline, peak, after, cache):
    return {
        "schema": "solver_resource_v1",
        "rss_bytes": {
            "before_admission": baseline,
            "peak_during_slot": peak,
            "after_feedback": after,
            "peak_incremental_working_memory": peak - baseline,
        },
        "exact_policy": {
            "peak_memo_entries": cache,
            "post_embedding_residual_entries": 0,
            "stages": [
                {
                    "stage": 1,
                    "peak_memo_entries": cache,
                    "post_embedding_residual_entries": 0,
                }
            ],
        },
    }


def write_trace(path, *, enabled=True, include_snapshot=True):
    events = [
        {
            "event": "run_started",
            "memory_diagnostics": enabled,
            "datapath_mode": "kernel",
            "configuration": {"stages": 1, "replicas_per_stage": 2, "flows": 3},
        },
        {
            "event": "iteration_completed",
            "summary": (
                {"solver_resource": snapshot(100, 160, 120, 10)}
                if include_snapshot
                else {}
            ),
        },
        {
            "event": "iteration_completed",
            "summary": (
                {"solver_resource": snapshot(120, 200, 130, 12)}
                if include_snapshot
                else {}
            ),
        },
        {"event": "run_completed", "reached_equilibrium": True},
    ]
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )


def test_summary_reports_rss_and_cache_distributions(tmp_path):
    path = tmp_path / "trace.jsonl"
    write_trace(path)

    report = summarize_trace(path)

    assert report["iterations"] == 2
    assert report["rss_bytes"]["peak_incremental_working_memory"]["mean"] == 70
    assert report["rss_bytes"]["peak_during_slot"]["maximum"] == 200
    assert report["rss_mib"]["peak_during_slot"]["maximum"] == pytest.approx(
        200 / (1024 * 1024)
    )
    assert report["exact_policy"]["peak_memo_entries"]["maximum"] == 12
    assert report["exact_policy"]["stages"]["1"][
        "post_embedding_residual_entries"
    ]["maximum"] == 0


def test_summary_rejects_memory_disabled_trace(tmp_path):
    path = tmp_path / "trace.jsonl"
    write_trace(path, enabled=False)

    with pytest.raises(ValueError, match="--memory 1"):
        summarize_trace(path)
