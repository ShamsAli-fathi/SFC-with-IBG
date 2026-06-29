from dataclasses import dataclass
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

    def __post_init__(self):
        if self.state not in (1, 2, 3, 4):
            raise ValueError("profile state must be one of 1, 2, 3, or 4")
        if self.capacity <= 0 or self.delay <= 0:
            raise ValueError("profile capacity and delay must be positive")
        if self.cost < 0 or self.gamma < 0:
            raise ValueError("profile cost and gamma must not be negative")
        if self.base_delay_ms < 0 or self.congestion_delay_ms < 0:
            raise ValueError("profile delays must not be negative")


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
