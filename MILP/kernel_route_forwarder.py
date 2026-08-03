"""MILP-only public forwarder for one selected directed stage pair.

The implementation reuses the Exact forwarder's processor, HTTP, telemetry,
timing, cgroup, and lifecycle code.  Only continuation validation differs:
MILP permits one strictly later selected stage rather than requiring the next
contiguous stage in a complete chain.
"""

from __future__ import annotations

import httpx

from testbed.route_forwarder import (
    ForwarderConfig,
    ReplicaRouteForwarder,
    RouteForwardingError,
    RouteProcessRequest,
    create_app as create_exact_forwarder_app,
)


MILP_KERNEL_FORWARDER_VERSION = "milp-kernel-two-stage-forwarder-v1"


class MILPKernelRouteForwarder(ReplicaRouteForwarder):
    """Execute at most one strictly later selected MILP hop."""

    def _validate_next_hop(self, request: RouteProcessRequest) -> None:
        if not request.remaining_hops:
            return
        if len(request.remaining_hops) != 1:
            raise RouteForwardingError(
                "MILP two-stage forwarding requires exactly one remaining hop"
            )
        next_stage = request.remaining_hops[0].stage
        if next_stage <= self.config.stage:
            raise RouteForwardingError(
                "MILP selected next stage must be strictly later than "
                f"{self.config.stage}, got {next_stage}"
            )


def create_app(
    config: ForwarderConfig | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
):
    runtime = MILPKernelRouteForwarder(
        config or ForwarderConfig.from_env(),
        transport=transport,
    )
    application = create_exact_forwarder_app(runtime=runtime)
    application.title = "MILP Two-Selected-Stage Route Forwarder"
    application.version = MILP_KERNEL_FORWARDER_VERSION
    return application


app = create_app()
