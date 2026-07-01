from dataclasses import dataclass
from dataclasses import asdict, replace
import json
from pathlib import Path


@dataclass(frozen=True)
class ReplicaProfile:
    state: int
    capacity: int
    delay: float
    cost: float
    gamma: float
    base_delay_ms: float
    congestion_delay_ms: float
    observation_seed: int | None = None

    def __post_init__(self):
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


def load_profiles(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    stages = document.get("stages")
    if not isinstance(stages, dict):
        raise ValueError("profile document must contain a stages mapping")

    profiles = {}
    for stage_value, replicas in stages.items():
        if not isinstance(replicas, dict):
            raise ValueError(f"stage {stage_value} profiles must be a mapping")
        for replica_value, values in replicas.items():
            key = (int(stage_value), int(replica_value))
            if key[0] < 1 or key[1] < 1:
                raise ValueError("profile stage and replica IDs must be positive")
            profiles[key] = ReplicaProfile(**values)

    if not profiles:
        raise ValueError("profile document must contain at least one replica")
    return profiles


def require_profile(profiles, stage, replica_id):
    try:
        return profiles[(stage, replica_id)]
    except KeyError as error:
        raise ValueError(
            f"missing deterministic profile for stage {stage} replica {replica_id}"
        ) from error


def _extension_observation_seed(stage, replica_id):
    total = stage + replica_id
    pairing = (total * (total + 1) // 2) + replica_id
    return 1_000_000_000 + pairing


def expand_profiles(profiles, num_of_stages, num_of_replicas):
    """Select or deterministically extend profiles to the requested dimensions."""
    if num_of_stages < 1 or num_of_replicas < 1:
        raise ValueError("stage and replica counts must be positive")
    if not profiles:
        raise ValueError("at least one template profile is required")

    stage_ids = sorted({stage for stage, _ in profiles})
    replica_ids_by_stage = {
        stage: sorted(
            replica_id
            for profile_stage, replica_id in profiles
            if profile_stage == stage
        )
        for stage in stage_ids
    }
    expanded = {}
    for stage in range(1, num_of_stages + 1):
        template_stage = stage_ids[(stage - 1) % len(stage_ids)]
        template_replicas = replica_ids_by_stage[template_stage]
        for replica_id in range(1, num_of_replicas + 1):
            key = (stage, replica_id)
            if key in profiles:
                expanded[key] = profiles[key]
                continue
            template_replica = template_replicas[
                (replica_id - 1) % len(template_replicas)
            ]
            expanded[key] = replace(
                profiles[(template_stage, template_replica)],
                observation_seed=_extension_observation_seed(stage, replica_id),
            )
    return expanded


def profiles_document(profiles):
    stages = {}
    for (stage, replica_id), profile in sorted(profiles.items()):
        stages.setdefault(str(stage), {})[str(replica_id)] = asdict(profile)
    return {"stages": stages}
