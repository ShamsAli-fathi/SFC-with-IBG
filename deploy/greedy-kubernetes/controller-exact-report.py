"""Lean controller-image copy of the frozen strict SLA helper."""


def SLA_v(end_to_end_latency_ms_per_flow, threshold_ms):
    if threshold_ms <= 0:
        raise ValueError("SLA latency threshold must be positive")
    return sum(
        latency_ms > threshold_ms
        for latency_ms in end_to_end_latency_ms_per_flow.values()
    )
