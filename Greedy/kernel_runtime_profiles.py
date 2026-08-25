"""Greedy-owned validation for processor-private runtime profiles."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from .contracts import GreedyConfiguration, ReplicaIdentity
from .slot_contracts import (
    GreedyReplicaProfile,
    materialized_profile_fingerprint,
)


GREEDY_KERNEL_RUNTIME_PROFILE_VERSION = "greedy-kernel-runtime-profile-v1"


@dataclass(frozen=True)
class GreedyKernelRuntimeProfileDocument:
    """Complete hidden environment map mounted only into processors."""

    configuration: GreedyConfiguration
    profiles: tuple[GreedyReplicaProfile, ...]
    source_identity: str
    contract_version: str = GREEDY_KERNEL_RUNTIME_PROFILE_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, GreedyConfiguration):
            raise TypeError("configuration must be GreedyConfiguration")
        profiles = tuple(self.profiles)
        object.__setattr__(self, "profiles", profiles)
        if not isinstance(self.source_identity, str) or not self.source_identity:
            raise ValueError("source_identity must be a nonempty string")
        if self.contract_version != GREEDY_KERNEL_RUNTIME_PROFILE_VERSION:
            raise ValueError("unexpected Greedy runtime-profile version")
        if not all(type(profile) is GreedyReplicaProfile for profile in profiles):
            raise TypeError("profiles must contain GreedyReplicaProfile values")
        expected = tuple(
            ReplicaIdentity(stage, replica)
            for stage in self.configuration.stages
            for replica in self.configuration.replica_ids
        )
        identities = tuple(profile.identity for profile in profiles)
        if identities != expected:
            raise ValueError(
                "runtime profiles must cover canonical contiguous identities exactly"
            )

    @property
    def fingerprint(self) -> str:
        return materialized_profile_fingerprint(self.profiles)

    def profile_by_identity(self) -> Mapping[ReplicaIdentity, GreedyReplicaProfile]:
        return {profile.identity: profile for profile in self.profiles}


def runtime_profile_document_from_mapping(
    value: Mapping[str, object],
) -> GreedyKernelRuntimeProfileDocument:
    if not isinstance(value, Mapping):
        raise ValueError("runtime-profile document must be a mapping")
    required = {
        "configuration",
        "profiles",
        "source_identity",
        "contract_version",
    }
    if set(value) != required:
        raise ValueError("runtime-profile document fields are incomplete or unexpected")
    dimensions = value["configuration"]
    profiles = value["profiles"]
    if not isinstance(dimensions, Mapping) or set(dimensions) != {
        "num_flows",
        "num_stages",
        "num_replicas",
    }:
        raise ValueError("runtime-profile configuration requires explicit N, K, and M")
    if not isinstance(profiles, list):
        raise ValueError("runtime-profile profiles must be a list")
    try:
        configuration = GreedyConfiguration(
            dimensions["num_flows"],
            dimensions["num_stages"],
            dimensions["num_replicas"],
        )
        entries = tuple(
            GreedyReplicaProfile(
                identity=ReplicaIdentity(item["stage"], item["replica"]),
                hidden_state=item["hidden_state"],
                observation_seed=item["observation_seed"],
            )
            for item in profiles
        )
        return GreedyKernelRuntimeProfileDocument(
            configuration=configuration,
            profiles=entries,
            source_identity=value["source_identity"],
            contract_version=value["contract_version"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid Greedy runtime-profile document: {error}") from error


def runtime_profile_document_to_mapping(
    document: GreedyKernelRuntimeProfileDocument,
) -> dict[str, object]:
    if not isinstance(document, GreedyKernelRuntimeProfileDocument):
        raise TypeError("document must be GreedyKernelRuntimeProfileDocument")
    configuration = document.configuration
    return {
        "contract_version": document.contract_version,
        "source_identity": document.source_identity,
        "configuration": {
            "num_flows": configuration.num_flows,
            "num_stages": configuration.num_stages,
            "num_replicas": configuration.num_replicas,
        },
        "profiles": [
            {
                "stage": profile.identity.stage,
                "replica": profile.identity.replica,
                "hidden_state": profile.hidden_state,
                "observation_seed": profile.observation_seed,
            }
            for profile in document.profiles
        ],
    }


def load_runtime_profile_document(
    path: str | Path,
) -> GreedyKernelRuntimeProfileDocument:
    return runtime_profile_document_from_mapping(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
