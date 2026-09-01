"""Greedy-owned controller-boundary payload and wall-time measurement."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
import time
from typing import Callable, Mapping


GREEDY_CONTROL_PLANE_SCHEMA = "greedy-control-plane-wall-time-v1"
GREEDY_CONTROL_PLANE_TIMING_FIELDS = (
    "discovery",
    "admission",
    "feedback",
    "active",
    "data_plane_wait",
)
GREEDY_CONTROL_PLANE_DATA_FIELDS = (
    "kubernetes_discovery_tx",
    "kubernetes_discovery_rx",
    "route_command_tx",
    "selected_telemetry_rx",
    "belief_tx",
    "belief_rx",
)


def _counts(value: object, *, label: str) -> Mapping[str, int]:
    expected = {*GREEDY_CONTROL_PLANE_DATA_FIELDS, "total"}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"invalid Greedy control-plane {label} fields")
    for name in expected:
        item = value[name]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ValueError(
                f"Greedy control-plane {label}.{name} must be a nonnegative integer"
            )
    return value


def validate_greedy_control_plane_snapshot(
    snapshot: object,
) -> Mapping[str, object]:
    if not isinstance(snapshot, Mapping) or set(snapshot) != {
        "schema",
        "timing_ms",
        "payload_bytes",
        "messages",
    }:
        raise ValueError("invalid Greedy control-plane snapshot fields")
    if snapshot.get("schema") != GREEDY_CONTROL_PLANE_SCHEMA:
        raise ValueError("unsupported Greedy control-plane schema")
    timing = snapshot.get("timing_ms")
    if not isinstance(timing, Mapping) or set(timing) != set(
        GREEDY_CONTROL_PLANE_TIMING_FIELDS
    ):
        raise ValueError("invalid Greedy control-plane timing fields")
    for name in GREEDY_CONTROL_PLANE_TIMING_FIELDS:
        value = timing[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            or value < 0
        ):
            raise ValueError(f"control-plane timing {name} must be finite and nonnegative")
    payload = _counts(snapshot.get("payload_bytes"), label="payload_bytes")
    messages = _counts(snapshot.get("messages"), label="messages")
    if payload["total"] != sum(
        payload[name] for name in GREEDY_CONTROL_PLANE_DATA_FIELDS
    ):
        raise ValueError("Greedy control-plane payload total is inconsistent")
    if messages["total"] != sum(
        messages[name] for name in GREEDY_CONTROL_PLANE_DATA_FIELDS
    ):
        raise ValueError("Greedy control-plane message total is inconsistent")
    if timing["active"] != timing["admission"] + timing["feedback"]:
        raise ValueError("Greedy active time must equal admission plus feedback")
    if timing["discovery"] > timing["admission"]:
        raise ValueError("Greedy discovery time cannot exceed admission time")
    for name in (
        "kubernetes_discovery_tx",
        "kubernetes_discovery_rx",
        "route_command_tx",
        "selected_telemetry_rx",
    ):
        if messages[name] != 1:
            raise ValueError(f"Greedy control-plane {name} requires one message")
    for name in ("belief_tx", "belief_rx"):
        if payload[name] != 0 or messages[name] != 0:
            raise ValueError("Greedy beliefs are controller-local")
    return snapshot


@dataclass
class GreedyControlPlaneMeter:
    """Measure successful application bodies and monotonic phase wall time."""

    wall_clock_ns: Callable[[], int] = time.perf_counter_ns
    payload_bytes: dict[str, int] = field(default_factory=dict)
    messages: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._active = False
        self._slot_started_ns: int | None = None
        self._discovery_started_ns: int | None = None
        self._discovery_elapsed_ns = 0
        self._route_dispatched_ns: int | None = None
        self._telemetry_received_ns: int | None = None
        self._reset_counts()

    def _reset_counts(self) -> None:
        self.payload_bytes = {name: 0 for name in GREEDY_CONTROL_PLANE_DATA_FIELDS}
        self.messages = {name: 0 for name in GREEDY_CONTROL_PLANE_DATA_FIELDS}

    def begin_slot(self) -> None:
        self._reset_counts()
        self._slot_started_ns = self.wall_clock_ns()
        self._discovery_started_ns = None
        self._discovery_elapsed_ns = 0
        self._route_dispatched_ns = None
        self._telemetry_received_ns = None
        self._active = True

    def begin_discovery(self) -> None:
        self._require_active()
        if self._discovery_started_ns is not None:
            raise RuntimeError("Greedy discovery timing is already active")
        self._discovery_started_ns = self.wall_clock_ns()

    def end_discovery(self) -> None:
        if self._discovery_started_ns is None:
            raise RuntimeError("Greedy discovery timing is not active")
        ended = self.wall_clock_ns()
        if ended < self._discovery_started_ns:
            raise RuntimeError("Greedy control-plane clock moved backwards")
        self._discovery_elapsed_ns += ended - self._discovery_started_ns
        self._discovery_started_ns = None

    def mark_route_dispatch(self) -> None:
        self._require_active()
        if self._discovery_started_ns is not None or self._route_dispatched_ns is not None:
            raise RuntimeError("Greedy route dispatch timing is invalid")
        self._route_dispatched_ns = self.wall_clock_ns()

    def mark_telemetry_received(self) -> None:
        self._require_active()
        if self._route_dispatched_ns is None or self._telemetry_received_ns is not None:
            raise RuntimeError("Greedy telemetry timing is invalid")
        self._telemetry_received_ns = self.wall_clock_ns()

    def record_exchange(
        self,
        *,
        request_field: str,
        response_field: str,
        request_payload_bytes: int,
        response_payload_bytes: int,
    ) -> None:
        self._require_active()
        for name in (request_field, response_field):
            if name not in self.payload_bytes:
                raise ValueError(f"unknown Greedy control-plane field: {name}")
        for value in (request_payload_bytes, response_payload_bytes):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("Greedy payload byte counts must be nonnegative integers")
        self.payload_bytes[request_field] += request_payload_bytes
        self.payload_bytes[response_field] += response_payload_bytes
        self.messages[request_field] += 1
        self.messages[response_field] += 1

    def finish_slot(self) -> Mapping[str, object]:
        self._require_active()
        if (
            self._slot_started_ns is None
            or self._route_dispatched_ns is None
            or self._telemetry_received_ns is None
        ):
            raise RuntimeError("Greedy control-plane timing is incomplete")
        finished = self.wall_clock_ns()
        if not (
            self._slot_started_ns
            <= self._route_dispatched_ns
            <= self._telemetry_received_ns
            <= finished
        ):
            raise RuntimeError("Greedy control-plane clock moved backwards")
        admission = self._route_dispatched_ns - self._slot_started_ns
        wait = self._telemetry_received_ns - self._route_dispatched_ns
        feedback = finished - self._telemetry_received_ns
        admission_ms = admission / 1_000_000.0
        feedback_ms = feedback / 1_000_000.0
        payload = dict(self.payload_bytes)
        messages = dict(self.messages)
        payload["total"] = sum(payload.values())
        messages["total"] = sum(messages.values())
        self._active = False
        snapshot = {
            "schema": GREEDY_CONTROL_PLANE_SCHEMA,
            "timing_ms": {
                "discovery": self._discovery_elapsed_ns / 1_000_000.0,
                "admission": admission_ms,
                "feedback": feedback_ms,
                "active": admission_ms + feedback_ms,
                "data_plane_wait": wait / 1_000_000.0,
            },
            "payload_bytes": payload,
            "messages": messages,
        }
        return validate_greedy_control_plane_snapshot(snapshot)

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError("Greedy control-plane slot measurement is not active")
