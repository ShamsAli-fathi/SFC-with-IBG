"""Versioned controller-only admission and planning-link configuration."""

from __future__ import annotations

from dataclasses import dataclass
import json
from math import isfinite
from numbers import Integral
from pathlib import Path
from typing import Mapping

from .contracts import HybridConfiguration, ReplicaChoice
from .phase0_contract import ReplicaAdmission
from .slot_contracts import HybridPairValue


HYBRID_KERNEL_CONTROLLER_INPUT_CONTRACT_VERSION = (
    "ibg-hybrid-kernel-controller-inputs-v1"
)


@dataclass(frozen=True)
class HybridKernelControllerInputDocument:
    """Complete controller inputs that intentionally contain no true state."""

    configuration: HybridConfiguration
    admission: tuple[ReplicaAdmission, ...]
    planning_pair_links: tuple[HybridPairValue, ...]
    source_identity: str
    contract_version: str = HYBRID_KERNEL_CONTROLLER_INPUT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        admission = tuple(self.admission)
        links = tuple(self.planning_pair_links)
        object.__setattr__(self, "admission", admission)
        object.__setattr__(self, "planning_pair_links", links)
        if self.contract_version != HYBRID_KERNEL_CONTROLLER_INPUT_CONTRACT_VERSION:
            raise ValueError("unexpected Hybrid controller-input contract version")
        if not isinstance(self.source_identity, str) or not self.source_identity:
            raise ValueError("source_identity must be a nonempty string")
        expected_choices = {
            ReplicaChoice(stage, replica)
            for stage in range(1, self.configuration.num_stages + 1)
            for replica in range(1, self.configuration.num_replicas + 1)
        }
        actual_choices = tuple(item.choice for item in admission)
        if len(set(actual_choices)) != len(actual_choices):
            raise ValueError("controller admission contains duplicate replicas")
        if set(actual_choices) != expected_choices:
            raise ValueError("controller admission must cover every replica exactly")
        if admission != tuple(sorted(admission, key=lambda item: item.choice)):
            raise ValueError("controller admission must use canonical replica order")
        expected_pairs = {
            (ReplicaChoice(stage_a, replica_a), ReplicaChoice(stage_b, replica_b))
            for stage_a in range(1, self.configuration.num_stages + 1)
            for stage_b in range(stage_a + 1, self.configuration.num_stages + 1)
            for replica_a in range(1, self.configuration.num_replicas + 1)
            for replica_b in range(1, self.configuration.num_replicas + 1)
        }
        actual_pairs = tuple(link.pair for link in links)
        if len(set(actual_pairs)) != len(actual_pairs):
            raise ValueError("controller planning links contain duplicate pairs")
        if set(actual_pairs) != expected_pairs:
            raise ValueError("controller planning links must cover every directed pair")
        if links != tuple(sorted(links, key=lambda item: item.pair)):
            raise ValueError("controller planning links must use canonical pair order")


def controller_input_document_from_mapping(
    value: Mapping[str, object],
) -> HybridKernelControllerInputDocument:
    if not isinstance(value, Mapping):
        raise ValueError("controller-input document must be a mapping")
    configuration_value = value.get("configuration")
    admission_value = value.get("admission")
    links_value = value.get("planning_pair_links")
    if not isinstance(configuration_value, Mapping):
        raise ValueError("controller-input configuration is required")
    if not isinstance(admission_value, list) or not isinstance(links_value, list):
        raise ValueError("controller admission and planning links must be lists")
    configuration = HybridConfiguration(
        num_flows=configuration_value["num_flows"],
        num_stages=configuration_value["num_stages"],
        num_replicas=configuration_value["num_replicas"],
        stage_budget=configuration_value["stage_budget"],
    )
    admission = tuple(
        ReplicaAdmission(
            choice=ReplicaChoice(item["stage"], item["replica"]),
            ready=True,
            max_assigned_flows=item["max_assigned_flows"],
        )
        for item in admission_value
    )
    links = tuple(
        HybridPairValue(
            source=ReplicaChoice(item["source_stage"], item["source_replica"]),
            target=ReplicaChoice(item["target_stage"], item["target_replica"]),
            latency_ms=item["latency_ms"],
        )
        for item in links_value
    )
    return HybridKernelControllerInputDocument(
        configuration=configuration,
        admission=admission,
        planning_pair_links=links,
        source_identity=value["source_identity"],
        contract_version=value["contract_version"],
    )


def load_controller_input_document(
    path: str | Path,
) -> HybridKernelControllerInputDocument:
    return controller_input_document_from_mapping(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )

