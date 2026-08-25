"""Greedy ASGI entry point around the policy-neutral shared forwarder service."""

from __future__ import annotations

from testbed.route_forwarder import ForwarderConfig, create_app as create_shared_app

from .kernel_route_forwarder import GreedyKernelRouteForwarder


GREEDY_KERNEL_FORWARDER_SERVICE_VERSION = "greedy-kernel-forwarder-service-v1"


def create_app(runtime: GreedyKernelRouteForwarder | None = None):
    selected = runtime or GreedyKernelRouteForwarder(ForwarderConfig.from_env())
    return create_shared_app(runtime=selected)


app = create_app()
