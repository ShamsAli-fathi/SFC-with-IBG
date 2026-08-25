"""Greedy ASGI entry point around the policy-neutral private processor."""

from __future__ import annotations

from collections.abc import Mapping

from testbed.cnf_service import (
    LatencySource,
    ObservationJitterCallable,
    ReplicaConfig,
    create_app as create_shared_app,
)


GREEDY_KERNEL_PROCESSOR_SERVICE_VERSION = "greedy-kernel-processor-service-v1"


def processor_config_from_env(
    environ: Mapping[str, str] | None = None,
) -> ReplicaConfig:
    """Read hidden runtime values only inside the private processor boundary."""

    return ReplicaConfig.from_env(environ)


def create_app(
    config: ReplicaConfig | None = None,
    observation_source: LatencySource | None = None,
    observation_jitter_source: ObservationJitterCallable | None = None,
):
    return create_shared_app(
        config or processor_config_from_env(),
        observation_source=observation_source,
        observation_jitter_source=observation_jitter_source,
    )


app = create_app()
