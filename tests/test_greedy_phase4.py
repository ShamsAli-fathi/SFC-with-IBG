from __future__ import annotations

from copy import deepcopy
import inspect
import json
import os
from pathlib import Path
import random
import shlex
import shutil
import subprocess
import sys

import numpy as np
import pytest

from Greedy.comparison import (
    CANONICAL_MATCHED_COMPARISON,
    GREEDY_PHASE4_HYBRID_AUDIT_HEAD,
    GREEDY_PHASE4_HYBRID_SOURCE_AUDIT,
)
from Greedy.contracts import GreedyConfiguration, ReplicaIdentity
from Greedy.kernel_infrastructure import (
    CONTROLLER_RESOURCES,
    FLOW_GENERATOR_RESOURCES,
    GREEDY_CONTROLLER_IMAGE,
    GREEDY_CONTROLLER_INPUT_CONFIG_MAP,
    GREEDY_NAMESPACE,
    GREEDY_RUNTIME_PROFILE_CONFIG_MAP,
    GREEDY_SERVICE_IMAGE,
    GREEDY_STATIC_INPUT_VERSION,
    GREEDY_WORKLOAD_NODE_LABEL,
    PRIVATE_PROCESSOR_RESOURCES,
    PUBLIC_FORWARDER_RESOURCES,
    GreedyInfrastructureError,
    GreedyServingReadiness,
    GreedyWorkerAllocatable,
    parse_resource_documents,
    render_controller_job,
    render_kind_configuration,
    render_long_running_resources,
    render_resource_documents,
    require_worker_resources,
    static_deployment_input_from_mapping,
    validate_long_running_resources,
)
from Greedy.kernel_processor_service import processor_config_from_env
from Greedy.kernel_runtime_profiles import (
    GREEDY_KERNEL_RUNTIME_PROFILE_VERSION,
    load_runtime_profile_document,
    runtime_profile_document_to_mapping,
)
from scripts import greedy_offline_wheelhouse as wheelhouse
from scripts.render_greedy_kubernetes import render_input


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "greedy-kubernetes"
CANONICAL_EXAMPLE = DEPLOY / "examples" / "canonical-10x3x5.json"


def deployment_mapping(*, flows=7, stages=4, replicas=3):
    return {
        "contract_version": GREEDY_STATIC_INPUT_VERSION,
        "source_identity": f"test-explicit-{flows}x{stages}x{replicas}",
        "configuration": {
            "num_flows": flows,
            "num_stages": stages,
            "num_replicas": replicas,
        },
        "experiment_id": 1,
        "root_seed": 2050,
        "profile_seed": 17,
        "max_iterations": 9,
        "first_slot_id": 1,
        "profiles": [
            {
                "stage": stage,
                "replica": replica,
                "hidden_state": ((stage + replica - 2) % 4) + 1,
                "observation_seed": 10_000 + stage * 100 + replica,
            }
            for stage in range(1, stages + 1)
            for replica in range(1, replicas + 1)
        ],
    }


def ready_for(deployment):
    configuration = deployment.configuration
    return GreedyServingReadiness(
        configuration=configuration,
        ready_identities=tuple(
            ReplicaIdentity(stage, replica)
            for stage in configuration.stages
            for replica in configuration.replica_ids
        ),
        flow_generator_ready=True,
    )


def by_kind(resources, kind):
    return tuple(resource for resource in resources if resource["kind"] == kind)


def test_static_input_requires_explicit_complete_dimensions_and_profiles():
    value = deployment_mapping()
    for field in ("num_flows", "num_stages", "num_replicas"):
        incomplete = deepcopy(value)
        del incomplete["configuration"][field]
        with pytest.raises(ValueError, match="explicit N, K, and M"):
            static_deployment_input_from_mapping(incomplete)

    invalid = deepcopy(value)
    invalid["configuration"]["num_stages"] = 1
    invalid["profiles"] = invalid["profiles"][:3]
    with pytest.raises(ValueError, match="at least 2"):
        static_deployment_input_from_mapping(invalid)

    missing_profile = deepcopy(value)
    missing_profile["profiles"].pop()
    with pytest.raises(ValueError, match="canonical contiguous identities"):
        static_deployment_input_from_mapping(missing_profile)

    assert inspect.signature(static_deployment_input_from_mapping).parameters[
        "value"
    ].default is inspect.Parameter.empty


def test_runtime_profile_round_trip_and_processor_private_mount(tmp_path):
    deployment = static_deployment_input_from_mapping(
        deployment_mapping(flows=4, stages=3, replicas=2)
    )
    runtime_mapping = runtime_profile_document_to_mapping(
        deployment.runtime_profiles
    )
    assert runtime_mapping["contract_version"] == GREEDY_KERNEL_RUNTIME_PROFILE_VERSION
    path = tmp_path / "runtime-profiles.json"
    path.write_text(json.dumps(runtime_mapping), encoding="utf-8")

    loaded = load_runtime_profile_document(path)
    assert loaded == deployment.runtime_profiles
    assert loaded.fingerprint == deployment.runtime_profiles.fingerprint
    config = processor_config_from_env(
        {
            "STAGE": "2",
            "POD_NAME": "greedy-stage-2-1",
            "GREEDY_RUNTIME_PROFILES_PATH": str(path),
        }
    )
    expected = loaded.profile_by_identity()[ReplicaIdentity(2, 2)]
    assert (config.stage, config.replica_id, config.pod_name) == (
        2,
        2,
        "greedy-stage-2-1",
    )
    assert config.state == expected.hidden_state
    assert config.observation_seed == expected.observation_seed
    assert config.capacity == 1


def test_arbitrary_topology_render_is_complete_deterministic_and_parseable():
    deployment = static_deployment_input_from_mapping(deployment_mapping())
    resources = render_long_running_resources(deployment)
    rendered = render_resource_documents(resources)

    assert resources == render_long_running_resources(deployment)
    assert rendered == render_resource_documents(resources)
    assert parse_resource_documents(rendered) == resources
    assert len(by_kind(resources, "StatefulSet")) == 4
    assert len(by_kind(resources, "Service")) == 5
    assert len(by_kind(resources, "Deployment")) == 1
    assert not by_kind(resources, "Job")
    assert tuple(
        item["metadata"]["name"] for item in by_kind(resources, "StatefulSet")
    ) == tuple(f"greedy-stage-{stage}" for stage in range(1, 5))

    for stateful_set in by_kind(resources, "StatefulSet"):
        assert stateful_set["spec"]["replicas"] == 3
        labels = stateful_set["spec"]["template"]["metadata"]["labels"]
        assert labels["greedy.max-assigned-flows"] == "3"
        pod = stateful_set["spec"]["template"]["spec"]
        assert pod["automountServiceAccountToken"] is False
        assert pod["nodeSelector"] == {GREEDY_WORKLOAD_NODE_LABEL: "true"}
        assert [container["name"] for container in pod["containers"]] == [
            "private-processor",
            "public-forwarder",
        ]
        assert pod["containers"][0]["ports"][0]["containerPort"] == 8081
        assert pod["containers"][1]["ports"][0]["containerPort"] == 8080
        assert pod["containers"][1]["command"][-4:] == [
            "--workers",
            "2",
            "--timeout-keep-alive",
            "30",
        ]

    text = rendered.lower()
    assert "ibg-hybrid" not in text
    assert "milp-testbed" not in text
    assert '"name": "ibg-testbed"' not in text


def test_canonical_example_is_explicit_10x3x5_not_a_default():
    mapping = json.loads(CANONICAL_EXAMPLE.read_text(encoding="utf-8"))
    deployment = static_deployment_input_from_mapping(mapping)
    assert deployment.configuration == GreedyConfiguration(10, 3, 5)
    assert len(deployment.runtime_profiles.profiles) == 15
    resources = render_long_running_resources(deployment)
    assert len(by_kind(resources, "StatefulSet")) == 3
    assert all(item["spec"]["replicas"] == 5 for item in by_kind(resources, "StatefulSet"))
    assert deployment.configuration.admission_capacity_per_replica == 2
    assert render_input(CANONICAL_EXAMPLE, "long-running") == render_resource_documents(resources)


def test_rbac_token_mounts_security_and_configmap_separation_are_narrow():
    deployment = static_deployment_input_from_mapping(deployment_mapping())
    resources = render_long_running_resources(deployment)
    role = by_kind(resources, "Role")[0]
    assert role["metadata"]["namespace"] == GREEDY_NAMESPACE
    assert role["rules"] == [
        {"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list"]}
    ]
    assert not by_kind(resources, "ClusterRole")

    pods = [
        item["spec"]["template"]["spec"]
        for item in (*by_kind(resources, "StatefulSet"), *by_kind(resources, "Deployment"))
    ]
    for pod in pods:
        assert pod["automountServiceAccountToken"] is False
        assert pod["securityContext"]["runAsNonRoot"] is True
        assert pod["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
        for container in pod["containers"]:
            security = container["securityContext"]
            assert security["allowPrivilegeEscalation"] is False
            assert security["readOnlyRootFilesystem"] is True
            assert security["capabilities"] == {"drop": ["ALL"]}

    config_maps = {
        item["metadata"]["name"]: item for item in by_kind(resources, "ConfigMap")
    }
    runtime_text = config_maps[GREEDY_RUNTIME_PROFILE_CONFIG_MAP]["data"][
        "runtime-profiles.json"
    ]
    controller_text = config_maps[GREEDY_CONTROLLER_INPUT_CONFIG_MAP]["data"][
        "controller-inputs.json"
    ]
    assert "hidden_state" in runtime_text and "observation_seed" in runtime_text
    assert "hidden_state" not in controller_text
    assert "observation_seed" not in controller_text
    assert "belief" not in controller_text


def test_exact_hybrid_matched_resources_and_phase4_audit_are_frozen():
    assert PRIVATE_PROCESSOR_RESOURCES.kubernetes() == {
        "requests": {"cpu": "50m", "memory": "128Mi"},
        "limits": {"cpu": "1", "memory": "768Mi"},
    }
    assert PUBLIC_FORWARDER_RESOURCES.kubernetes() == {
        "requests": {"cpu": "25m", "memory": "128Mi"},
        "limits": {"cpu": "1", "memory": "256Mi"},
    }
    assert FLOW_GENERATOR_RESOURCES.kubernetes() == {
        "requests": {"cpu": "50m", "memory": "128Mi"},
        "limits": {"cpu": "1", "memory": "768Mi"},
    }
    assert CONTROLLER_RESOURCES.kubernetes() == {
        "requests": {"cpu": "2", "memory": "256Mi"},
        "limits": {"cpu": "4", "memory": "1Gi"},
    }
    comparison = CANONICAL_MATCHED_COMPARISON
    assert comparison.matched_value("private_processor_request") == "50m/128Mi"
    assert comparison.matched_value("public_forwarder_request") == "25m/128Mi"
    assert comparison.matched_value("flow_generator_request") == "50m/128Mi"
    assert comparison.matched_value("controller_request") == "2CPU/256Mi"
    assert GREEDY_PHASE4_HYBRID_AUDIT_HEAD == "f2e0065204570d9631f26953c94729b451ff92b5"
    assert len(GREEDY_PHASE4_HYBRID_SOURCE_AUDIT) == 10
    assert {item.disposition for item in GREEDY_PHASE4_HYBRID_SOURCE_AUDIT} == {
        "reuse",
        "adapt",
    }


def test_controller_job_requires_exact_ready_serving_and_stays_separate():
    deployment = static_deployment_input_from_mapping(deployment_mapping())
    with pytest.raises(GreedyInfrastructureError, match="requires completed serving readiness"):
        render_controller_job(deployment, None)
    with pytest.raises(GreedyInfrastructureError, match="exact canonical Ready"):
        GreedyServingReadiness(
            deployment.configuration,
            ready_for(deployment).ready_identities[:-1],
            True,
        )
    with pytest.raises(GreedyInfrastructureError, match="Ready flow generator"):
        GreedyServingReadiness(
            deployment.configuration,
            ready_for(deployment).ready_identities,
            False,
        )

    job = render_controller_job(deployment, ready_for(deployment))
    assert job["kind"] == "Job"
    pod = job["spec"]["template"]["spec"]
    assert pod["serviceAccountName"] == "greedy-controller"
    assert pod["automountServiceAccountToken"] is True
    assert pod["nodeSelector"] == {GREEDY_WORKLOAD_NODE_LABEL: "true"}
    container = pod["containers"][0]
    assert container["image"] == GREEDY_CONTROLLER_IMAGE
    assert container["resources"] == CONTROLLER_RESOURCES.kubernetes()
    job_text = json.dumps(job)
    assert GREEDY_RUNTIME_PROFILE_CONFIG_MAP not in job_text
    assert "hidden_state" not in job_text
    assert "observation_seed" not in job_text


def test_canonical_validation_rejects_namespace_image_rbac_node_resource_mount_and_stage_drift():
    deployment = static_deployment_input_from_mapping(deployment_mapping())
    canonical = render_long_running_resources(deployment)

    mutations = []
    changed = deepcopy(canonical)
    changed[0]["metadata"]["name"] = "ibg-hybrid-testbed"
    mutations.append(changed)
    changed = deepcopy(canonical)
    by_kind(changed, "Deployment")[0]["spec"]["template"]["spec"]["containers"][0]["image"] = "foreign:latest"
    mutations.append(changed)
    changed = deepcopy(canonical)
    by_kind(changed, "Role")[0]["rules"][0]["verbs"].append("watch")
    mutations.append(changed)
    changed = deepcopy(canonical)
    by_kind(changed, "StatefulSet")[0]["spec"]["template"]["spec"]["nodeSelector"] = {}
    mutations.append(changed)
    changed = deepcopy(canonical)
    by_kind(changed, "StatefulSet")[0]["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"] = "75m"
    mutations.append(changed)
    changed = deepcopy(canonical)
    by_kind(changed, "StatefulSet")[0]["spec"]["template"]["spec"]["containers"][0]["volumeMounts"] = []
    mutations.append(changed)
    changed = tuple(
        item
        for item in deepcopy(canonical)
        if item.get("metadata", {}).get("name") != "greedy-stage-2"
    )
    mutations.append(changed)

    for resources in mutations:
        with pytest.raises(GreedyInfrastructureError, match="canonical Greedy render"):
            validate_long_running_resources(deployment, resources)


def test_kind_topology_and_worker_request_preflight_are_exact():
    kind = render_kind_configuration()
    assert kind["nodes"] == [
        {"role": "control-plane"},
        {"role": "worker", "labels": {GREEDY_WORKLOAD_NODE_LABEL: "true"}},
    ]
    assert json.loads((DEPLOY / "kind-config.yaml").read_text()) == kind

    configuration = GreedyConfiguration(10, 3, 5)
    exact = GreedyWorkerAllocatable(cpu_millicores=3175, memory_mib=4224)
    required = require_worker_resources(configuration, exact)
    assert (required.cpu_millicores, required.memory_mib, required.serving_pods) == (
        3175,
        4224,
        15,
    )
    with pytest.raises(GreedyInfrastructureError, match="CPU"):
        require_worker_resources(
            configuration,
            GreedyWorkerAllocatable(3174, 5000),
        )
    with pytest.raises(GreedyInfrastructureError, match="memory"):
        require_worker_resources(
            configuration,
            GreedyWorkerAllocatable(4000, 4223),
        )


def docker_sources(name):
    sources = []
    for line in (DEPLOY / name).read_text().splitlines():
        if line.startswith("COPY "):
            fields = shlex.split(line)
            sources.extend(fields[1:-1])
    return set(sources)


def requirements(name):
    return {
        line.split("<", 1)[0].split(">", 1)[0].split("=", 1)[0].lower()
        for line in (DEPLOY / name).read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }


def test_dockerfiles_are_greedy_owned_offline_nonroot_and_policy_separated():
    assert requirements("requirements-service.txt") == {
        "numpy",
        "fastapi",
        "pydantic",
        "httpx",
        "uvicorn",
    }
    assert requirements("requirements-controller.txt") == {
        "numpy",
        "fastapi",
        "pydantic",
        "httpx",
    }
    service_sources = docker_sources("Dockerfile.service")
    controller_sources = docker_sources("Dockerfile.controller")
    assert "Greedy/kernel_flow_generator.py" in service_sources
    assert "Greedy/kernel_controller.py" not in service_sources
    assert "Greedy/policy.py" not in service_sources
    assert "Greedy/policy.py" in controller_sources
    assert "Greedy/kernel_controller.py" in controller_sources
    assert "Greedy/kernel_flow_generator.py" not in controller_sources
    assert all("IBG_Hybrid" not in source for source in service_sources | controller_sources)
    assert all(
        source not in service_sources | controller_sources
        for source in (
            "Greedy/main.py",
            "Greedy/budgeted.py",
            "Greedy/header.py",
            "Greedy/oracle.py",
            "Greedy/kernel_oracle.py",
        )
    )
    for name, cache in (
        ("Dockerfile.service", ".offline-wheels/greedy/service/"),
        ("Dockerfile.controller", ".offline-wheels/greedy/controller/"),
    ):
        text = (DEPLOY / name).read_text()
        assert "--no-index" in text
        assert "--find-links=/opt/greedy-wheels" in text
        assert cache in text
        assert "USER 10001:10001" in text
        assert "curl" not in text and "wget" not in text
    assert "uvicorn" not in (DEPLOY / "requirements-controller.txt").read_text().lower()


def materialize_docker_copy_sources(dockerfile, image_root):
    for line in (DEPLOY / dockerfile).read_text().splitlines():
        if not line.startswith("COPY "):
            continue
        fields = shlex.split(line)
        destination = fields[-1]
        for source in fields[1:-1]:
            if source.startswith(".offline-wheels/") or source.endswith((".txt", ".lock")):
                continue
            destination_path = Path(destination.removeprefix("/app/"))
            if destination.endswith("/"):
                destination_path /= Path(source).name
            target = image_root / destination_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source, target)


@pytest.mark.parametrize(
    ("dockerfile", "modules", "forbidden"),
    (
        (
            "Dockerfile.service",
            (
                "Greedy.kernel_processor_service",
                "Greedy.kernel_route_forwarder_service",
                "Greedy.kernel_flow_generator",
            ),
            ("Greedy.policy", "Greedy.kernel_controller", "IBG_Hybrid", "MILP"),
        ),
        (
            "Dockerfile.controller",
            ("Greedy.kernel_controller_service",),
            (
                "Greedy.kernel_processor_service",
                "Greedy.kernel_flow_generator",
                "IBG_Hybrid",
                "MILP",
            ),
        ),
    ),
)
def test_isolated_image_source_inventories_import_silently(
    tmp_path,
    dockerfile,
    modules,
    forbidden,
):
    image_root = tmp_path / "image"
    workdir = tmp_path / "work"
    workdir.mkdir()
    materialize_docker_copy_sources(dockerfile, image_root)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = f"{image_root}:{image_root / 'IBG'}"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        ";".join(f"import {module}" for module in modules)
        + ";import sys;assert all(name not in sys.modules for name in "
        + repr(forbidden)
        + ")"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=workdir,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert list(workdir.iterdir()) == []


def test_greedy_wheel_manifests_are_exact_versioned_and_solver_free(tmp_path):
    service = wheelhouse.load_manifest("service")
    controller = wheelhouse.load_manifest("controller")
    assert "uvicorn-0.51.0-py3-none-any.whl" in service.expected_filenames
    assert "uvicorn-0.51.0-py3-none-any.whl" not in controller.expected_filenames
    forbidden = {"scipy", "highs", "highspy", "ortools", "milp", "pandas"}
    for manifest in (service, controller):
        assert not {
            spec.distribution.lower().replace("_", "-")
            for spec in manifest.wheels
        } & forbidden

    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    for spec in service.wheels:
        (wheel_dir / spec.filename).write_bytes(b"fixture")
    wheelhouse.validate_wheelhouse("service", directory=wheel_dir)
    next(wheel_dir.glob("numpy-*.whl")).unlink()
    (wheel_dir / "scipy-1.0.0-py3-none-any.whl").write_bytes(b"forbidden")
    with pytest.raises(wheelhouse.GreedyWheelhouseError) as error:
        wheelhouse.validate_wheelhouse("service", directory=wheel_dir)
    assert "missing wheel: numpy-2.5.1" in str(error.value)
    assert "unexpected wheels: scipy-1.0.0-py3-none-any.whl" in str(error.value)


def test_phase4_imports_and_renderer_are_silent_rng_neutral_and_file_free(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import random,numpy as np; random.seed(84); np.random.seed(48); "
        "p=random.getstate(); n=np.random.get_state(); "
        "import Greedy.kernel_runtime_profiles,Greedy.kernel_infrastructure; "
        "import scripts.greedy_offline_wheelhouse,scripts.render_greedy_kubernetes; "
        "assert random.getstate()==p; a=np.random.get_state(); "
        "assert a[0]==n[0] and np.array_equal(a[1],n[1]) and a[2:]==n[2:]"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_phase4_sources_do_not_invoke_cluster_or_container_tools():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "Greedy" / "kernel_infrastructure.py",
            ROOT / "scripts" / "render_greedy_kubernetes.py",
            ROOT / "scripts" / "greedy_offline_wheelhouse.py",
        )
    ).lower()
    assert "subprocess" not in source
    assert '("docker",' not in source and '["docker"' not in source
    assert '("kubectl",' not in source and '["kubectl"' not in source
    assert '("kind",' not in source and '["kind"' not in source
    assert "--policy" not in source
    assert "mc-workers" not in source
    assert "processpool" not in source
