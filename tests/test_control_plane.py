import pytest

from control_plane import (
    CONTROL_PLANE_SCHEMA,
    ControlPlaneMeter,
    validate_control_plane_snapshot,
)


class ManualClock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        return self.value

    def advance_ms(self, milliseconds):
        self.value += int(milliseconds * 1_000_000)


def test_control_plane_snapshot_separates_active_work_from_route_wait():
    wall = ManualClock()
    cpu = ManualClock()
    meter = ControlPlaneMeter(wall_clock_ns=wall, cpu_clock_ns=cpu)

    meter.begin_slot()
    meter.begin_discovery()
    wall.advance_ms(2)
    cpu.advance_ms(1)
    meter.end_discovery()
    wall.advance_ms(3)
    cpu.advance_ms(2)
    meter.mark_route_dispatch()
    wall.advance_ms(7)
    cpu.advance_ms(0.5)
    meter.mark_telemetry_received()
    wall.advance_ms(2)
    cpu.advance_ms(1)
    meter.finish_slot()

    snapshot = meter.snapshot()

    assert snapshot["schema"] == CONTROL_PLANE_SCHEMA
    assert snapshot["timing_ms"] == {
        "discovery": 2.0,
        "admission": 5.0,
        "feedback": 2.0,
        "active": 7.0,
        "data_plane_wait": 7.0,
    }
    assert snapshot["cpu_ms"] == {
        "discovery": 1.0,
        "admission": 3.0,
        "feedback": 1.0,
        "active": 4.0,
    }
    assert snapshot["timing_ms"]["active"] == pytest.approx(
        snapshot["timing_ms"]["admission"]
        + snapshot["timing_ms"]["feedback"]
    )


def test_control_plane_payload_and_message_totals_are_deterministic():
    wall = ManualClock()
    cpu = ManualClock()
    meter = ControlPlaneMeter(wall_clock_ns=wall, cpu_clock_ns=cpu)

    meter.begin_slot()
    meter.record_exchange(
        request_field="kubernetes_discovery_tx",
        response_field="kubernetes_discovery_rx",
        request_payload_bytes=0,
        response_payload_bytes=100,
    )
    meter.record_exchange(
        request_field="route_command_tx",
        response_field="selected_telemetry_rx",
        request_payload_bytes=50,
        response_payload_bytes=200,
    )
    meter.mark_route_dispatch()
    meter.mark_telemetry_received()
    meter.finish_slot()

    snapshot = meter.snapshot()

    assert snapshot["payload_bytes"] == {
        "kubernetes_discovery_tx": 0,
        "kubernetes_discovery_rx": 100,
        "route_command_tx": 50,
        "selected_telemetry_rx": 200,
        "belief_tx": 0,
        "belief_rx": 0,
        "total": 350,
    }
    assert snapshot["messages"] == {
        "kubernetes_discovery_tx": 1,
        "kubernetes_discovery_rx": 1,
        "route_command_tx": 1,
        "selected_telemetry_rx": 1,
        "belief_tx": 0,
        "belief_rx": 0,
        "total": 4,
    }


def test_control_plane_validation_rejects_route_message_inflation():
    wall = ManualClock()
    cpu = ManualClock()
    meter = ControlPlaneMeter(wall_clock_ns=wall, cpu_clock_ns=cpu)
    meter.begin_slot()
    for _ in range(3):
        meter.record_exchange(
            request_field="kubernetes_discovery_tx",
            response_field="kubernetes_discovery_rx",
            request_payload_bytes=0,
            response_payload_bytes=100,
        )
    meter.record_exchange(
        request_field="route_command_tx",
        response_field="selected_telemetry_rx",
        request_payload_bytes=50,
        response_payload_bytes=200,
    )
    meter.mark_route_dispatch()
    meter.mark_telemetry_received()
    meter.finish_slot()
    snapshot = meter.snapshot()

    validate_control_plane_snapshot(snapshot, expected_stages=3)
    snapshot["messages"]["route_command_tx"] = 3
    snapshot["messages"]["total"] = sum(
        value
        for name, value in snapshot["messages"].items()
        if name != "total"
    )

    with pytest.raises(ValueError, match="one route command"):
        validate_control_plane_snapshot(snapshot, expected_stages=3)
