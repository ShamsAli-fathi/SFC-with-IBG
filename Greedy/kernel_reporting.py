"""One-run host reporting wrapper around the completed Phase 5 lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Callable

from .csv_export import DEFAULT_GREEDY_CSV_DIR, export_greedy_csv
from .evidence import GREEDY_SLOT_EVIDENCE_PREFIX
from .kernel_infrastructure import GREEDY_CONTROLLER_JOB, GREEDY_NAMESPACE
from .kernel_lifecycle import (
    GREEDY_CONTEXT,
    ROOT,
    Executor,
    GreedyLaunchConfiguration,
    GreedyLifecycleResult,
    WheelhouseValidator,
    _execute,
    run_greedy_lifecycle,
)
from .persistence import (
    DEFAULT_GREEDY_TRACE_DIR,
    GreedyTraceWriteResult,
    persist_greedy_trace,
    project_greedy_controller_output,
)


@dataclass(frozen=True)
class GreedyReportedRun:
    lifecycle: GreedyLifecycleResult
    trace: GreedyTraceWriteResult
    csv_paths: tuple[Path, ...]


def _follow_controller_logs(emit: Callable[[str], None]) -> None:
    """Print completed-slot output while the finite controller Job is running.

    This is display only.  The machine-readable evidence lines stay hidden here
    and are re-read verbatim from the finished Job afterwards, so a dropped or
    truncated follow can never shorten, reorder, or alter the persisted trace.
    """

    process = subprocess.Popen(
        (
            "kubectl", "--context", GREEDY_CONTEXT, "logs", "--follow",
            "-n", GREEDY_NAMESPACE, f"job/{GREEDY_CONTROLLER_JOB}",
            "--container=controller", "--pod-running-timeout=600s",
        ),
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip("\n")
            if not line.startswith(GREEDY_SLOT_EVIDENCE_PREFIX):
                emit(line)
    finally:
        if process.stdout is not None:
            process.stdout.close()
        process.wait()


def _controller_logs(execute: Executor) -> str:
    return execute(
        (
            "kubectl", "--context", GREEDY_CONTEXT, "logs", "-n",
            GREEDY_NAMESPACE, f"job/{GREEDY_CONTROLLER_JOB}",
            "--container=controller",
        ),
        True,
    )


def run_greedy_evidenced_lifecycle(
    launch: GreedyLaunchConfiguration,
    *,
    execute: Executor = _execute,
    validate_wheelhouses: WheelhouseValidator | None = None,
    emit: Callable[[str], None] = print,
    controller_log_output: Callable[[], str] | None = None,
    trace_dir: Path = DEFAULT_GREEDY_TRACE_DIR,
    csv_output_dir: Path = DEFAULT_GREEDY_CSV_DIR,
) -> GreedyReportedRun:
    followed_live = controller_log_output is None
    lifecycle = run_greedy_lifecycle(
        launch,
        execute=execute,
        validate_wheelhouses=validate_wheelhouses,
        emit=emit,
        stream_logs=(
            (lambda: _follow_controller_logs(emit)) if followed_live else None
        ),
    )
    output = (
        _controller_logs(execute)
        if controller_log_output is None
        else controller_log_output()
    )
    # Slot output already reached the terminal live; re-emitting the same text
    # from the captured log would duplicate every completed slot.
    evidence = project_greedy_controller_output(
        output,
        emit=(lambda _line: None) if followed_live else emit,
    )
    if not evidence:
        raise RuntimeError("Greedy controller emitted no completed-slot evidence")
    trace = persist_greedy_trace(
        evidence,
        launch=launch,
        lifecycle=lifecycle,
        trace_dir=trace_dir,
    )
    emit(f"Detailed Greedy JSONL trace: {trace.path}")
    csv_paths: tuple[Path, ...] = ()
    if launch.csv:
        csv_paths = export_greedy_csv(trace.path, csv_output_dir)
        emit(f"Greedy CSV reports: {csv_output_dir}")
        for path in csv_paths:
            emit(f"  {path.relative_to(csv_output_dir)}")
    return GreedyReportedRun(lifecycle, trace, csv_paths)
