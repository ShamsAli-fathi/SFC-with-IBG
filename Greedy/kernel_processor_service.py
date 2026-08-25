"""Greedy ASGI entry point around the policy-neutral private processor."""

from __future__ import annotations

from collections.abc import Mapping
import os
import re

from testbed.cnf_service import (
    LatencySource,
    ObservationJitterCallable,
    ReplicaConfig,
    create_app as create_shared_app,
)

from .contracts import ReplicaIdentity
from .kernel_runtime_profiles import load_runtime_profile_document


GREEDY_KERNEL_PROCESSOR_SERVICE_VERSION = "greedy-kernel-processor-service-v1"


def processor_config_from_env(
    environ: Mapping[str, str] | None = None,
) -> ReplicaConfig:
    """Read hidden runtime values only inside the private processor boundary."""
    values = os.environ if environ is None else environ
    stage = int(values.get("STAGE", "1"))
    pod_name = values.get("POD_NAME", f"greedy-stage-{stage}-0")
    ordinal = re.search(r"-(\d+)$", pod_name)
    if ordinal is None:
        raise ValueError("POD_NAME must end in a StatefulSet ordinal")
    replica_id = int(ordinal.group(1)) + 1
    path = values.get("GREEDY_RUNTIME_PROFILES_PATH")
    if path is None:
        return ReplicaConfig(
            stage=stage,
            replica_id=replica_id,
            pod_name=pod_name,
        )
    document = load_runtime_profile_document(path)
    try:
        profile = document.profile_by_identity()[
            ReplicaIdentity(stage, replica_id)
        ]
    except KeyError as error:
        raise ValueError(
            f"missing Greedy runtime profile for stage {stage} replica {replica_id}"
        ) from error
    return ReplicaConfig(
        stage=stage,
        replica_id=replica_id,
        pod_name=pod_name,
        state=profile.hidden_state,
        # Admission is controller-owned; the processor does not enforce it.
        capacity=1,
        observation_seed=profile.observation_seed,
    )


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
