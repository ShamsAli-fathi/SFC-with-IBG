from dataclasses import dataclass
from typing import Callable, Mapping


def belief_snapshot(replica_list):
    return {
        f"{stage}:{replica_id}": [float(value) for value in replica.belief]
        for (stage, replica_id), replica in sorted(replica_list.items())
    }


def replica_snapshot(replica_list):
    return [
        {
            "stage": int(stage),
            "replica_id": int(replica_id),
            "belief": [float(value) for value in replica.belief],
            "delay": float(replica.delay),
            "cost": float(replica.cost),
            "gamma": float(replica.gamma),
            "state": int(replica.state),
            "capacity": int(replica.capacity),
        }
        for (stage, replica_id), replica in sorted(replica_list.items())
    ]


def max_belief_delta(before, after):
    return max(
        (
            abs(before[key][index] - after[key][index])
            for key in before
            for index in range(len(before[key]))
        ),
        default=0.0,
    )


@dataclass(frozen=True)
class ExperimentOutcome:
    iterations: int
    reached_equilibrium: bool
    final_summary: Mapping


def run_until_equilibrium(
    *,
    replica_list,
    first_slot_id,
    max_iterations,
    run_slot: Callable,
    summarize: Callable,
    emit: Callable,
    run_metadata,
    require_equilibrium=True,
):
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")

    emit(
        {
            "event": "run_started",
            **run_metadata,
            "max_iterations": max_iterations,
            "initial_replicas": replica_snapshot(replica_list),
        }
    )

    final_summary = None
    for iteration in range(1, max_iterations + 1):
        slot_id = first_slot_id + iteration - 1
        beliefs_before = belief_snapshot(replica_list)
        result = run_slot(slot_id)
        final_summary = summarize(result, slot_id)
        beliefs_after = belief_snapshot(replica_list)
        emit(
            {
                "event": "iteration_completed",
                **run_metadata,
                "iteration": iteration,
                "slot_id": slot_id,
                "max_belief_delta": max_belief_delta(
                    beliefs_before,
                    beliefs_after,
                ),
                "beliefs_before": beliefs_before,
                "summary": final_summary,
            }
        )
        if result.equilibrium == 1:
            emit(
                {
                    "event": "run_completed",
                    **run_metadata,
                    "iterations": iteration,
                    "reached_equilibrium": True,
                    "final_replicas": replica_snapshot(replica_list),
                }
            )
            return ExperimentOutcome(iteration, True, final_summary)

    emit(
        {
            "event": "run_completed",
            **run_metadata,
            "iterations": max_iterations,
            "reached_equilibrium": False,
            "final_replicas": replica_snapshot(replica_list),
        }
    )
    if require_equilibrium:
        raise RuntimeError(
            f"equilibrium was not reached within {max_iterations} iterations"
        )
    return ExperimentOutcome(max_iterations, False, final_summary)
