import json

import pytest

from testbed.network_impairment import (
    NETWORK_IMPAIRMENT_DISTRIBUTION,
    NETWORK_IMPAIRMENT_INTERFACE,
    NETWORK_IMPAIRMENT_SCHEMA,
    NETWORK_IMPAIRMENT_SCOPE,
    NetworkImpairment,
)


def test_disabled_network_impairment_is_explicit_and_has_no_tc_command():
    impairment = NetworkImpairment.disabled()

    assert impairment.to_dict() == {
        "schema": NETWORK_IMPAIRMENT_SCHEMA,
        "enabled": False,
        "delay_ms": 0.0,
        "jitter_ms": 0.0,
        "distribution": NETWORK_IMPAIRMENT_DISTRIBUTION,
        "interface": NETWORK_IMPAIRMENT_INTERFACE,
        "scope": NETWORK_IMPAIRMENT_SCOPE,
    }
    with pytest.raises(ValueError, match="has no tc command"):
        impairment.tc_command()


def test_enabled_network_impairment_builds_normal_delay_jitter_command():
    impairment = NetworkImpairment.enabled_with(
        delay_ms=10,
        jitter_ms=3,
    )

    assert impairment.tc_command() == [
        "/usr/sbin/tc",
        "qdisc",
        "replace",
        "dev",
        "eth0",
        "root",
        "netem",
        "delay",
        "10ms",
        "3ms",
        "distribution",
        "normal",
    ]
    assert NetworkImpairment.from_json(impairment.to_json()) == impairment
    assert json.loads(impairment.to_json())["enabled"] is True


@pytest.mark.parametrize(
    ("delay_ms", "jitter_ms", "message"),
    [
        (0, 0, "positive delay_ms"),
        (-1, 0, "finite and non-negative"),
        (10, -1, "finite and non-negative"),
        (2, 3, "cannot exceed"),
    ],
)
def test_enabled_network_impairment_rejects_invalid_values(
    delay_ms,
    jitter_ms,
    message,
):
    with pytest.raises(ValueError, match=message):
        NetworkImpairment.enabled_with(
            delay_ms=delay_ms,
            jitter_ms=jitter_ms,
        )


def test_network_impairment_metadata_is_strictly_versioned():
    document = NetworkImpairment.disabled().to_dict()
    document["schema"] = "future"

    with pytest.raises(ValueError, match="unsupported schema"):
        NetworkImpairment.from_dict(document)
