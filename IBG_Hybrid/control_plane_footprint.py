"""Observed Hybrid controller-boundary payload and message accounting.

The category names and application-body byte boundary match IBG-Exact's
``control_plane_v1`` contract.  Hybrid intentionally exposes a data-only
schema: it does not sample wall time, CPU time, memory, cgroups, or wire bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


HYBRID_CONTROL_PLANE_DATA_SCHEMA = "ibg-hybrid-control-plane-data-v1"
HYBRID_CONTROL_PLANE_DATA_ENV = "HYBRID_CONTROL_PLANE_FOOTPRINT"
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


def validate_hybrid_control_plane_data_snapshot(
    snapshot: object,
) -> Mapping[str, object]:
    """Validate one completed Hybrid aggregate-discovery/route exchange."""

    if not isinstance(snapshot, Mapping) or set(snapshot) != {
        "schema",
        "payload_bytes",
        "messages",
    }:
        raise ValueError("invalid Hybrid control-plane data snapshot fields")
    if snapshot.get("schema") != HYBRID_CONTROL_PLANE_DATA_SCHEMA:
        raise ValueError("unsupported Hybrid control-plane data schema")
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
    """Count successful application-body exchanges for one slot at a time."""

    payload_bytes: dict[str, int] = field(default_factory=dict)
    messages: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._active = False
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
        self._active = True

    def record_exchange(
        self,
        *,
        request_field: str,
        response_field: str,
        request_payload_bytes: int,
        response_payload_bytes: int,
    ) -> None:
        if not self._active:
            raise RuntimeError("Hybrid control-plane slot measurement is not active")
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
        if not self._active:
            raise RuntimeError("Hybrid control-plane slot measurement is not active")
        self._active = False
        payload = dict(self.payload_bytes)
        messages = dict(self.messages)
        payload["total"] = sum(payload.values())
        messages["total"] = sum(messages.values())
        snapshot = {
            "schema": HYBRID_CONTROL_PLANE_DATA_SCHEMA,
            "payload_bytes": payload,
            "messages": messages,
        }
        return validate_hybrid_control_plane_data_snapshot(snapshot)
