"""MILP-owned deterministic processor-profile configuration.

These profiles configure the shared lightweight processor service only.  Their
legacy capacity, delay, cost, and gamma fields are compatibility metadata for
that service; MILP admission capacity is defined separately by the canonical
experiment profile in assigned flows per slot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path


@dataclass(frozen=True)
class MILPRuntimeReplicaProfile:
    state: int
    capacity: int
    delay: float
    cost: float
    gamma: float
    base_delay_ms: float
    congestion_delay_ms: float
    observation_seed: int | None = None

    def __post_init__(self) -> None:
        if self.state not in (1, 2, 3, 4):
            raise ValueError("profile state must be one of 1, 2, 3, or 4")
        if self.capacity <= 0 or self.delay <= 0:
            raise ValueError("profile capacity and delay must be positive")
        if self.cost < 0 or self.gamma < 0:
            raise ValueError("profile cost and gamma must not be negative")
        if self.base_delay_ms < 0 or self.congestion_delay_ms < 0:
            raise ValueError("profile delays must not be negative")
        if self.observation_seed is not None and self.observation_seed < 0:
            raise ValueError("profile observation_seed must not be negative")


def load_milp_runtime_profiles(
    path: str | Path,
) -> dict[tuple[int, int], MILPRuntimeReplicaProfile]:
    return milp_runtime_profiles_from_document(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def milp_runtime_profiles_from_document(
    document: object,
) -> dict[tuple[int, int], MILPRuntimeReplicaProfile]:
    """Parse the JSON-safe runtime-profile document used by replica Pods."""

    if not isinstance(document, dict):
        raise ValueError("profile document must be an object")
    stages = document.get("stages")
    if not isinstance(stages, dict):
        raise ValueError("profile document must contain a stages mapping")
    profiles: dict[tuple[int, int], MILPRuntimeReplicaProfile] = {}
    for stage_value, replicas in stages.items():
        if not isinstance(replicas, dict):
            raise ValueError(f"stage {stage_value} profiles must be a mapping")
        for replica_value, values in replicas.items():
            key = (int(stage_value), int(replica_value))
            if key[0] < 1 or key[1] < 1:
                raise ValueError("profile stage and replica IDs must be positive")
            profiles[key] = MILPRuntimeReplicaProfile(**values)
    if not profiles:
        raise ValueError("profile document must contain at least one replica")
    return profiles


def _extension_observation_seed(stage: int, replica_id: int) -> int:
    total = stage + replica_id
    pairing = (total * (total + 1) // 2) + replica_id
    return 1_000_000_000 + pairing


def expand_milp_runtime_profiles(
    profiles: dict[tuple[int, int], MILPRuntimeReplicaProfile],
    num_of_stages: int,
    num_of_replicas: int,
) -> dict[tuple[int, int], MILPRuntimeReplicaProfile]:
    """Select or deterministically extend MILP-owned processor profiles."""

    if num_of_stages < 1 or num_of_replicas < 1:
        raise ValueError("stage and replica counts must be positive")
    if not profiles:
        raise ValueError("at least one template profile is required")
    stage_ids = sorted({stage for stage, _ in profiles})
    replica_ids_by_stage = {
        stage: sorted(replica_id for profile_stage, replica_id in profiles if profile_stage == stage)
        for stage in stage_ids
    }
    expanded: dict[tuple[int, int], MILPRuntimeReplicaProfile] = {}
    for stage in range(1, num_of_stages + 1):
        template_stage = stage_ids[(stage - 1) % len(stage_ids)]
        template_replicas = replica_ids_by_stage[template_stage]
        for replica_id in range(1, num_of_replicas + 1):
            key = (stage, replica_id)
            if key in profiles:
                expanded[key] = profiles[key]
                continue
            template_replica = template_replicas[(replica_id - 1) % len(template_replicas)]
            expanded[key] = replace(
                profiles[(template_stage, template_replica)],
                observation_seed=_extension_observation_seed(stage, replica_id),
            )
    return expanded


def milp_runtime_profiles_document(
    profiles: dict[tuple[int, int], MILPRuntimeReplicaProfile],
) -> dict[str, object]:
    stages: dict[str, dict[str, dict[str, object]]] = {}
    for (stage, replica_id), profile in sorted(profiles.items()):
        stages.setdefault(str(stage), {})[str(replica_id)] = asdict(profile)
    return {"stages": stages}
