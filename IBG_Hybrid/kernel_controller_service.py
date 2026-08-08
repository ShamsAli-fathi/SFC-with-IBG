"""Import-safe entry point for a future Hybrid controller Job."""

from __future__ import annotations

import os

from .kernel_controller import (
    HybridKernelControllerAdapter,
    HybridKernelFlowGeneratorHttpClient,
)
from .kernel_controller_config import load_controller_input_document
from .kernel_infrastructure_contract import DEFAULT_HYBRID_KERNEL_OWNERSHIP
from .kernel_kubernetes_discovery import (
    HybridKubernetesApi,
    HybridKubernetesReplicaDiscovery,
)
from .runner import format_hybrid_slot_metrics


def main() -> None:
    inputs = load_controller_input_document(
        os.environ.get(
            "HYBRID_CONTROLLER_INPUTS_PATH",
            "/etc/ibg-hybrid-controller/controller-inputs.json",
        )
    )
    ownership = DEFAULT_HYBRID_KERNEL_OWNERSHIP
    api = HybridKubernetesApi(ownership=ownership)
    discovery = HybridKubernetesReplicaDiscovery(
        api,
        inputs.configuration,
        ownership=ownership,
    )
    flow_generator = HybridKernelFlowGeneratorHttpClient(
        os.environ.get(
            "FLOW_GENERATOR_URL",
            "http://ibg-hybrid-flow-generator.ibg-hybrid-testbed."
            "svc.cluster.local.:8080",
        )
    )
    uniform = (0.25, 0.25, 0.25, 0.25)
    controller = HybridKernelControllerAdapter(
        controller_inputs=inputs,
        discovery=discovery,
        flow_generator=flow_generator,
        initial_beliefs={item.choice: uniform for item in inputs.admission},
    )
    first_slot = int(os.environ.get("SLOT_ID", "1"))
    iterations = int(os.environ.get("MAX_ITERATIONS", "1"))
    if first_slot < 1 or iterations < 1:
        raise ValueError("SLOT_ID and MAX_ITERATIONS must be positive")
    for slot_id in range(first_slot, first_slot + iterations):
        outcome = controller.run_slot(slot_id)
        print(format_hybrid_slot_metrics(outcome.slot), flush=True)


if __name__ == "__main__":
    main()

