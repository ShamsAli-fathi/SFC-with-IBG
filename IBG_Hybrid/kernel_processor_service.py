"""Hybrid-owned HTTP entry point around the frozen Exact processor runtime."""

from __future__ import annotations

import os
import re
from typing import Mapping

from testbed.cnf_service import ReplicaConfig, create_app as create_exact_app

from .contracts import ReplicaChoice
from .kernel_runtime_profiles import load_runtime_profile_document


HYBRID_KERNEL_PROCESSOR_SERVICE_VERSION = "ibg-hybrid-kernel-processor-service-v1"


def processor_config_from_env(
    environ: Mapping[str, str] | None = None,
) -> ReplicaConfig:
    values = os.environ if environ is None else environ
    stage = int(values.get("STAGE", "1"))
    pod_name = values.get("POD_NAME", f"hybrid-stage-{stage}-0")
    ordinal = re.search(r"-(\d+)$", pod_name)
    if ordinal is None:
        raise ValueError("POD_NAME must end in a StatefulSet ordinal")
    replica_id = int(ordinal.group(1)) + 1
    path = values.get("HYBRID_RUNTIME_PROFILES_PATH")
    if path is None:
        return ReplicaConfig(
            stage=stage,
            replica_id=replica_id,
            pod_name=pod_name,
        )
    document = load_runtime_profile_document(path)
    try:
        profile = document.profile_by_choice()[ReplicaChoice(stage, replica_id)]
    except KeyError as error:
        raise ValueError(
            f"missing Hybrid runtime profile for stage {stage} replica {replica_id}"
        ) from error
    return ReplicaConfig(
        stage=stage,
        replica_id=replica_id,
        pod_name=pod_name,
        state=profile.hidden_state,
        # The frozen processor does not enforce this compatibility value.
        # Hybrid assigned-flow admission remains controller-only.
        capacity=1,
        observation_seed=profile.observation_seed,
    )


def create_app(config: ReplicaConfig | None = None):
    return create_exact_app(config or processor_config_from_env())


app = create_app()

