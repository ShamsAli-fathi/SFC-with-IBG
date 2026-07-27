import os
import threading


SOLVER_RESOURCE_SCHEMA = "solver_resource_v1"
DEFAULT_SAMPLE_INTERVAL_SECONDS = 0.005


def read_current_rss_bytes():
    """Return current process RSS from procfs, not a lifetime high-water mark."""
    with open("/proc/self/statm", encoding="ascii") as source:
        fields = source.read().split()
    if len(fields) < 2:
        raise RuntimeError("/proc/self/statm does not contain an RSS field")
    resident_pages = int(fields[1])
    if resident_pages < 0:
        raise RuntimeError("current RSS page count must not be negative")
    return resident_pages * os.sysconf("SC_PAGE_SIZE")


def validate_solver_resource_snapshot(snapshot, *, expected_stages=None):
    if not isinstance(snapshot, dict):
        raise ValueError("solver resource snapshot must be an object")
    if snapshot.get("schema") != SOLVER_RESOURCE_SCHEMA:
        raise ValueError("unsupported solver resource schema")

    rss = snapshot.get("rss_bytes")
    if not isinstance(rss, dict):
        raise ValueError("solver resource RSS values must be an object")
    required_rss = (
        "before_admission",
        "peak_during_slot",
        "after_feedback",
        "peak_incremental_working_memory",
    )
    for field in required_rss:
        value = rss.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"solver resource RSS {field} must be non-negative")
    if rss["peak_during_slot"] < rss["before_admission"]:
        raise ValueError("peak RSS must not be below the admission baseline")
    if rss["peak_during_slot"] < rss["after_feedback"]:
        raise ValueError("peak RSS must not be below post-feedback RSS")
    if rss["peak_incremental_working_memory"] != (
        rss["peak_during_slot"] - rss["before_admission"]
    ):
        raise ValueError("incremental working memory must equal peak minus baseline")

    exact_policy = snapshot.get("exact_policy")
    if not isinstance(exact_policy, dict):
        raise ValueError("solver resource exact-policy values must be an object")
    for field in ("peak_memo_entries", "post_embedding_residual_entries"):
        value = exact_policy.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"exact-policy {field} must be non-negative")

    stages = exact_policy.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("solver resource snapshot must contain stage records")
    stage_ids = []
    for record in stages:
        if not isinstance(record, dict):
            raise ValueError("solver resource stage record must be an object")
        stage = record.get("stage")
        peak = record.get("peak_memo_entries")
        residual = record.get("post_embedding_residual_entries")
        if isinstance(stage, bool) or not isinstance(stage, int) or stage < 1:
            raise ValueError("solver resource stage ID must be positive")
        if isinstance(peak, bool) or not isinstance(peak, int) or peak < 0:
            raise ValueError("stage peak memo entries must be non-negative")
        if isinstance(residual, bool) or not isinstance(residual, int) or residual < 0:
            raise ValueError("stage residual memo entries must be non-negative")
        if residual > peak:
            raise ValueError("stage residual memo entries cannot exceed its peak")
        stage_ids.append(stage)
    if stage_ids != sorted(set(stage_ids)):
        raise ValueError("solver resource stages must be unique and ordered")
    if expected_stages is not None and stage_ids != list(
        range(1, expected_stages + 1)
    ):
        raise ValueError("solver resource stage records are incomplete")
    if exact_policy["peak_memo_entries"] != max(
        record["peak_memo_entries"] for record in stages
    ):
        raise ValueError("overall peak memo entries must match the stage maximum")
    if exact_policy["post_embedding_residual_entries"] != max(
        record["post_embedding_residual_entries"] for record in stages
    ):
        raise ValueError("overall residual entries must match the stage maximum")
    return snapshot


class SolverResourceMeter:
    """Opt-in current-RSS sampler and exact-policy cache-accounting meter."""

    def __init__(
        self,
        *,
        rss_reader=read_current_rss_bytes,
        sample_interval_seconds=DEFAULT_SAMPLE_INTERVAL_SECONDS,
    ):
        if sample_interval_seconds is not None and sample_interval_seconds <= 0:
            raise ValueError("sample interval must be positive or None")
        self._rss_reader = rss_reader
        self._sample_interval_seconds = sample_interval_seconds
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._sample_error = None
        self._baseline = None
        self._peak = None
        self._after_feedback = None
        self._stages = []

    def _read_and_observe(self):
        value = self._rss_reader()
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RuntimeError("RSS reader must return non-negative integer bytes")
        with self._lock:
            self._peak = value if self._peak is None else max(self._peak, value)
        return value

    def _sample_loop(self):
        while not self._stop.wait(self._sample_interval_seconds):
            try:
                self._read_and_observe()
            except BaseException as error:
                self._sample_error = error
                self._stop.set()
                return

    def begin_slot(self):
        if self._baseline is not None:
            raise RuntimeError("solver resource slot has already begun")
        self._baseline = self._read_and_observe()
        if self._sample_interval_seconds is not None:
            self._thread = threading.Thread(
                target=self._sample_loop,
                name="solver-resource-rss",
                daemon=True,
            )
            self._thread.start()

    def observe_rss(self):
        if self._baseline is None or self._after_feedback is not None:
            raise RuntimeError("solver resource slot is not active")
        return self._read_and_observe()

    def record_stage_cache(self, stage, peak_entries, residual_entries):
        if self._baseline is None or self._after_feedback is not None:
            raise RuntimeError("solver resource slot is not active")
        if self._stages and stage <= self._stages[-1]["stage"]:
            raise ValueError("solver resource stages must be recorded in order")
        peak_entries = int(peak_entries)
        residual_entries = int(residual_entries)
        if (
            peak_entries < 0
            or residual_entries < 0
            or residual_entries > peak_entries
        ):
            raise ValueError("solver resource cache entries are inconsistent")
        self._read_and_observe()
        self._stages.append(
            {
                "stage": int(stage),
                "peak_memo_entries": peak_entries,
                "post_embedding_residual_entries": residual_entries,
            }
        )

    def finish_slot(self):
        if self._baseline is None or self._after_feedback is not None:
            raise RuntimeError("solver resource slot is not active")
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        if self._sample_error is not None:
            raise RuntimeError("controller RSS sampling failed") from self._sample_error
        self._after_feedback = self._read_and_observe()

    def abort_slot(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def snapshot(self, *, expected_stages=None):
        if self._after_feedback is None:
            raise RuntimeError("solver resource slot has not finished")
        snapshot = {
            "schema": SOLVER_RESOURCE_SCHEMA,
            "rss_bytes": {
                "before_admission": self._baseline,
                "peak_during_slot": self._peak,
                "after_feedback": self._after_feedback,
                "peak_incremental_working_memory": self._peak - self._baseline,
            },
            "exact_policy": {
                "peak_memo_entries": max(
                    record["peak_memo_entries"] for record in self._stages
                ),
                "post_embedding_residual_entries": max(
                    record["post_embedding_residual_entries"]
                    for record in self._stages
                ),
                "stages": list(self._stages),
            },
        }
        return validate_solver_resource_snapshot(
            snapshot,
            expected_stages=expected_stages,
        )
