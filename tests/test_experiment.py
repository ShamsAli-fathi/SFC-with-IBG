from types import SimpleNamespace

import pytest

from testbed.experiment import (
    belief_snapshot,
    max_belief_delta,
    replica_snapshot,
    run_until_equilibrium,
)


def make_replica():
    return SimpleNamespace(
        belief=[0.25, 0.25, 0.25, 0.25],
        delay=25,
        cost=1,
        gamma=0.2,
        state=1,
        capacity=2000,
    )


def test_snapshots_are_stable_and_measure_the_largest_change():
    replicas = {(1, 1): make_replica()}
    before = belief_snapshot(replicas)
    replicas[(1, 1)].belief = [0.4, 0.2, 0.2, 0.2]
    after = belief_snapshot(replicas)

    assert before == {"1:1": [0.25, 0.25, 0.25, 0.25]}
    assert max_belief_delta(before, after) == pytest.approx(0.15)
    assert replica_snapshot(replicas)[0]["replica_id"] == 1


def test_equilibrium_runner_keeps_state_and_emits_complete_trace():
    replicas = {(1, 1): make_replica()}
    events = []
    slots = []

    def run_slot(slot_id):
        slots.append(slot_id)
        if len(slots) == 1:
            replicas[(1, 1)].belief = [0.4, 0.2, 0.2, 0.2]
            return SimpleNamespace(equilibrium=0)
        replicas[(1, 1)].belief = [0.41, 0.2, 0.2, 0.19]
        return SimpleNamespace(equilibrium=1)

    outcome = run_until_equilibrium(
        replica_list=replicas,
        first_slot_id=7,
        max_iterations=5,
        run_slot=run_slot,
        summarize=lambda result, slot_id: {
            "slot_id": slot_id,
            "metrics": {"equilibrium": result.equilibrium},
        },
        emit=events.append,
        run_metadata={"seed": 2050},
    )

    assert slots == [7, 8]
    assert outcome.iterations == 2
    assert outcome.reached_equilibrium is True
    assert [event["event"] for event in events] == [
        "run_started",
        "iteration_completed",
        "iteration_completed",
        "run_completed",
    ]
    assert events[1]["max_belief_delta"] == pytest.approx(0.15)
    assert events[2]["max_belief_delta"] == pytest.approx(0.01)
    assert events[-1]["final_replicas"][0]["belief"] == [
        0.41,
        0.2,
        0.2,
        0.19,
    ]


def test_equilibrium_runner_fails_after_bounded_iterations():
    replicas = {(1, 1): make_replica()}
    events = []

    with pytest.raises(RuntimeError, match="within 2 iterations"):
        run_until_equilibrium(
            replica_list=replicas,
            first_slot_id=1,
            max_iterations=2,
            run_slot=lambda slot_id: SimpleNamespace(equilibrium=0),
            summarize=lambda result, slot_id: {"slot_id": slot_id},
            emit=events.append,
            run_metadata={"seed": 2050},
        )

    assert events[-1]["event"] == "run_completed"
    assert events[-1]["reached_equilibrium"] is False
