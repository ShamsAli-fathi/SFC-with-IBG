"""Import-safe finite controller entry point; presentation remains Phase 6."""

from __future__ import annotations

import os

from .contracts import ReplicaIdentity
from .kernel_controller import GreedyKernelController
from .kernel_controller_config import load_controller_input_document


def main() -> None:
    document = load_controller_input_document(
        os.environ.get(
            "GREEDY_CONTROLLER_INPUTS_PATH",
            "/etc/greedy-controller/controller-inputs.json",
        )
    )
    configuration = document.controller.configuration
    uniform = {
        ReplicaIdentity(stage, replica): (0.25, 0.25, 0.25, 0.25)
        for stage in configuration.stages
        for replica in configuration.replica_ids
    }
    controller = GreedyKernelController.from_http(
        controller_configuration=document.controller,
        initial_beliefs=uniform,
        flow_generator_url=os.environ.get(
            "FLOW_GENERATOR_URL",
            "http://greedy-flow-generator.greedy-testbed.svc.cluster.local.:8080",
        ),
    )
    controller.run_experiment()


if __name__ == "__main__":
    main()
