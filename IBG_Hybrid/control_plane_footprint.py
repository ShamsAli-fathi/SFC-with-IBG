"""Observed Hybrid controller-boundary data and wall-time accounting.

The category names and application-body byte boundary match IBG-Exact's
``control_plane_v1`` contract. Hybrid adds monotonic phase wall times while
intentionally excluding CPU time, memory, cgroups, and wire bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
import time
from typing import Callable, Mapping


HYBRID_CONTROL_PLANE_DATA_SCHEMA = "ibg-hybrid-control-plane-wall-time-v2"
HYBRID_CONTROL_PLANE_DATA_ENV = "HYBRID_CONTROL_PLANE_FOOTPRINT"
HYBRID_CONTROL_PLANE_TIMING_FIELDS = (
    "discovery",
    "admission",
    "feedback",
    "active",
    "data_plane_wait",
)
HYBRID_CONTROL_PLANE_PAYLOAD_FIELDS = (
    "kubernetes_discovery_tx",
    "kubernetes_discovery_rx",
    "route_command_tx",
    "selected_telemetry_rx",
    "belief_tx",
    "belief_rx",
)
HYBRID_CONTROL_PLANE_MESSAGE_FIELDS = HYBRID_CONTROL_PLANE_PAYLOAD_FIELDS


def _require_counts(
    document: object,
    fields: tuple[str, ...],
    label: str,
) -> Mapping[str, int]:
    if not isinstance(document, Mapping) or set(document) != {*fields, "total"}:
        raise ValueError(f"invalid Hybrid control-plane {label} fields")
    for name in (*fields, "total"):
        value = document[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"Hybrid control-plane {label}.{name} must be a "
                "non-negative integer"
            )
    return document


def _require_timing(document: object) -> Mapping[str, float]:
    if not isinstance(document, Mapping) or set(document) != set(
        HYBRID_CONTROL_PLANE_TIMING_FIELDS
    ):
        raise ValueError("invalid Hybrid control-plane timing_ms fields")
    for name in HYBRID_CONTROL_PLANE_TIMING_FIELDS:
        value = document[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            or value < 0
        ):
            raise ValueError(
                f"Hybrid control-plane timing_ms.{name} must be finite and "
                "non-negative"
            )
    return document


def validate_hybrid_control_plane_data_snapshot(
    snapshot: object,
) -> Mapping[str, object]:
    """Validate one completed Hybrid aggregate-discovery/route exchange."""

    if not isinstance(snapshot, Mapping) or set(snapshot) != {
        "schema",
        "timing_ms",
        "payload_bytes",
        "messages",
    }:
        raise ValueError("invalid Hybrid control-plane data snapshot fields")
    if snapshot.get("schema") != HYBRID_CONTROL_PLANE_DATA_SCHEMA:
        raise ValueError("unsupported Hybrid control-plane data schema")
    timing = _require_timing(snapshot.get("timing_ms"))
    payload = _require_counts(
        snapshot.get("payload_bytes"),
        HYBRID_CONTROL_PLANE_PAYLOAD_FIELDS,
        "payload_bytes",
    )
    messages = _require_counts(
        snapshot.get("messages"),
        HYBRID_CONTROL_PLANE_MESSAGE_FIELDS,
        "messages",
    )
    if payload["total"] != sum(
        payload[name] for name in HYBRID_CONTROL_PLANE_PAYLOAD_FIELDS
    ):
        raise ValueError("Hybrid control-plane payload total does not match components")
    if messages["total"] != sum(
        messages[name] for name in HYBRID_CONTROL_PLANE_MESSAGE_FIELDS
    ):
        raise ValueError("Hybrid control-plane message total does not match components")
    if timing["active"] != timing["admission"] + timing["feedback"]:
        raise ValueError(
            "Hybrid control-plane active time does not match admission plus feedback"
        )
    if timing["discovery"] > timing["admission"]:
        raise ValueError(
            "Hybrid control-plane discovery time exceeds admission time"
        )
    for field in (
        "kubernetes_discovery_tx",
        "kubernetes_discovery_rx",
        "route_command_tx",
        "selected_telemetry_rx",
    ):
        if messages[field] != 1:
            raise ValueError(
                f"Hybrid control-plane {field} must contain exactly one message"
            )
    for field in ("belief_tx", "belief_rx"):
        if payload[field] != 0 or messages[field] != 0:
            raise ValueError(
                "Hybrid beliefs are controller-local and must have zero observed "
                "exchange"
            )
    return snapshot


@dataclass
class HybridControlPlaneDataMeter:
    """Measure successful application data and phase wall time for one slot."""

    wall_clock_ns: Callable[[], int] = time.perf_counter_ns
    payload_bytes: dict[str, int] = field(default_factory=dict)
    messages: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._active = False
        self._slot_started_ns = None
        self._discovery_started_ns = None
        self._discovery_elapsed_ns = 0
        self._route_dispatched_ns = None
        self._telemetry_received_ns = None
        self._reset_counts()

    def _reset_counts(self) -> None:
        self.payload_bytes = {
            name: 0 for name in HYBRID_CONTROL_PLANE_PAYLOAD_FIELDS
        }
        self.messages = {
            name: 0 for name in HYBRID_CONTROL_PLANE_MESSAGE_FIELDS
        }

    def begin_slot(self) -> None:
        self._reset_counts()
        self._discovery_started_ns = None
        self._discovery_elapsed_ns = 0
        self._route_dispatched_ns = None
        self._telemetry_received_ns = None
        self._slot_started_ns = self.wall_clock_ns()
        self._active = True

    def begin_discovery(self) -> None:
        self._require_active()
        if self._discovery_started_ns is not None:
            raise RuntimeError("Hybrid control-plane discovery is already active")
        self._discovery_started_ns = self.wall_clock_ns()

    def end_discovery(self) -> None:
        if self._discovery_started_ns is None:
            raise RuntimeError("Hybrid control-plane discovery is not active")
        ended_ns = self.wall_clock_ns()
        if ended_ns < self._discovery_started_ns:
            raise RuntimeError("Hybrid control-plane wall clock moved backwards")
        self._discovery_elapsed_ns += ended_ns - self._discovery_started_ns
        self._discovery_started_ns = None

    def mark_route_dispatch(self) -> None:
        self._require_active()
        if self._discovery_started_ns is not None:
            raise RuntimeError("Hybrid discovery must finish before route dispatch")
        if self._route_dispatched_ns is not None:
            raise RuntimeError("Hybrid route dispatch is already recorded")
        self._route_dispatched_ns = self.wall_clock_ns()

    def mark_telemetry_received(self) -> None:
        self._require_active()
        if self._route_dispatched_ns is None:
            raise RuntimeError("Hybrid route dispatch must precede telemetry")
        if self._telemetry_received_ns is not None:
            raise RuntimeError("Hybrid telemetry receipt is already recorded")
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
        if request_field not in self.payload_bytes:
            raise ValueError(f"unknown Hybrid control-plane field: {request_field}")
        if response_field not in self.payload_bytes:
            raise ValueError(f"unknown Hybrid control-plane field: {response_field}")
        for value in (request_payload_bytes, response_payload_bytes):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(
                    "Hybrid control-plane payload byte counts must be "
                    "non-negative integers"
                )
        self.payload_bytes[request_field] += request_payload_bytes
        self.payload_bytes[response_field] += response_payload_bytes
        self.messages[request_field] += 1
        self.messages[response_field] += 1

    def finish_slot(self) -> Mapping[str, object]:
        self._require_active()
        if self._slot_started_ns is None or self._route_dispatched_ns is None:
            raise RuntimeError("Hybrid control-plane admission timing is incomplete")
        if self._telemetry_received_ns is None:
            raise RuntimeError("Hybrid control-plane telemetry timing is incomplete")
        finished_ns = self.wall_clock_ns()
        timestamps = (
            self._slot_started_ns,
            self._route_dispatched_ns,
            self._telemetry_received_ns,
            finished_ns,
        )
        if list(timestamps) != sorted(timestamps):
            raise RuntimeError("Hybrid control-plane wall clock moved backwards")
        self._active = False
        admission_ns = self._route_dispatched_ns - self._slot_started_ns
        data_plane_wait_ns = (
            self._telemetry_received_ns - self._route_dispatched_ns
        )
        feedback_ns = finished_ns - self._telemetry_received_ns
        admission_ms = self._milliseconds(admission_ns)
        feedback_ms = self._milliseconds(feedback_ns)
        payload = dict(self.payload_bytes)
        messages = dict(self.messages)
        payload["total"] = sum(payload.values())
        messages["total"] = sum(messages.values())
        snapshot = {
            "schema": HYBRID_CONTROL_PLANE_DATA_SCHEMA,
            "timing_ms": {
                "discovery": self._milliseconds(self._discovery_elapsed_ns),
                "admission": admission_ms,
                "feedback": feedback_ms,
                "active": admission_ms + feedback_ms,
                "data_plane_wait": self._milliseconds(data_plane_wait_ns),
            },
            "payload_bytes": payload,
            "messages": messages,
        }
        return validate_hybrid_control_plane_data_snapshot(snapshot)

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError("Hybrid control-plane slot measurement is not active")

    @staticmethod
    def _milliseconds(value_ns: int) -> float:
        return value_ns / 1_000_000.0
