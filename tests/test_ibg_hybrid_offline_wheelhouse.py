import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import hybrid_offline_wheelhouse as wheelhouse
from scripts import run_hybrid_kernel_phase4 as runner


ROOT = Path(__file__).resolve().parents[1]


def _stage_manifest_tree(root: Path) -> None:
    source = ROOT / "deploy" / "hybrid-kubernetes" / "wheel-manifests"
    target = root / "deploy" / "hybrid-kubernetes" / "wheel-manifests"
    target.mkdir(parents=True)
    for path in source.iterdir():
        shutil.copy2(path, target / path.name)


def _write_complete_wheelhouse(root: Path, image: str) -> Path:
    directory = root / ".offline-wheels" / "ibg-hybrid" / image
    directory.mkdir(parents=True)
    manifest = wheelhouse.load_manifest(image, root=root)
    for spec in manifest.wheels:
        (directory / spec.filename).write_bytes(b"test wheel")
    return directory


def test_versioned_wheel_manifests_and_locks_are_exact_and_isolated(tmp_path):
    _stage_manifest_tree(tmp_path)
    service = wheelhouse.load_manifest("service", root=tmp_path)
    controller = wheelhouse.load_manifest("controller", root=tmp_path)

    assert service.lock_filename == "requirements-service.lock"
    assert controller.lock_filename == "requirements-controller.lock"
    assert "uvicorn-0.51.0-py3-none-any.whl" in service.expected_filenames
    assert "uvicorn-0.51.0-py3-none-any.whl" not in controller.expected_filenames
    forbidden = {"scipy", "highs", "highspy", "ortools", "milp"}
    for manifest in (service, controller):
        assert not {
            spec.distribution.lower().replace("_", "-")
            for spec in manifest.wheels
        } & forbidden


def test_wheelhouse_validator_reports_each_missing_or_unexpected_wheel(tmp_path):
    _stage_manifest_tree(tmp_path)
    directory = _write_complete_wheelhouse(tmp_path, "service")
    missing = next(directory.glob("numpy-*.whl"))
    missing.unlink()
    (directory / "scipy-1.0.0-py3-none-any.whl").write_bytes(b"not allowed")

    with pytest.raises(wheelhouse.HybridWheelhouseError) as error:
        wheelhouse.validate_wheelhouse("service", root=tmp_path)

    message = str(error.value)
    assert "missing wheel: numpy-2.5.1" in message
    assert "unexpected wheels: scipy-1.0.0-py3-none-any.whl" in message


def test_wheelhouse_validator_rejects_a_recorded_digest_mismatch(tmp_path):
    _stage_manifest_tree(tmp_path)
    directory = _write_complete_wheelhouse(tmp_path, "controller")
    manifest_path = (
        tmp_path
        / "deploy"
        / "hybrid-kubernetes"
        / "wheel-manifests"
        / "controller.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["wheels"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(wheelhouse.HybridWheelhouseError, match="digest mismatch"):
        wheelhouse.validate_wheelhouse("controller", root=tmp_path, directory=directory)


def test_explicit_copy_stages_only_a_complete_supplied_wheel_set(tmp_path):
    _stage_manifest_tree(tmp_path)
    source = tmp_path / "supplied-service-wheels"
    source.mkdir()
    for spec in wheelhouse.load_manifest("service", root=tmp_path).wheels:
        (source / spec.filename).write_bytes(b"test wheel")

    destination = wheelhouse.copy_supplied_wheels(
        "service", source=source, root=tmp_path
    )

    assert destination == tmp_path / ".offline-wheels" / "ibg-hybrid" / "service"
    assert {path.name for path in destination.iterdir()} == set(
        wheelhouse.load_manifest("service", root=tmp_path).expected_filenames
    )


def test_normal_mode_validates_both_wheelhouses_before_cluster_or_docker(
    monkeypatch, capsys
):
    calls = []

    def fail_validation():
        calls.append("validate")
        raise RuntimeError("service wheel is missing")

    monkeypatch.setattr(runner, "_validate_offline_wheelhouses", fail_validation)
    commands = []
    with pytest.raises(RuntimeError, match="service wheel is missing"):
        runner.run_small(
            execute=lambda command, capture: commands.append(command) or ""
        )

    assert calls == ["validate"]
    assert commands == []
    assert capsys.readouterr().out.endswith(
        "Hybrid image mode: build offline from validated local wheelhouses\n"
    )


def test_skip_build_never_touches_wheelhouses_before_node_reuse(monkeypatch):
    monkeypatch.setattr(
        runner,
        "_validate_offline_wheelhouses",
        lambda: pytest.fail("--skip-build must not validate wheelhouses"),
    )
    commands = []

    with pytest.raises(RuntimeError, match="requires the existing persistent"):
        runner.run_small(
            skip_build=True,
            execute=lambda command, capture: commands.append(command) or "",
        )

    assert commands == [("kind", "get", "clusters")]


def test_validated_normal_build_keeps_network_disabled_and_builds_both_images(
    monkeypatch,
):
    commands = []
    monkeypatch.setattr(runner, "_validate_offline_wheelhouses", lambda: None)
    monkeypatch.setattr(runner, "_require_local_image", lambda execute, image: None)

    runner._build_images_offline(
        lambda command, capture: commands.append(command) or ""
    )

    assert len(commands) == 2
    assert {command[command.index("--tag") + 1] for command in commands} == {
        runner.SERVICE_IMAGE,
        runner.CONTROLLER_IMAGE,
    }
    assert all("--pull=false" in command and "--network=none" in command for command in commands)


def test_wheelhouse_helper_import_is_silent_and_file_safe(tmp_path):
    environment = {"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import scripts.hybrid_offline_wheelhouse",
        ],
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
