"""Hybrid-only two-selected-stage continuation rule for frozen forwarders."""

from __future__ import annotations

from testbed.route_forwarder import (
    ReplicaRouteForwarder,
    RouteForwardingError,
    RouteProcessRequest,
)


HYBRID_KERNEL_FORWARDER_VERSION = "ibg-hybrid-two-selected-stage-forwarder-v1"


class HybridKernelRouteForwarder(ReplicaRouteForwarder):
    """Permit one strictly later selected stage, including noncontiguous hops."""

    def _validate_next_hop(self, request: RouteProcessRequest) -> None:
        if not 1 <= self.config.stage <= 3:
            raise RouteForwardingError(
                "Hybrid forwarder stage must be within the active three-stage SFC"
            )
        if not request.remaining_hops:
            return
        if len(request.remaining_hops) != 1:
            raise RouteForwardingError(
                "Hybrid L=2 forwarding requires exactly one remaining hop"
            )
        next_stage = request.remaining_hops[0].stage
        if next_stage > 3:
            raise RouteForwardingError(
                "Hybrid selected next stage must be within the three-stage SFC"
            )
        if next_stage <= self.config.stage:
            raise RouteForwardingError(
                "Hybrid selected next stage must be strictly later than "
                f"{self.config.stage}, got {next_stage}"
            )
