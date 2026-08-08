"""Hybrid-owned ASGI entry point around the frozen Exact forwarder service."""

from __future__ import annotations

from testbed.route_forwarder import ForwarderConfig, create_app as create_exact_app

from .kernel_route_forwarder import HybridKernelRouteForwarder


HYBRID_KERNEL_FORWARDER_SERVICE_VERSION = (
    "ibg-hybrid-kernel-route-forwarder-service-v1"
)


def create_app(runtime: HybridKernelRouteForwarder | None = None):
    selected_runtime = runtime or HybridKernelRouteForwarder(
        ForwarderConfig.from_env()
    )
    return create_exact_app(runtime=selected_runtime)


app = create_app()

