import asyncio

from httpx import ASGITransport, AsyncClient
import numpy as np
import pytest

from IBG.latency_model import require_state_parameters, sample_latency_ms
from testbed.cnf_service import (
    LatencyObservationSource,
    ReplicaConfig,
    SeededLatencyObservationSource,
    create_app,
)


async def request(app, method, path, **kwargs):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


def fixed_latency(assigned_load):
    return 2.0


def test_health_exposes_stable_identity():
    config = ReplicaConfig(stage=2, replica_id=7, pod_name="stage-2-6")
    app = create_app(config, observation_source=fixed_latency)

    response = asyncio.run(request(app, "GET", "/health"))

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "stage": 2,
        "replica_id": 7,
        "pod_name": "stage-2-6",
        "current_concurrency": 0,
    }


def test_process_returns_identity_and_latency_observation():
    config = ReplicaConfig(
        stage=3,
        replica_id=4,
        pod_name="stage-3-3",
        base_delay_ms=2,
        congestion_delay_ms=1,
    )
    app = create_app(config, observation_source=fixed_latency)

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
    assert body["assigned_load"] == 1
    assert body["modeled_processing_latency_ms"] == 2.0
    assert body["legacy_congestion"] == 1
    assert body["processing_latency_ms"] >= 2
    assert body["signal_latency_ms"] == body["processing_latency_ms"]
    assert body["legacy_signal"] == body["state_estimate"]
    assert body["legacy_likelihood"] == body["state_likelihood"]
    assert sum(body["state_likelihood"]) == pytest.approx(1.0)
    assert "processor_timing" not in body
    assert app.state.runtime.active_requests == 0


def test_opt_in_processor_path_diagnostics_split_private_work():
    app = create_app(
        ReplicaConfig(stage=2, replica_id=3, pod_name="stage-2-2"),
        observation_source=fixed_latency,
    )

    response = asyncio.run(
        request(
            app,
            "POST",
            "/process",
            headers={"x-ibg-forwarding-path-diagnostics": "1"},
            json={
                "slot_id": 5,
                "flow_id": 11,
                "forwarding_path_diagnostics": True,
            },
        )
    )

    assert response.status_code == 200
    timing = response.json()["processor_timing"]
    assert timing["schema_version"] == "processor_path_v1"
    assert timing["clock"] == "unix-epoch-ns"
    assert (
        timing["ingress_started_unix_ns"]
        <= timing["handler_started_unix_ns"]
        <= timing["work_started_unix_ns"]
        <= timing["work_finished_unix_ns"]
        <= timing["handler_finished_unix_ns"]
    )
    assert timing["work_ms"] >= 2.0
    assert timing["handler_ms"] == pytest.approx(
        timing["pre_work_ms"]
        + timing["work_ms"]
        + timing["post_work_ms"],
        abs=1e-6,
    )


def test_warmup_absorbs_first_use_without_consuming_observation_source():
    def forbidden_observation(assigned_load):
        raise AssertionError("warmup must not sample a processing observation")

    app = create_app(
        ReplicaConfig(stage=2, replica_id=3, pod_name="stage-2-2", state=4),
        observation_source=forbidden_observation,
    )

    first = asyncio.run(request(app, "GET", "/warmup"))
    repeated = asyncio.run(request(app, "GET", "/warmup"))

    assert first.status_code == 200
    assert repeated.status_code == 200
    assert app.state.runtime.warmed is True
    assert app.state.runtime.active_requests == 0
    assert app.state.runtime.peak_concurrency == 0


def test_seeded_warmup_does_not_shift_request_stable_processing_sample():
    config = ReplicaConfig(
        stage=2,
        replica_id=3,
        pod_name="stage-2-2",
        state=4,
        observation_seed=1203,
    )
    expected = SeededLatencyObservationSource(config)(
        assigned_load=2,
        slot_id=7,
        flow_id=4,
    )
    app = create_app(config)

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            await client.get("/warmup")
            return await client.post(
                "/process",
                json={
                    "slot_id": 7,
                    "flow_id": 4,
                    "assigned_load": 2,
                },
            )

    response = asyncio.run(scenario())

    assert response.status_code == 200
    assert response.json()["modeled_processing_latency_ms"] == expected


def test_latency_model_uses_final_assignment_load_not_admission_order():
    observed_congestion = []

    def observation_source(assigned_load):
        observed_congestion.append(assigned_load)
        return 30.0

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
                            "assigned_load": 3,
                        },
                    )
                    for flow_id in (1, 2, 3)
                ]
            )

    responses = asyncio.run(scenario())

    assert sorted(response.json()["concurrency"] for response in responses) == [1, 2, 3]
    assert {response.json()["assigned_load"] for response in responses} == {3}
    assert observed_congestion == [3, 3, 3]


def test_concurrent_requests_report_real_overlapping_load():
    observed_concurrency = []

    def observation_source(assigned_load):
        observed_concurrency.append(assigned_load)
        return 30.0

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


def test_latency_observation_source_matches_reference_model():
    config = ReplicaConfig(stage=1, replica_id=2, state=2, capacity=5000)

    np.random.seed(77)
    expected = sample_latency_ms(3, require_state_parameters(2))
    np.random.seed(77)
    observed = LatencyObservationSource(config)(assigned_load=3)

    assert observed == expected


def test_seeded_latency_is_request_stable_and_uses_phase1_model():
    source = SeededLatencyObservationSource(
        ReplicaConfig(
            stage=2,
            replica_id=3,
            state=3,
            capacity=3500,
            observation_seed=1203,
        )
    )

    first = source(assigned_load=2, slot_id=4, flow_id=1)
    repeated = source(assigned_load=2, slot_id=4, flow_id=1)
    another_flow = source(assigned_load=2, slot_id=4, flow_id=2)

    assert repeated == first
    assert another_flow != first


def test_hidden_state_causally_changes_modeled_processing_latency():
    bad = SeededLatencyObservationSource(
        ReplicaConfig(state=1, observation_seed=99)
    )(assigned_load=2, slot_id=1, flow_id=1)
    good = SeededLatencyObservationSource(
        ReplicaConfig(state=4, observation_seed=99)
    )(assigned_load=2, slot_id=1, flow_id=1)

    assert bad > good


def test_request_validation_rejects_invalid_flow_without_leaking_load():
    app = create_app(ReplicaConfig(), observation_source=fixed_latency)

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
