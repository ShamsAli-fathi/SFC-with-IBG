from __future__ import annotations

import asyncio
import copy
from concurrent.futures import Executor
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from IBG_Hybrid.contracts import ReplicaChoice
import IBG_Hybrid.kernel_controller as controller_module
from IBG_Hybrid.kernel_controller import HybridKernelControllerAdapter
from IBG_Hybrid.kernel_controller_config import controller_input_document_from_mapping
from IBG_Hybrid.posterior_mirror import (
    HYBRID_POSTERIOR_MIRROR_SCHEMA,
    HYBRID_POSTERIOR_RECEIPT_SCHEMA,
    HybridPosteriorMirrorHttpClient,
    build_canonical_posterior_update,
    canonical_posterior_vector_bytes,
    create_posterior_mirror_app,
    posterior_mirror_provenance,
    validate_hybrid_posterior_mirror_snapshot,
    validate_posterior_mirror_provenance,
)
from scripts import run_hybrid_kernel_phase4 as runner


ROOT = Path(__file__).resolve().parents[1]


class _NoopExecutor(Executor):
    def __init__(self):
        self.shutdown_calls = []

    def shutdown(self, wait=True, *, cancel_futures=False):
        self.shutdown_calls.append((wait, cancel_futures))


class _FakeDiscovery:
    def __init__(self, configuration):
        self.configuration = configuration
        self.close_calls = 0

    def wait_for_complete_ready(self, **kwargs):
        assert kwargs == {}
        return SimpleNamespace(
            configuration=self.configuration,
            replicas=tuple(
                SimpleNamespace(choice=ReplicaChoice(stage, 1))
                for stage in range(1, 4)
            ),
        )

    def close(self):
        self.close_calls += 1


class _FakeFlowGenerator:
    def __init__(self):
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


class _RecordingMirror:
    def __init__(self, *, failure: Exception | None = None):
        self.calls = []
        self.close_calls = 0
        self.failure = failure

    def mirror_slot(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        return {"measurement": "accepted"}

    def close(self):
        self.close_calls += 1


def _controller_inputs():
    return controller_input_document_from_mapping(
        {
            "contract_version": "ibg-hybrid-kernel-controller-inputs-v1",
            "source_identity": "posterior-mirror-test-v1",
            "configuration": {
                "num_flows": 2,
                "num_stages": 3,
                "num_replicas": 1,
                "stage_budget": 2,
            },
            "admission": [
                {"stage": stage, "replica": 1, "max_assigned_flows": 2}
                for stage in range(1, 4)
            ],
            "planning_pair_links": [
                {
                    "source_stage": source,
                    "source_replica": 1,
                    "target_stage": target,
                    "target_replica": 1,
                    "latency_ms": 0.25,
                }
                for source, target in ((1, 2), (1, 3), (2, 3))
            ],
        }
    )


def _ready_node(name: str, labels: dict[str, str], *, cpu: str = "8"):
    return {
        "metadata": {"name": name, "labels": labels},
        "status": {
            "allocatable": {"cpu": cpu, "memory": "32Gi"},
            "conditions": [
                {"type": "Ready", "status": "True"},
            ],
        },
    }


def _resource_execute(command, capture_output):
    assert capture_output is True
    if command[-4:] == ("get", "nodes", "-o", "json"):
        return json.dumps(
            {
                "items": [
                    _ready_node(
                        runner.CONTROL_PLANE_NODE_NAME,
                        {"node-role.kubernetes.io/control-plane": ""},
                    ),
                    _ready_node(
                        runner.WORKER_NODE_NAME,
                        {runner.WORKLOAD_NODE_LABEL: runner.WORKLOAD_NODE_LABEL_VALUE},
                    ),
                ]
            }
        )
    if command[-5:] == ("get", "pods", "-A", "-o", "json"):
        return json.dumps({"items": []})
    raise AssertionError(command)


def test_canonical_vector_and_complete_body_are_exact_and_distinct():
    posterior = (0.81, 0.12, 0.05, 0.02)
    vector = canonical_posterior_vector_bytes(posterior)
    update = build_canonical_posterior_update(
        run_id="controller-pod-uid",
        slot_id=7,
        choice=ReplicaChoice(2, 3),
        posterior=posterior,
    )

    assert vector == b"[0.81,0.12,0.05,0.02]"
    assert update.vector_payload == vector
    assert len(update.application_body) > len(vector)
    assert update.application_body == build_canonical_posterior_update(
        run_id="controller-pod-uid",
        slot_id=7,
        choice=ReplicaChoice(2, 3),
        posterior=posterior,
    ).application_body


@pytest.mark.parametrize(
    "posterior",
    (
        (True, 0.0, 0.0, 0.0),
        (float("nan"), 0.3, 0.3, 0.4),
        (float("inf"), 0.3, 0.3, 0.4),
        (-0.1, 0.3, 0.3, 0.5),
        ("0.1", 0.2, 0.3, 0.4),
    ),
)
def test_canonical_vector_rejects_malformed_probabilities(posterior):
    with pytest.raises(ValueError, match="posterior"):
        canonical_posterior_vector_bytes(posterior)


def test_receiver_accepts_only_canonical_unique_updates():
    application = create_posterior_mirror_app()
    update = build_canonical_posterior_update(
        run_id="run-1",
        slot_id=1,
        choice=ReplicaChoice(1, 2),
        posterior=(0.4, 0.3, 0.2, 0.1),
    )

    noncanonical = json.dumps(
        update.document.model_dump(mode="json", by_alias=True),
        indent=2,
    ).encode("utf-8")
    other = noncanonical.replace(b'"run-1"', b'"run-2"')

    async def exercise_receiver():
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://mirror.test",
        ) as client:
            response = await client.post(
                "/posterior-update",
                content=update.application_body,
                headers={"content-type": "application/json"},
            )
            assert response.status_code == 200
            assert response.json()["schema"] == HYBRID_POSTERIOR_RECEIPT_SCHEMA
            assert response.json()["application_body_bytes"] == len(
                update.application_body
            )
            duplicate = await client.post(
                "/posterior-update",
                content=update.application_body,
                headers={"content-type": "application/json"},
            )
            assert duplicate.status_code == 409
            malformed = await client.post(
                "/posterior-update",
                content=other,
                headers={"content-type": "application/json"},
            )
            assert malformed.status_code == 422

    asyncio.run(exercise_receiver())


def test_http_sender_sums_unique_sampled_replicas_in_canonical_order():
    bodies = []

    def receive(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        document = json.loads(request.content)
        canonical = build_canonical_posterior_update(
            run_id=document["run_id"],
            slot_id=document["slot_id"],
            choice=ReplicaChoice(document["stage"], document["replica"]),
            posterior=document["posterior"],
        )
        assert request.content == canonical.application_body
        return httpx.Response(
            200,
            json=canonical.receipt.model_dump(mode="json"),
        )

    beliefs = {
        ReplicaChoice(1, 1): (0.4, 0.3, 0.2, 0.1),
        ReplicaChoice(2, 2): (0.1, 0.2, 0.3, 0.4),
        ReplicaChoice(3, 1): (0.25, 0.25, 0.25, 0.25),
    }
    original = copy.deepcopy(beliefs)
    client = HybridPosteriorMirrorHttpClient(
        "http://mirror.test",
        run_id="run-9",
        transport=httpx.MockTransport(receive),
    )
    try:
        snapshot = client.mirror_slot(
            slot_id=4,
            beliefs_after=beliefs,
            updated_choices=(
                ReplicaChoice(2, 2),
                ReplicaChoice(1, 1),
                ReplicaChoice(2, 2),
            ),
        )
    finally:
        client.close()

    assert beliefs == original
    assert snapshot["schema"] == HYBRID_POSTERIOR_MIRROR_SCHEMA
    assert [
        (item["stage"], item["replica"])
        for item in snapshot["updates"]
    ] == [(1, 1), (2, 2)]
    assert snapshot["messages"]["posterior_updates"] == 2
    assert snapshot["payload_bytes"]["application_bodies"] == sum(
        len(body) for body in bodies
    )
    assert snapshot["payload_bytes"]["posterior_vectors"] == sum(
        item["vector_payload_bytes"] for item in snapshot["updates"]
    )


def test_controller_mirrors_after_learning_without_replacing_local_belief_owner(
    monkeypatch,
):
    inputs = _controller_inputs()
    uniform = {
        item.choice: (0.25, 0.25, 0.25, 0.25)
        for item in inputs.admission
    }
    learned = {
        choice: (0.4, 0.3, 0.2, 0.1)
        for choice in uniform
    }
    sampled = (ReplicaChoice(2, 1), ReplicaChoice(1, 1), ReplicaChoice(2, 1))

    def fake_run(slot_input, **kwargs):
        kwargs["simulation_adapter"].requests_submitted = 1
        return SimpleNamespace(
            beliefs_after=tuple(sorted(learned.items())),
            beliefs_after_mapping=dict(learned),
            observations=tuple(
                SimpleNamespace(choice=choice) for choice in sampled
            ),
        )

    monkeypatch.setattr(controller_module, "run_hybrid_slot", fake_run)
    discovery = _FakeDiscovery(inputs.configuration)
    generator = _FakeFlowGenerator()
    mirror = _RecordingMirror()
    executor = _NoopExecutor()
    controller = HybridKernelControllerAdapter(
        controller_inputs=inputs,
        discovery=discovery,
        flow_generator=generator,
        initial_beliefs=uniform,
        posterior_mirror=mirror,
        lookahead_executor=executor,
    )
    try:
        outcome = controller.run_slot(5)
        assert outcome.posterior_mirror == {"measurement": "accepted"}
        assert mirror.calls == [
            {
                "slot_id": 5,
                "beliefs_after": learned,
                "updated_choices": (ReplicaChoice(1, 1), ReplicaChoice(2, 1)),
            }
        ]
        assert controller.beliefs == learned
    finally:
        controller.close()
    assert mirror.close_calls == discovery.close_calls == generator.close_calls == 1
    assert executor.shutdown_calls == [(True, True)]


def test_failed_mirror_does_not_commit_controller_beliefs(monkeypatch):
    inputs = _controller_inputs()
    uniform = {
        item.choice: (0.25, 0.25, 0.25, 0.25)
        for item in inputs.admission
    }
    learned = {
        choice: (0.4, 0.3, 0.2, 0.1)
        for choice in uniform
    }

    def fake_run(slot_input, **kwargs):
        kwargs["simulation_adapter"].requests_submitted = 1
        return SimpleNamespace(
            beliefs_after=tuple(sorted(learned.items())),
            beliefs_after_mapping=dict(learned),
            observations=(SimpleNamespace(choice=ReplicaChoice(1, 1)),),
        )

    monkeypatch.setattr(controller_module, "run_hybrid_slot", fake_run)
    mirror = _RecordingMirror(failure=RuntimeError("receiver rejected payload"))
    controller = HybridKernelControllerAdapter(
        controller_inputs=inputs,
        discovery=_FakeDiscovery(inputs.configuration),
        flow_generator=_FakeFlowGenerator(),
        initial_beliefs=uniform,
        posterior_mirror=mirror,
        lookahead_executor=_NoopExecutor(),
    )
    try:
        with pytest.raises(RuntimeError, match="receiver rejected payload"):
            controller.run_slot(1)
        assert controller.beliefs == uniform
    finally:
        controller.close()


def test_snapshot_validation_rejects_totals_order_and_digest_drift():
    beliefs = {
        ReplicaChoice(1, 1): (0.4, 0.3, 0.2, 0.1),
        ReplicaChoice(2, 1): (0.1, 0.2, 0.3, 0.4),
    }

    def receive(request: httpx.Request) -> httpx.Response:
        document = json.loads(request.content)
        canonical = build_canonical_posterior_update(
            run_id=document["run_id"],
            slot_id=document["slot_id"],
            choice=ReplicaChoice(document["stage"], document["replica"]),
            posterior=document["posterior"],
        )
        return httpx.Response(200, json=canonical.receipt.model_dump(mode="json"))

    client = HybridPosteriorMirrorHttpClient(
        "http://mirror.test",
        run_id="run-validation",
        transport=httpx.MockTransport(receive),
    )
    try:
        snapshot = client.mirror_slot(
            slot_id=3,
            beliefs_after=beliefs,
            updated_choices=tuple(beliefs),
        )
    finally:
        client.close()

    wrong_total = copy.deepcopy(snapshot)
    wrong_total["payload_bytes"]["posterior_vectors"] += 1
    with pytest.raises(ValueError, match="totals"):
        validate_hybrid_posterior_mirror_snapshot(wrong_total)

    wrong_order = copy.deepcopy(snapshot)
    wrong_order["updates"].reverse()
    with pytest.raises(ValueError, match="canonically ordered"):
        validate_hybrid_posterior_mirror_snapshot(wrong_order)

    wrong_digest = copy.deepcopy(snapshot)
    wrong_digest["updates"][0]["vector_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="canonical beliefs"):
        validate_hybrid_posterior_mirror_snapshot(
            wrong_digest,
            expected_slot_id=3,
            expected_beliefs=beliefs,
            expected_updated_choices=tuple(beliefs),
        )


def test_provenance_is_explicit_for_enabled_and_disabled_runs():
    disabled = posterior_mirror_provenance(False)
    enabled = posterior_mirror_provenance(True)
    assert disabled["transport"] == "none"
    assert enabled["transport"] == "http-pod-to-pod"
    assert validate_posterior_mirror_provenance(
        disabled, expected_enabled=False
    ) == disabled
    with pytest.raises(ValueError, match="drifted"):
        validate_posterior_mirror_provenance(enabled, expected_enabled=False)


def test_cli_is_default_off_and_accepts_only_explicit_zero_or_one():
    common = [
        "run",
        "--flow", "2",
        "--stage", "3",
        "--replica", "1",
        "--profile-seed", "7",
        "--max-iterations", "2",
    ]
    assert runner.parse_args(common).posterior_mirror == 0
    assert runner.parse_args([*common, "--posterior-mirror", "1"]).posterior_mirror == 1
    with pytest.raises(SystemExit):
        runner.parse_args([*common, "--posterior-mirror", "2"])


def test_receiver_manifest_is_worker_only_nonprivileged_and_default_unreferenced():
    manifest = runner.POSTERIOR_MIRROR_MANIFEST
    text = manifest.read_text(encoding="utf-8")
    assert text.count("kind: Service\n") == 1
    assert text.count("kind: Deployment\n") == 1
    assert 'ibg-hybrid.workload-node: "true"' in text
    assert "automountServiceAccountToken: false" in text
    assert "runAsNonRoot: true" in text
    assert "allowPrivilegeEscalation: false" in text
    assert 'drop: ["ALL"]' in text
    assert "privileged:" not in text
    assert "hostNetwork:" not in text
    assert "hostPID:" not in text
    assert "hostIPC:" not in text
    assert "affinity:" not in text
    assert "hostPath:" not in text
    assert 'requests: {cpu: 25m, memory: 64Mi}' in text
    assert f"image: {runner.SERVICE_IMAGE}" in text
    assert "python3\", \"-m\", \"uvicorn" in text
    base = (
        ROOT / "deploy/hybrid-kubernetes/kustomization.yaml"
    ).read_text(encoding="utf-8")
    assert "posterior-mirror.yaml" not in base


def test_all_retained_controller_jobs_expose_receiver_url_and_pod_run_identity():
    jobs = (
        ROOT / "deploy/hybrid-kubernetes/controller-job.yaml",
        ROOT / "deploy/hybrid-kubernetes/dynamic-controller-job.yaml",
        ROOT / "deploy/hybrid-kubernetes-phase4-small/controller-job.yaml",
        ROOT / "deploy/hybrid-kubernetes-phase6-3x3x2/controller-job.yaml",
        ROOT / "deploy/hybrid-kubernetes-phase7-3x3x2/controller-job.yaml",
        ROOT / "deploy/hybrid-kubernetes-phase7.5-3x3x2/controller-job.yaml",
        ROOT / "deploy/hybrid-kubernetes-phase8-gate1-4x3x2/controller-job.yaml",
    )
    for job in jobs:
        text = job.read_text(encoding="utf-8")
        assert "HYBRID_POSTERIOR_MIRROR_URL" in text
        assert "HYBRID_CONTROLLER_POD_UID" in text
        assert "fieldPath: metadata.uid" in text
        assert f'{runner.WORKLOAD_NODE_LABEL}: "true"' in text
    for job in (jobs[1], jobs[4], jobs[5]):
        assert "/app/IBG_Hybrid/posterior_mirror.py" in job.read_text(
            encoding="utf-8"
        )


def test_receiver_reconciliation_applies_only_when_enabled_and_deletes_when_disabled():
    calls = []

    def execute(command, capture_output):
        calls.append((command, capture_output))
        return ""

    runner._reconcile_posterior_mirror(execute, enabled=True)
    assert calls == [
        (
            runner._kubectl(
                "apply", "-f", str(runner.POSTERIOR_MIRROR_MANIFEST)
            ),
            False,
        ),
        (
            runner._kubectl(
                "rollout",
                "status",
                "-n",
                runner.HYBRID_NAMESPACE,
                runner.POSTERIOR_MIRROR_RESOURCE,
                "--timeout=120s",
            ),
            False,
        ),
    ]
    calls.clear()
    runner._reconcile_posterior_mirror(execute, enabled=False)
    assert calls == [
        (
            runner._kubectl(
                "delete",
                "deployment",
                "service",
                runner.POSTERIOR_MIRROR_NAME,
                "-n",
                runner.HYBRID_NAMESPACE,
                "--ignore-not-found",
                "--wait=true",
            ),
            False,
        )
    ]


def test_resource_preflight_adds_only_the_enabled_receiver_request():
    disabled = runner._validate_node_resource_capacity(
        _resource_execute,
        existing_replica_count=1,
        requested_replica_count=1,
        posterior_mirror_enabled=False,
    )
    enabled = runner._validate_node_resource_capacity(
        _resource_execute,
        existing_replica_count=1,
        requested_replica_count=1,
        posterior_mirror_enabled=True,
    )
    assert enabled.requested_cpu_milli - disabled.requested_cpu_milli == 25
    assert (
        enabled.requested_memory_bytes - disabled.requested_memory_bytes
        == 64 * 1024**2
    )
