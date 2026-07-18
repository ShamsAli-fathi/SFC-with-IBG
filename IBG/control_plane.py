from dataclasses import dataclass, field
import math
import time


CONTROL_PLANE_SCHEMA = "control_plane_v1"

PAYLOAD_FIELDS = (
    "kubernetes_discovery_tx",
    "kubernetes_discovery_rx",
    "route_command_tx",
    "selected_telemetry_rx",
    "belief_tx",
    "belief_rx",
)

MESSAGE_FIELDS = PAYLOAD_FIELDS


def validate_control_plane_snapshot(snapshot, *, expected_stages=None):
    if snapshot.get("schema") != CONTROL_PLANE_SCHEMA:
        raise ValueError("unsupported control-plane measurement schema")

    timing = snapshot.get("timing_ms")
    cpu = snapshot.get("cpu_ms")
    payload = snapshot.get("payload_bytes")
    messages = snapshot.get("messages")
    _require_numeric_fields(
        timing,
        ("discovery", "admission", "feedback", "active", "data_plane_wait"),
        "timing_ms",
    )
    _require_numeric_fields(
        cpu,
        ("discovery", "admission", "feedback", "active"),
        "cpu_ms",
    )
    if not math.isclose(
        timing["active"],
        timing["admission"] + timing["feedback"],
        abs_tol=1e-9,
    ):
        raise ValueError("control-plane wall active time does not match components")
    if not math.isclose(
        cpu["active"],
        cpu["admission"] + cpu["feedback"],
        abs_tol=1e-9,
    ):
        raise ValueError("control-plane CPU active time does not match components")
    if timing["discovery"] > timing["admission"] + 1e-9:
        raise ValueError("discovery time exceeds admission time")
    if cpu["discovery"] > cpu["admission"] + 1e-9:
        raise ValueError("discovery CPU time exceeds admission CPU time")

    _require_count_fields(payload, PAYLOAD_FIELDS, "payload_bytes")
    _require_count_fields(messages, MESSAGE_FIELDS, "messages")
    if payload.get("total") != sum(payload[name] for name in PAYLOAD_FIELDS):
        raise ValueError("control-plane payload total does not match components")
    if messages.get("total") != sum(messages[name] for name in MESSAGE_FIELDS):
        raise ValueError("control-plane message total does not match components")
    if expected_stages is not None:
        if expected_stages < 1:
            raise ValueError("expected_stages must be positive")
        for field in ("kubernetes_discovery_tx", "kubernetes_discovery_rx"):
            if messages[field] != expected_stages:
                raise ValueError(
                    f"{field} must contain one message per configured stage"
                )
        if messages["route_command_tx"] != 1:
            raise ValueError("a completed slot must contain one route command")
        if messages["selected_telemetry_rx"] != 1:
            raise ValueError("a completed slot must contain one telemetry response")
    return snapshot


def _require_numeric_fields(document, expected, label):
    if not isinstance(document, dict) or set(document) != set(expected):
        raise ValueError(f"invalid control-plane {label} fields")
    for name in expected:
        value = document[name]
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"control-plane {label}.{name} must be finite")
        if value < 0:
            raise ValueError(f"control-plane {label}.{name} must be non-negative")


def _require_count_fields(document, expected, label):
    if not isinstance(document, dict) or set(document) != {*expected, "total"}:
        raise ValueError(f"invalid control-plane {label} fields")
    for name in (*expected, "total"):
        value = document[name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(
                f"control-plane {label}.{name} must be a non-negative integer"
            )


@dataclass
class ControlPlaneMeter:
    """Measure controller work without counting selected-route RPCs."""

    wall_clock_ns: object = time.perf_counter_ns
    cpu_clock_ns: object = time.process_time_ns
    payload_bytes: dict = field(default_factory=dict)
    messages: dict = field(default_factory=dict)

    def __post_init__(self):
        self._reset_counts()
        self._slot_started_wall_ns = None
        self._slot_started_cpu_ns = None
        self._discovery_started_wall_ns = None
        self._discovery_started_cpu_ns = None
        self._discovery_wall_ns = 0
        self._discovery_cpu_ns = 0
        self._dispatch_wall_ns = None
        self._dispatch_cpu_ns = None
        self._telemetry_wall_ns = None
        self._telemetry_cpu_ns = None
        self._finished_wall_ns = None
        self._finished_cpu_ns = None

    def _reset_counts(self):
        self.payload_bytes = {name: 0 for name in PAYLOAD_FIELDS}
        self.messages = {name: 0 for name in MESSAGE_FIELDS}

    def begin_slot(self):
        self._reset_counts()
        self._discovery_wall_ns = 0
        self._discovery_cpu_ns = 0
        self._dispatch_wall_ns = None
        self._dispatch_cpu_ns = None
        self._telemetry_wall_ns = None
        self._telemetry_cpu_ns = None
        self._finished_wall_ns = None
        self._finished_cpu_ns = None
        self._slot_started_wall_ns = self.wall_clock_ns()
        self._slot_started_cpu_ns = self.cpu_clock_ns()

    def begin_discovery(self):
        self._require_started()
        if self._discovery_started_wall_ns is not None:
            raise RuntimeError("control-plane discovery timing is already active")
        self._discovery_started_wall_ns = self.wall_clock_ns()
        self._discovery_started_cpu_ns = self.cpu_clock_ns()

    def end_discovery(self):
        if self._discovery_started_wall_ns is None:
            raise RuntimeError("control-plane discovery timing is not active")
        ended_wall_ns = self.wall_clock_ns()
        ended_cpu_ns = self.cpu_clock_ns()
        self._discovery_wall_ns += ended_wall_ns - self._discovery_started_wall_ns
        self._discovery_cpu_ns += ended_cpu_ns - self._discovery_started_cpu_ns
        self._discovery_started_wall_ns = None
        self._discovery_started_cpu_ns = None

    def mark_route_dispatch(self):
        self._require_started()
        self._dispatch_wall_ns = self.wall_clock_ns()
        self._dispatch_cpu_ns = self.cpu_clock_ns()

    def mark_telemetry_received(self):
        if self._dispatch_wall_ns is None:
            raise RuntimeError("route dispatch must precede telemetry")
        self._telemetry_wall_ns = self.wall_clock_ns()
        self._telemetry_cpu_ns = self.cpu_clock_ns()

    def finish_slot(self):
        if self._telemetry_wall_ns is None:
            raise RuntimeError("telemetry must precede control-plane completion")
        self._finished_wall_ns = self.wall_clock_ns()
        self._finished_cpu_ns = self.cpu_clock_ns()

    def record_exchange(
        self,
        *,
        request_field,
        response_field,
        request_payload_bytes,
        response_payload_bytes,
    ):
        if request_field not in self.payload_bytes:
            raise ValueError(f"unknown control-plane field: {request_field}")
        if response_field not in self.payload_bytes:
            raise ValueError(f"unknown control-plane field: {response_field}")
        if request_payload_bytes < 0 or response_payload_bytes < 0:
            raise ValueError("control-plane payload byte counts must be non-negative")
        self.payload_bytes[request_field] += int(request_payload_bytes)
        self.payload_bytes[response_field] += int(response_payload_bytes)
        self.messages[request_field] += 1
        self.messages[response_field] += 1

    def snapshot(self):
        if self._finished_wall_ns is None:
            raise RuntimeError("control-plane slot measurement is incomplete")
        admission_wall_ns = self._dispatch_wall_ns - self._slot_started_wall_ns
        feedback_wall_ns = self._finished_wall_ns - self._telemetry_wall_ns
        admission_cpu_ns = self._dispatch_cpu_ns - self._slot_started_cpu_ns
        feedback_cpu_ns = self._finished_cpu_ns - self._telemetry_cpu_ns
        payload = dict(self.payload_bytes)
        messages = dict(self.messages)
        payload["total"] = sum(payload.values())
        messages["total"] = sum(messages.values())
        snapshot = {
            "schema": CONTROL_PLANE_SCHEMA,
            "timing_ms": {
                "discovery": self._milliseconds(self._discovery_wall_ns),
                "admission": self._milliseconds(admission_wall_ns),
                "feedback": self._milliseconds(feedback_wall_ns),
                "active": self._milliseconds(
                    admission_wall_ns + feedback_wall_ns
                ),
                "data_plane_wait": self._milliseconds(
                    self._telemetry_wall_ns - self._dispatch_wall_ns
                ),
            },
            "cpu_ms": {
                "discovery": self._milliseconds(self._discovery_cpu_ns),
                "admission": self._milliseconds(admission_cpu_ns),
                "feedback": self._milliseconds(feedback_cpu_ns),
                "active": self._milliseconds(admission_cpu_ns + feedback_cpu_ns),
            },
            "payload_bytes": payload,
            "messages": messages,
        }
        return validate_control_plane_snapshot(snapshot)

    def _require_started(self):
        if self._slot_started_wall_ns is None:
            raise RuntimeError("control-plane slot measurement has not started")

    @staticmethod
    def _milliseconds(value_ns):
        return value_ns / 1_000_000.0
