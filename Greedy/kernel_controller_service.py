"""Import-safe finite controller entry point with Phase 6 presentation."""

from __future__ import annotations

import os

from .console_output import (
    format_greedy_replica_beliefs,
    format_greedy_slot_metrics,
)
from .control_plane_footprint import GreedyControlPlaneMeter
from .contracts import ReplicaIdentity
from .evidence import (
    GREEDY_SLOT_EVIDENCE_PREFIX,
    build_greedy_slot_evidence,
    canonical_greedy_evidence_json,
)
from .kernel_controller import GreedyKernelController
from .kernel_controller_config import load_controller_input_document
from .runtime_resources import read_current_controller_resources


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
    meter = (
        GreedyControlPlaneMeter()
        if document.controller.control_plane_footprint_enabled
        else None
    )
    controller = GreedyKernelController.from_http(
        controller_configuration=document.controller,
        initial_beliefs=uniform,
        flow_generator_url=os.environ.get(
            "FLOW_GENERATOR_URL",
            "http://greedy-flow-generator.greedy-testbed.svc.cluster.local.:8080",
        ),
        control_plane_meter=meter,
        resource_sampler=read_current_controller_resources,
    )
    print(
        "\n"
        + format_greedy_replica_beliefs(
            "Initial replica state", controller.beliefs
        ),
        flush=True,
    )

    def completed(iteration, outcome) -> None:
        print(format_greedy_slot_metrics(outcome.slot, iteration=iteration), flush=True)
        evidence = build_greedy_slot_evidence(
            outcome,
            parity_replay_enabled=document.controller.parity_replay_enabled,
        )
        print(
            GREEDY_SLOT_EVIDENCE_PREFIX
            + canonical_greedy_evidence_json(evidence),
            flush=True,
        )

    experiment = controller.run_experiment(on_slot_completed=completed)
    status = "reached" if experiment.pure_experiment.reached_equilibrium else "not reached"
    print(
        f"Equilibrium {status} after "
        f"{experiment.pure_experiment.iterations_completed} iteration(s).",
        flush=True,
    )
    print(
        "\n"
        + format_greedy_replica_beliefs(
            "Final replica state", controller.beliefs
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
