import importlib.util
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

from IBG_Hybrid.kernel_infrastructure_contract import (
    DEFAULT_HYBRID_KERNEL_IMAGE_OWNERSHIP,
)


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "hybrid-kubernetes"


SERVICE_COPY_MAP = {
    "IBG/datapath.py": "IBG/datapath.py",
    "IBG/latency_model.py": "IBG/latency_model.py",
    "testbed/__init__.py": "testbed/__init__.py",
    "testbed/profiles.py": "testbed/profiles.py",
    "testbed/cnf_service.py": "testbed/cnf_service.py",
    "testbed/route_forwarder.py": "testbed/route_forwarder.py",
    "deploy/hybrid-kubernetes/service-package-init.py": "IBG_Hybrid/__init__.py",
    "deploy/hybrid-kubernetes/image-stage-budget.py": "IBG_Hybrid/budgeted.py",
    "IBG_Hybrid/contracts.py": "IBG_Hybrid/contracts.py",
    "IBG_Hybrid/kernel_infrastructure_contract.py": (
        "IBG_Hybrid/kernel_infrastructure_contract.py"
    ),
    "IBG_Hybrid/kernel_runtime_profiles.py": (
        "IBG_Hybrid/kernel_runtime_profiles.py"
    ),
    "IBG_Hybrid/kernel_route_contracts.py": "IBG_Hybrid/kernel_route_contracts.py",
    "IBG_Hybrid/kernel_route_execution.py": "IBG_Hybrid/kernel_route_execution.py",
    "IBG_Hybrid/kernel_route_forwarder.py": "IBG_Hybrid/kernel_route_forwarder.py",
    "IBG_Hybrid/kernel_processor_service.py": (
        "IBG_Hybrid/kernel_processor_service.py"
    ),
    "IBG_Hybrid/kernel_route_forwarder_service.py": (
        "IBG_Hybrid/kernel_route_forwarder_service.py"
    ),
    "IBG_Hybrid/kernel_flow_generator.py": "IBG_Hybrid/kernel_flow_generator.py",
}


CONTROLLER_COPY_MAP = {
    "IBG/datapath.py": "IBG/datapath.py",
    "IBG/latency_model.py": "IBG/latency_model.py",
    "IBG/learning.py": "IBG/learning.py",
    "IBG/outcome_latency.py": "IBG/outcome_latency.py",
    "deploy/hybrid-kubernetes/controller-exact-header.py": "IBG/header.py",
    "deploy/hybrid-kubernetes/controller-exact-report.py": "IBG/report.py",
    "testbed/__init__.py": "testbed/__init__.py",
    "testbed/profiles.py": "testbed/profiles.py",
    "testbed/cnf_service.py": "testbed/cnf_service.py",
    "testbed/route_forwarder.py": "testbed/route_forwarder.py",
    "deploy/hybrid-kubernetes/controller-package-init.py": (
        "IBG_Hybrid/__init__.py"
    ),
    "deploy/hybrid-kubernetes/image-stage-budget.py": "IBG_Hybrid/budgeted.py",
    "IBG_Hybrid/contracts.py": "IBG_Hybrid/contracts.py",
    "IBG_Hybrid/expected_utility.py": "IBG_Hybrid/expected_utility.py",
    "IBG_Hybrid/phase0_contract.py": "IBG_Hybrid/phase0_contract.py",
    "IBG_Hybrid/policy.py": "IBG_Hybrid/policy.py",
    "IBG_Hybrid/slot_contracts.py": "IBG_Hybrid/slot_contracts.py",
    "IBG_Hybrid/simulation.py": "IBG_Hybrid/simulation.py",
    "IBG_Hybrid/runner.py": "IBG_Hybrid/runner.py",
    "IBG_Hybrid/console_output.py": "IBG_Hybrid/console_output.py",
    "IBG_Hybrid/kernel_infrastructure_contract.py": (
        "IBG_Hybrid/kernel_infrastructure_contract.py"
    ),
    "IBG_Hybrid/kernel_route_contracts.py": "IBG_Hybrid/kernel_route_contracts.py",
    "IBG_Hybrid/kernel_controller_config.py": (
        "IBG_Hybrid/kernel_controller_config.py"
    ),
    "IBG_Hybrid/kernel_kubernetes_discovery.py": (
        "IBG_Hybrid/kernel_kubernetes_discovery.py"
    ),
    "IBG_Hybrid/kernel_controller.py": "IBG_Hybrid/kernel_controller.py",
    "IBG_Hybrid/kernel_controller_service.py": (
        "IBG_Hybrid/kernel_controller_service.py"
    ),
    "IBG_Hybrid/kernel_phase4_validation.py": (
        "IBG_Hybrid/kernel_phase4_validation.py"
    ),
    "IBG_Hybrid/kernel_controller_cli.py": (
        "IBG_Hybrid/kernel_controller_cli.py"
    ),
}


def requirements(name):
    return {
        line.split("<", 1)[0].split(">", 1)[0].split("=", 1)[0].lower()
        for line in (DEPLOY / name).read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def docker_copy_sources(name):
    sources = []
    for line in (DEPLOY / name).read_text().splitlines():
        if line.startswith("COPY "):
            fields = shlex.split(line)
            sources.extend(fields[1:-1])
    return set(sources)


def materialize(root, copy_map):
    for source, destination in copy_map.items():
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, target)


def run_isolated_import(image_root, workdir, modules, assertions):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = f"{image_root}:{image_root / 'IBG'}"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    module_imports = "; ".join(f"import {name}" for name in modules)
    code = (
        "import random, sys, numpy as np; "
        "random.seed(8103); np.random.seed(3108); "
        "p=random.getstate(); n=np.random.get_state(); "
        f"{module_imports}; "
        "assert random.getstate()==p; a=np.random.get_state(); "
        "assert a[0]==n[0] and np.array_equal(a[1],n[1]) and a[2:]==n[2:]; "
        f"{assertions}"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=workdir,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def test_image_names_and_manifest_references_remain_phase0_owned():
    ownership = DEFAULT_HYBRID_KERNEL_IMAGE_OWNERSHIP
    assert ownership.service_image == "ibg-hybrid-testbed:kernel-service-v1"
    assert ownership.controller_image == "ibg-hybrid-testbed:kernel-controller-v1"
    manifests = "\n".join(
        (DEPLOY / name).read_text()
        for name in ("replicas.yaml", "flow-generator.yaml", "controller-job.yaml")
    )
    assert manifests.count(ownership.service_image) == 7
    assert manifests.count(ownership.controller_image) == 1


def test_service_dependency_and_source_inventory_is_lean():
    assert requirements("requirements-service.txt") == {
        "numpy",
        "fastapi",
        "httpx",
        "uvicorn",
        "pydantic",
    }
    sources = docker_copy_sources("Dockerfile.service")
    assert sources == set(SERVICE_COPY_MAP) | {
        "deploy/hybrid-kubernetes/requirements-service.txt",
        "deploy/hybrid-kubernetes/wheel-manifests/requirements-service.lock",
        ".offline-wheels/ibg-hybrid/service/",
    }
    forbidden = {
        "IBG_Hybrid/policy.py",
        "IBG_Hybrid/runner.py",
        "IBG_Hybrid/simulation.py",
        "IBG_Hybrid/report.py",
        "IBG_Hybrid/kernel_controller.py",
        "IBG_Hybrid/kernel_controller_service.py",
        "IBG_Hybrid/kernel_kubernetes_discovery.py",
    }
    assert sources.isdisjoint(forbidden)
    assert not any(source.startswith(("IBG/claude", "MILP/")) for source in sources)
    dependency_text = (DEPLOY / "requirements-service.txt").read_text().lower()
    assert all(
        name not in dependency_text
        for name in ("scipy", "highs", "ortools", "pandas")
    )
    dockerignore = (ROOT / ".dockerignore").read_text()
    for source in sources:
        if source.startswith("deploy/hybrid-kubernetes/"):
            assert f"!{source}" in dockerignore


def test_controller_dependency_and_source_inventory_owns_policy_learning_and_mc():
    assert requirements("requirements-controller.txt") == {
        "numpy",
        "fastapi",
        "httpx",
        "pydantic",
    }
    sources = docker_copy_sources("Dockerfile.controller")
    assert sources == set(CONTROLLER_COPY_MAP) | {
        "deploy/hybrid-kubernetes/requirements-controller.txt",
        "deploy/hybrid-kubernetes/wheel-manifests/requirements-controller.lock",
        ".offline-wheels/ibg-hybrid/controller/",
    }
    assert {
        "IBG_Hybrid/policy.py",
        "IBG_Hybrid/runner.py",
        "IBG_Hybrid/kernel_controller.py",
        "IBG_Hybrid/kernel_kubernetes_discovery.py",
        "IBG/learning.py",
        "IBG/outcome_latency.py",
    }.issubset(sources)
    assert not any(source.startswith("MILP/") for source in sources)
    assert all(
        source not in sources
        for source in (
            "IBG_Hybrid/kernel_processor_service.py",
            "IBG_Hybrid/kernel_route_forwarder_service.py",
            "IBG_Hybrid/kernel_flow_generator.py",
        )
    )
    dockerfile = (DEPLOY / "Dockerfile.controller").read_text().lower()
    dependencies = (DEPLOY / "requirements-controller.txt").read_text().lower()
    assert "uvicorn" not in dependencies
    assert "scipy" not in dependencies
    assert "highs" not in dependencies
    assert "ortools" not in dependencies
    assert "ibg_hybrid.kernel_controller_service" in dockerfile


def test_hybrid_dockerfiles_install_only_from_the_local_wheelhouse():
    for name, image in (
        ("Dockerfile.service", "service"),
        ("Dockerfile.controller", "controller"),
    ):
        dockerfile = (DEPLOY / name).read_text(encoding="utf-8").lower()
        assert "--no-index" in dockerfile
        assert "--find-links=/opt/ibg-hybrid-wheels" in dockerfile
        assert f".offline-wheels/ibg-hybrid/{image}/" in dockerfile
        assert "curl" not in dockerfile
        assert "wget" not in dockerfile
        assert "pip install --no-cache-dir -r" not in dockerfile


def test_service_image_package_imports_are_isolated_safe_and_file_free(tmp_path):
    image_root = tmp_path / "service-image"
    workdir = tmp_path / "service-work"
    workdir.mkdir()
    materialize(image_root, SERVICE_COPY_MAP)
    completed = run_isolated_import(
        image_root,
        workdir,
        (
            "IBG_Hybrid.kernel_processor_service",
            "IBG_Hybrid.kernel_route_forwarder_service",
            "IBG_Hybrid.kernel_flow_generator",
        ),
        (
            "assert all(name not in sys.modules for name in "
            "['IBG_Hybrid.policy','IBG_Hybrid.runner',"
            "'IBG_Hybrid.kernel_controller','pandas','scipy','ortools','MILP'])"
        ),
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert list(workdir.iterdir()) == []
    assert not (image_root / "MILP").exists()
    assert not (image_root / "IBG_Hybrid" / "policy.py").exists()


def test_controller_image_package_imports_policy_learning_and_manual_mc_only(
    tmp_path,
):
    image_root = tmp_path / "controller-image"
    workdir = tmp_path / "controller-work"
    workdir.mkdir()
    materialize(image_root, CONTROLLER_COPY_MAP)
    completed = run_isolated_import(
        image_root,
        workdir,
        (
            "IBG_Hybrid.kernel_controller_service",
            "IBG_Hybrid.kernel_controller_cli",
        ),
        (
            "from IBG_Hybrid.policy import IBGHybridPolicy, "
            "HybridMonteCarloDecision; "
            "from IBG_Hybrid.runner import HYBRID_SLOT_POLICY_MC; "
            "assert HYBRID_SLOT_POLICY_MC=='mc'; "
            "assert all(name not in sys.modules for name in "
            "['IBG_Hybrid.kernel_processor_service',"
            "'IBG_Hybrid.kernel_route_forwarder_service',"
            "'IBG_Hybrid.kernel_flow_generator','pandas','scipy','ortools','MILP',"
            "'uvicorn'])"
        ),
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert list(workdir.iterdir()) == []
    assert (image_root / "IBG_Hybrid" / "policy.py").is_file()
    assert (image_root / "IBG" / "learning.py").is_file()
    assert not (image_root / "MILP").exists()


def test_image_stage_budget_matches_frozen_hybrid_contract():
    shim = load_module("phase3_stage_budget", DEPLOY / "image-stage-budget.py")
    assert shim.require_hybrid_stage_budget(2) == 2
    with pytest.raises(ValueError, match="exactly L=2"):
        shim.require_hybrid_stage_budget(3)
    with pytest.raises(TypeError, match="integer"):
        shim.require_hybrid_stage_budget(True)


def test_controller_exact_learning_metric_overlay_matches_frozen_functions():
    import header as exact_header
    from IBG.report import SLA_v as exact_sla

    lean_header = load_module(
        "phase3_exact_header", DEPLOY / "controller-exact-header.py"
    )
    lean_report = load_module(
        "phase3_exact_report", DEPLOY / "controller-exact-report.py"
    )
    constructor = dict(
        stage=1,
        replica=1,
        belief=[0.25, 0.25, 0.25, 0.25],
        delay=25,
        cost=1.0,
        gamma=0.0,
        state=1,
        capacity=5,
    )
    exact_replica = exact_header.Replica(**constructor)
    lean_replica = lean_header.Replica(**constructor)
    likelihood = (0.1, 0.2, 0.3, 0.4)
    assert lean_replica.utility_kernel(2, 27.5) == exact_replica.utility_kernel(2, 27.5)
    exact_local = exact_replica.local_update(likelihood, 31.5)
    lean_local = lean_replica.local_update(likelihood, 31.5)
    assert lean_local == exact_local
    exact_replica.aggregation([exact_local])
    lean_replica.aggregation([lean_local])
    assert lean_replica.belief == exact_replica.belief
    assert lean_header.is_equilibrium({1: lean_replica}, [lean_replica.belief]) == (
        exact_header.is_equilibrium({1: exact_replica}, [exact_replica.belief])
    )
    exact_values = {1: [3.5], 2: [4.5]}
    lean_values = {1: [3.5], 2: [4.5]}
    assert lean_header.jain_index(lean_values, 8.0) == exact_header.jain_index(
        exact_values, 8.0
    )
    latencies = {1: 109.9, 2: 110.1}
    assert lean_report.SLA_v(latencies, 110.0) == exact_sla(latencies, 110.0)


def test_controller_never_receives_runtime_profile_or_hidden_state_mount():
    controller = (DEPLOY / "controller-job.yaml").read_text().lower()
    assert "runtime-profile" not in controller
    assert "hidden_state" not in controller
    assert "belief" not in controller
    assert "image: ibg-hybrid-testbed:kernel-controller-v1" in controller


def test_workers_ports_keepalive_probes_and_resources_remain_phase2_values():
    replicas = (DEPLOY / "replicas.yaml").read_text()
    assert replicas.count("kind: StatefulSet") == 3
    assert replicas.count('"--port", "8081"') == 3
    assert replicas.count('"--port", "8080", "--workers", "2"') == 3
    assert replicas.count('"--timeout-keep-alive", "30"') == 3
    assert replicas.count("requests: {cpu: 50m, memory: 128Mi}") == 3
    assert replicas.count('limits: {cpu: "1", memory: 768Mi}') == 3
    assert replicas.count("requests: {cpu: 25m, memory: 128Mi}") == 3
    assert replicas.count('limits: {cpu: "1", memory: 256Mi}') == 3
    assert replicas.count("httpGet: {path: /warmup, port: processor}") == 3
    assert replicas.count("httpGet: {path: /health, port: processor}") == 3
    assert replicas.count("http://127.0.0.1:8081") == 3
    assert replicas.count('value: "30"') == 3
    assert "64Mi" not in replicas
