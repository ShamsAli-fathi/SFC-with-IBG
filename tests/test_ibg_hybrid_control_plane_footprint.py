from copy import deepcopy

import pytest

from IBG.control_plane import MESSAGE_FIELDS, PAYLOAD_FIELDS
from IBG_Hybrid.control_plane_footprint import (
    HYBRID_CONTROL_PLANE_MESSAGE_FIELDS,
    HYBRID_CONTROL_PLANE_PAYLOAD_FIELDS,
    HYBRID_CONTROL_PLANE_DATA_SCHEMA,
    HybridControlPlaneDataMeter,
    validate_hybrid_control_plane_data_snapshot,
)


def _snapshot():
    meter = HybridControlPlaneDataMeter()
    meter.begin_slot()
    meter.record_exchange(
        request_field="kubernetes_discovery_tx",
        response_field="kubernetes_discovery_rx",
        request_payload_bytes=0,
        response_payload_bytes=120,
    )
    meter.record_exchange(
        request_field="route_command_tx",
        response_field="selected_telemetry_rx",
        request_payload_bytes=80,
        response_payload_bytes=220,
    )
    return meter.finish_slot()


def test_data_meter_matches_exact_categories_without_timing_or_cpu():
    snapshot = _snapshot()

    assert snapshot == {
        "schema": HYBRID_CONTROL_PLANE_DATA_SCHEMA,
        "payload_bytes": {
            "kubernetes_discovery_tx": 0,
            "kubernetes_discovery_rx": 120,
            "route_command_tx": 80,
            "selected_telemetry_rx": 220,
            "belief_tx": 0,
            "belief_rx": 0,
            "total": 420,
        },
        "messages": {
            "kubernetes_discovery_tx": 1,
            "kubernetes_discovery_rx": 1,
            "route_command_tx": 1,
            "selected_telemetry_rx": 1,
            "belief_tx": 0,
            "belief_rx": 0,
            "total": 4,
        },
    }
    assert "timing_ms" not in snapshot
    assert "cpu_ms" not in snapshot


def test_data_only_categories_match_frozen_exact_control_plane_v1():
    assert HYBRID_CONTROL_PLANE_PAYLOAD_FIELDS == PAYLOAD_FIELDS
    assert HYBRID_CONTROL_PLANE_MESSAGE_FIELDS == MESSAGE_FIELDS


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["payload_bytes"].__setitem__("total", 419),
        lambda value: value["messages"].__setitem__("total", 5),
        lambda value: value["messages"].__setitem__("kubernetes_discovery_tx", 2),
        lambda value: value["payload_bytes"].__setitem__("belief_tx", 1),
        lambda value: value["messages"].__setitem__("belief_rx", 1),
    ],
)
def test_data_snapshot_rejects_incorrect_totals_messages_and_belief_exchange(mutate):
    snapshot = deepcopy(_snapshot())
    mutate(snapshot)

    with pytest.raises(ValueError):
        validate_hybrid_control_plane_data_snapshot(snapshot)


def test_data_meter_resets_between_slots_and_requires_complete_exchange():
    meter = HybridControlPlaneDataMeter()
    meter.begin_slot()
    meter.record_exchange(
        request_field="kubernetes_discovery_tx",
        response_field="kubernetes_discovery_rx",
        request_payload_bytes=0,
        response_payload_bytes=1,
    )
    with pytest.raises(ValueError, match="route_command_tx"):
        meter.finish_slot()

    meter.begin_slot()
    meter.record_exchange(
        request_field="kubernetes_discovery_tx",
        response_field="kubernetes_discovery_rx",
        request_payload_bytes=0,
        response_payload_bytes=2,
    )
    meter.record_exchange(
        request_field="route_command_tx",
        response_field="selected_telemetry_rx",
        request_payload_bytes=3,
        response_payload_bytes=4,
    )
    assert meter.finish_slot()["payload_bytes"]["total"] == 9
