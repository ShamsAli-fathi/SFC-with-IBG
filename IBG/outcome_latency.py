"""Select the latency basis used for reported outcome utility and SLA."""

PHYSICAL_ONLY_OUTCOME_LATENCY_MODE = "physical-only-v1"
PHYSICAL_PLUS_PAIR_OUTCOME_LATENCY_MODE = "physical-plus-pair-v1"
OUTCOME_LATENCY_MODES = frozenset(
    {
        PHYSICAL_ONLY_OUTCOME_LATENCY_MODE,
        PHYSICAL_PLUS_PAIR_OUTCOME_LATENCY_MODE,
    }
)
DEFAULT_OUTCOME_LATENCY_MODE = PHYSICAL_ONLY_OUTCOME_LATENCY_MODE


def require_outcome_latency_mode(mode):
    if mode not in OUTCOME_LATENCY_MODES:
        raise ValueError(
            "outcome latency mode must be one of "
            f"{sorted(OUTCOME_LATENCY_MODES)}"
        )
    return mode


def outcome_latency_ms_per_flow(
    physical_latency_ms_per_flow,
    link_latency_ms_per_flow,
    mode=DEFAULT_OUTCOME_LATENCY_MODE,
):
    """Return the selected reporting/SLA latency without discarding raw data."""
    mode = require_outcome_latency_mode(mode)
    physical_flows = set(physical_latency_ms_per_flow)
    link_flows = set(link_latency_ms_per_flow)
    if physical_flows != link_flows:
        raise ValueError("physical and pair latency flows must match")
    if mode == PHYSICAL_ONLY_OUTCOME_LATENCY_MODE:
        return {
            flow: float(physical_latency_ms_per_flow[flow])
            for flow in physical_latency_ms_per_flow
        }
    return {
        flow: float(physical_latency_ms_per_flow[flow])
        + float(link_latency_ms_per_flow[flow])
        for flow in physical_latency_ms_per_flow
    }
