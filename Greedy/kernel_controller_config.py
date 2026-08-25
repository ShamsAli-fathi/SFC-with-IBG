"""Import-safe parsing for the public Greedy finite-controller document."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from .contracts import GreedyConfiguration
from .kernel_contracts import GreedyKernelControllerConfiguration


GREEDY_KERNEL_CONTROLLER_INPUT_VERSION = "greedy-kernel-controller-inputs-v1"


@dataclass(frozen=True)
class GreedyKernelControllerInputDocument:
    controller: GreedyKernelControllerConfiguration
    source_identity: str
    contract_version: str = GREEDY_KERNEL_CONTROLLER_INPUT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.controller, GreedyKernelControllerConfiguration):
            raise TypeError("controller must be GreedyKernelControllerConfiguration")
        if not isinstance(self.source_identity, str) or not self.source_identity:
            raise ValueError("source_identity must be a nonempty string")
        if self.contract_version != GREEDY_KERNEL_CONTROLLER_INPUT_VERSION:
            raise ValueError("unexpected Greedy controller-input version")


def controller_input_document_from_mapping(
    value: Mapping[str, object],
) -> GreedyKernelControllerInputDocument:
    if not isinstance(value, Mapping):
        raise ValueError("controller-input document must be a mapping")
    required = {
        "configuration",
        "experiment_id",
        "root_seed",
        "profile_seed",
        "runtime_profile_fingerprint",
        "max_iterations",
        "source_identity",
        "contract_version",
    }
    optional = {"first_slot_id", "controller_contract_version"}
    missing = required - set(value)
    unexpected = set(value) - required - optional
    if missing:
        raise ValueError(f"controller-input document is missing fields: {sorted(missing)}")
    if unexpected:
        raise ValueError(
            f"controller-input document contains forbidden fields: {sorted(unexpected)}"
        )
    dimensions = value.get("configuration")
    if not isinstance(dimensions, Mapping):
        raise ValueError("controller-input configuration is required")
    if set(dimensions) != {"num_flows", "num_stages", "num_replicas"}:
        raise ValueError(
            "controller-input dimensions must contain only explicit N, K, and M"
        )
    configuration = GreedyConfiguration(
        num_flows=dimensions["num_flows"],
        num_stages=dimensions["num_stages"],
        num_replicas=dimensions["num_replicas"],
    )
    controller = GreedyKernelControllerConfiguration(
        configuration=configuration,
        experiment_id=value["experiment_id"],
        root_seed=value["root_seed"],
        profile_seed=value["profile_seed"],
        runtime_profile_fingerprint=value["runtime_profile_fingerprint"],
        max_iterations=value["max_iterations"],
        first_slot_id=value.get("first_slot_id", 1),
        contract_version=value.get(
            "controller_contract_version",
            GreedyKernelControllerConfiguration.__dataclass_fields__["contract_version"].default,
        ),
    )
    return GreedyKernelControllerInputDocument(
        controller=controller,
        source_identity=value["source_identity"],
        contract_version=value["contract_version"],
    )


def controller_input_document_to_mapping(
    document: GreedyKernelControllerInputDocument,
) -> dict[str, object]:
    if not isinstance(document, GreedyKernelControllerInputDocument):
        raise TypeError("document must be GreedyKernelControllerInputDocument")
    controller = document.controller
    configuration = controller.configuration
    return {
        "contract_version": document.contract_version,
        "source_identity": document.source_identity,
        "configuration": {
            "num_flows": configuration.num_flows,
            "num_stages": configuration.num_stages,
            "num_replicas": configuration.num_replicas,
        },
        "experiment_id": controller.experiment_id,
        "root_seed": controller.root_seed,
        "profile_seed": controller.profile_seed,
        "runtime_profile_fingerprint": controller.runtime_profile_fingerprint,
        "max_iterations": controller.max_iterations,
        "first_slot_id": controller.first_slot_id,
        "controller_contract_version": controller.contract_version,
    }


def load_controller_input_document(
    path: str | Path,
) -> GreedyKernelControllerInputDocument:
    return controller_input_document_from_mapping(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
