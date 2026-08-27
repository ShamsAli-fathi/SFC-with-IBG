from __future__ import annotations

import pytest

from Greedy.evidence import _belief_mapping
from Greedy.kernel_lifecycle import (
    GreedyLifecycleError,
    _memory_mib,
    image_source_fingerprints,
)


def test_live_kubernetes_allocatable_ki_is_conservatively_accepted():
    assert _memory_mib("32813992Ki") == 32044
    assert _memory_mib("2048Mi") == 2048
    assert _memory_mib("2Gi") == 2048


@pytest.mark.parametrize("value", ("-1Ki", "not-memory", "1Ti", ""))
def test_worker_memory_quantity_still_fails_closed_for_invalid_values(value):
    with pytest.raises(GreedyLifecycleError):
        _memory_mib(value)


def test_lifecycle_source_fingerprints_match_trace_sha256_width():
    fingerprints = image_source_fingerprints()
    assert set(fingerprints) == {"service", "controller"}
    assert all(len(value) == 64 for value in fingerprints.values())
    assert all(
        character in "0123456789abcdef"
        for value in fingerprints.values()
        for character in value
    )


@pytest.mark.parametrize(
    "belief",
    (
        [0.199, 0.399, 0.201, 0.2],  # 0.999 after frozen learner rounding
        [0.201, 0.399, 0.201, 0.2],  # 1.001 after frozen learner rounding
    ),
)
def test_evidence_accepts_bounded_three_decimal_belief_rounding(belief):
    result = _belief_mapping(
        {"1:1": belief},
        name="beliefs_after",
        identities=((1, 1),),
    )
    assert result[(1, 1)] == tuple(belief)


@pytest.mark.parametrize(
    "belief",
    (
        [0.19, 0.39, 0.2, 0.2],
        [0.21, 0.4, 0.2, 0.2],
    ),
)
def test_evidence_rejects_belief_mass_beyond_rounding_bound(belief):
    with pytest.raises(ValueError, match="rounded unit-mass tolerance"):
        _belief_mapping(
            {"1:1": belief},
            name="beliefs_after",
            identities=((1, 1),),
        )
