"""Greedy-owned arbitrary-K continuation rule over the shared forwarder."""

from __future__ import annotations

from testbed.route_forwarder import (
    ForwarderConfig,
    ReplicaRouteForwarder,
    RouteForwardingError,
    RouteProcessRequest,
)

from .kernel_contracts import GreedyClientLifecycle


GREEDY_KERNEL_FORWARDER_VERSION = "greedy-two-selected-stage-forwarder-v1"


class GreedyKernelRouteForwarder(ReplicaRouteForwarder):
    """Execute only a preselected optional second hop at a later stage."""

    def __init__(self, config: ForwarderConfig, **kwargs) -> None:
        super().__init__(config, **kwargs)
        self._greedy_closed = False
        self._processor_close_calls = 0
        self._downstream_close_calls = 0
        if self.processor_client is self.client:
            raise RuntimeError("local processor and downstream clients must be separate")

    @property
    def client_lifecycles(self) -> tuple[GreedyClientLifecycle, GreedyClientLifecycle]:
        return (
            GreedyClientLifecycle(
                owner="public-forwarder-local-private-processor",
                scope="forwarder-lifespan-processor-compatible-default-idle-window",
                client_instances=1,
                close_calls=self._processor_close_calls,
                closed=self.processor_client.is_closed,
            ),
            GreedyClientLifecycle(
                owner="public-forwarder-downstream-forwarder",
                scope="forwarder-lifespan-30-second-keepalive",
                client_instances=1,
                close_calls=self._downstream_close_calls,
                closed=self.client.is_closed,
            ),
        )

    async def close(self) -> None:
        if self._greedy_closed:
            return
        self._greedy_closed = True
        first_error: Exception | None = None
        if not self.processor_client.is_closed:
            try:
                await self.processor_client.aclose()
                self._processor_close_calls += 1
            except Exception as error:  # pragma: no cover - defensive ownership path
                first_error = error
        if not self.client.is_closed:
            try:
                await self.client.aclose()
                self._downstream_close_calls += 1
            except Exception as error:  # pragma: no cover - defensive ownership path
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error

    def _validate_next_hop(self, request: RouteProcessRequest) -> None:
        if not request.remaining_hops:
            return
        if len(request.remaining_hops) != 1:
            raise RouteForwardingError(
                "Greedy L=2 forwarding requires exactly one remaining hop"
            )
        next_stage = request.remaining_hops[0].stage
        if next_stage <= self.config.stage:
            raise RouteForwardingError(
                "Greedy selected next stage must be strictly later than "
                f"{self.config.stage}, got {next_stage}"
            )
