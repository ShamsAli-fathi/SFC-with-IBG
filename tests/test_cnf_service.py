import asyncio

from httpx import ASGITransport, AsyncClient
import numpy as np
import pytest

from IBG.header import Replica
from testbed.cnf_service import (
    LegacyObservationSource,
    ReplicaConfig,
    SeededLegacyObservationSource,
    create_app,
)


async def request(app, method, path, **kwargs):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


def fixed_observation(congestion):
    return 3, (0.1, 0.2, 0.3, 0.4)


def test_health_exposes_stable_identity():
    config = ReplicaConfig(stage=2, replica_id=7, pod_name="stage-2-6")
    app = create_app(config, observation_source=fixed_observation)

    response = asyncio.run(request(app, "GET", "/health"))

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "stage": 2,
        "replica_id": 7,
        "pod_name": "stage-2-6",
        "current_concurrency": 0,
    }


def test_process_returns_identity_latency_and_separate_legacy_observation():
    config = ReplicaConfig(
        stage=3,
        replica_id=4,
        pod_name="stage-3-3",
        base_delay_ms=2,
        congestion_delay_ms=1,
    )
    app = create_app(config, observation_source=fixed_observation)

    response = asyncio.run(
        request(
            app,
            "POST",
            "/process",
            json={"slot_id": 5, "flow_id": 11},
        )
    )
    body = response.json()

    assert response.status_code == 200
    assert body["slot_id"] == 5
    assert body["flow_id"] == 11
    assert body["stage"] == 3
    assert body["replica_id"] == 4
    assert body["pod_name"] == "stage-3-3"
    assert body["concurrency"] == 1
    assert body["legacy_congestion"] == 1
    assert body["processing_latency_ms"] >= 2
    assert body["legacy_signal"] == 3
    assert body["legacy_likelihood"] == [0.1, 0.2, 0.3, 0.4]
    assert app.state.runtime.active_requests == 0


def test_legacy_observation_uses_final_assignment_load_not_admission_order():
    observed_congestion = []

    def observation_source(congestion):
        observed_congestion.append(congestion)
        return fixed_observation(congestion)

    app = create_app(
        ReplicaConfig(base_delay_ms=30, congestion_delay_ms=5),
        observation_source=observation_source,
    )

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await asyncio.gather(
                *[
                    client.post(
                        "/process",
                        json={
                            "slot_id": 1,
                            "flow_id": flow_id,
                            "legacy_congestion": 3,
                        },
                    )
                    for flow_id in (1, 2, 3)
                ]
            )

    responses = asyncio.run(scenario())

    assert sorted(response.json()["concurrency"] for response in responses) == [1, 2, 3]
    assert {response.json()["legacy_congestion"] for response in responses} == {3}
    assert observed_congestion == [3, 3, 3]


def test_concurrent_requests_report_real_overlapping_load():
    observed_concurrency = []

    def observation_source(congestion):
        observed_concurrency.append(congestion)
        return fixed_observation(congestion)

    config = ReplicaConfig(base_delay_ms=30, congestion_delay_ms=5)
    app = create_app(config, observation_source=observation_source)

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await asyncio.gather(
                *[
                    client.post(
                        "/process",
                        json={"slot_id": 1, "flow_id": flow_id},
                    )
                    for flow_id in (1, 2, 3)
                ]
            )

    responses = asyncio.run(scenario())

    assert all(response.status_code == 200 for response in responses)
    assert sorted(response.json()["concurrency"] for response in responses) == [1, 2, 3]
    assert sorted(observed_concurrency) == [1, 2, 3]
    assert app.state.runtime.peak_concurrency == 3
    assert app.state.runtime.active_requests == 0


def test_legacy_observation_source_matches_reference_tasting():
    config = ReplicaConfig(stage=1, replica_id=2, state=2, capacity=5000)
    reference = Replica(1, 2, [0.25] * 4, 5, 1, 0, 2, 5000)

    np.random.seed(77)
    expected_signal, expected_likelihood = reference.tasting(congestion=3)
    np.random.seed(77)
    signal, likelihood = LegacyObservationSource(config)(congestion=3)

    assert signal == expected_signal
    np.testing.assert_allclose(likelihood, expected_likelihood)


def test_seeded_observation_is_request_stable_and_uses_legacy_model():
    source = SeededLegacyObservationSource(
        ReplicaConfig(
            stage=2,
            replica_id=3,
            state=3,
            capacity=3500,
            observation_seed=1203,
        )
    )

    first = source(congestion=2, slot_id=4, flow_id=1)
    repeated = source(congestion=2, slot_id=4, flow_id=1)
    another_flow = source(congestion=2, slot_id=4, flow_id=2)

    assert repeated == first
    assert another_flow[1] != first[1]


def test_request_validation_rejects_invalid_flow_without_leaking_load():
    app = create_app(ReplicaConfig(), observation_source=fixed_observation)

    response = asyncio.run(
        request(
            app,
            "POST",
            "/process",
            json={"slot_id": 1, "flow_id": 0},
        )
    )

    assert response.status_code == 422
    assert app.state.runtime.active_requests == 0


def test_processing_failure_releases_concurrency_counter():
    def failing_observation(congestion):
        raise RuntimeError("observation failed")

    app = create_app(
        ReplicaConfig(base_delay_ms=0),
        observation_source=failing_observation,
    )

    with pytest.raises(RuntimeError, match="observation failed"):
        asyncio.run(
            request(
                app,
                "POST",
                "/process",
                json={"slot_id": 1, "flow_id": 1},
            )
        )

    assert app.state.runtime.active_requests == 0


def test_environment_configuration_is_deterministic():
    config = ReplicaConfig.from_env(
        {
            "STAGE": "2",
            "REPLICA_ID": "6",
            "POD_NAME": "stage-2-5",
            "STATE": "3",
            "CAPACITY": "5000",
            "BASE_DELAY_MS": "7.5",
            "CONGESTION_DELAY_MS": "1.25",
            "OBSERVATION_SEED": "1206",
        }
    )

    assert config == ReplicaConfig(
        stage=2,
        replica_id=6,
        pod_name="stage-2-5",
        state=3,
        capacity=5000,
        base_delay_ms=7.5,
        congestion_delay_ms=1.25,
        observation_seed=1206,
    )


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"stage": 0}, "stage"),
        ({"replica_id": 0}, "replica_id"),
        ({"pod_name": ""}, "pod_name"),
        ({"state": 5}, "state"),
        ({"capacity": 0}, "capacity"),
        ({"base_delay_ms": -1}, "base_delay_ms"),
        ({"congestion_delay_ms": -1}, "congestion_delay_ms"),
        ({"observation_seed": -1}, "observation_seed"),
    ],
)
def test_replica_config_rejects_invalid_values(changes, message):
    values = {
        "stage": 1,
        "replica_id": 1,
        "pod_name": "stage-1-0",
        "state": 4,
        "capacity": 2000,
        "base_delay_ms": 5,
        "congestion_delay_ms": 2,
    }
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        ReplicaConfig(**values)
