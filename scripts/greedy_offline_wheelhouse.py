#!/usr/bin/env python3
"""Validate Greedy image wheelhouses without downloading packages."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
IMAGE_NAMES = ("service", "controller")
FORBIDDEN_DISTRIBUTIONS = frozenset(
    {"milp", "scipy", "highs", "highspy", "ortools", "pandas"}
)


class GreedyWheelhouseError(RuntimeError):
    """A local wheelhouse does not match its Greedy-owned manifest."""


@dataclass(frozen=True)
class WheelSpec:
    distribution: str
    version: str
    filename: str
    python_tag: str
    abi_tag: str
    platform_tag: str
    sha256: str | None


@dataclass(frozen=True)
class WheelManifest:
    image: str
    lock_filename: str
    wheels: tuple[WheelSpec, ...]

    @property
    def expected_filenames(self) -> frozenset[str]:
        return frozenset(spec.filename for spec in self.wheels)


def _canonical_distribution(value: str) -> str:
    return value.lower().replace("_", "-").replace(".", "-")


def _manifest_path(image: str, root: Path) -> Path:
    if image not in IMAGE_NAMES:
        raise GreedyWheelhouseError(f"unknown Greedy image wheelhouse: {image!r}")
    return root / "deploy" / "greedy-kubernetes" / "wheel-manifests" / f"{image}.json"


def _wheelhouse_path(image: str, root: Path) -> Path:
    if image not in IMAGE_NAMES:
        raise GreedyWheelhouseError(f"unknown Greedy image wheelhouse: {image!r}")
    return root / ".offline-wheels" / "greedy" / image


def load_manifest(image: str, *, root: Path = ROOT) -> WheelManifest:
    path = _manifest_path(image, root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise GreedyWheelhouseError(f"invalid or missing Greedy wheel manifest: {path}") from error
    if not isinstance(payload, Mapping):
        raise GreedyWheelhouseError("Greedy wheel manifest must be an object")
    if payload.get("contract_version") != "greedy-offline-wheelhouse-v1":
        raise GreedyWheelhouseError("unsupported Greedy wheel manifest version")
    if payload.get("image") != image:
        raise GreedyWheelhouseError("Greedy wheel manifest has the wrong image")
    if payload.get("python") != "cp312" or payload.get("platform") != "linux/amd64":
        raise GreedyWheelhouseError("unsupported Greedy wheel Python/platform")
    lock_filename = payload.get("lock_filename")
    entries = payload.get("wheels")
    if not isinstance(lock_filename, str) or not lock_filename or not isinstance(entries, list):
        raise GreedyWheelhouseError("Greedy wheel manifest is incomplete")
    specs = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise GreedyWheelhouseError("Greedy wheel manifest entry must be an object")
        keys = (
            "distribution",
            "version",
            "filename",
            "python_tag",
            "abi_tag",
            "platform_tag",
        )
        values = tuple(entry.get(key) for key in keys)
        if not all(isinstance(value, str) and value for value in values):
            raise GreedyWheelhouseError("Greedy wheel manifest entry is incomplete")
        distribution, version, filename, python_tag, abi_tag, platform_tag = values
        digest = entry.get("sha256")
        if digest is not None and (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise GreedyWheelhouseError("Greedy wheel digest is invalid")
        if not filename.endswith(f"-{python_tag}-{abi_tag}-{platform_tag}.whl"):
            raise GreedyWheelhouseError(f"incompatible wheel filename tags: {filename}")
        if _canonical_distribution(distribution) in FORBIDDEN_DISTRIBUTIONS:
            raise GreedyWheelhouseError(
                f"forbidden solver distribution in Greedy manifest: {distribution}"
            )
        specs.append(
            WheelSpec(
                distribution,
                version,
                filename,
                python_tag,
                abi_tag,
                platform_tag,
                digest,
            )
        )
    manifest = WheelManifest(image, lock_filename, tuple(specs))
    if len(manifest.expected_filenames) != len(manifest.wheels):
        raise GreedyWheelhouseError("Greedy wheel manifest has duplicate filenames")
    lock_path = path.parent / lock_filename
    try:
        lock_lines = lock_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise GreedyWheelhouseError(f"missing Greedy wheel lock: {lock_path}") from error
    locked: dict[str, str] = {}
    for line in lock_lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value.count("==") != 1:
            raise GreedyWheelhouseError(f"invalid Greedy lock entry: {value}")
        distribution, version = value.split("==", 1)
        key = _canonical_distribution(distribution)
        if not distribution or not version or key in locked:
            raise GreedyWheelhouseError(f"invalid Greedy lock entry: {value}")
        locked[key] = version
    expected = {
        _canonical_distribution(spec.distribution): spec.version
        for spec in manifest.wheels
    }
    if locked != expected:
        raise GreedyWheelhouseError("Greedy wheel lock does not exactly match manifest")
    return manifest


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_wheelhouse(
    image: str,
    *,
    root: Path = ROOT,
    directory: Path | None = None,
) -> WheelManifest:
    manifest = load_manifest(image, root=root)
    target = directory if directory is not None else _wheelhouse_path(image, root)
    if not target.is_dir():
        raise GreedyWheelhouseError(f"wheelhouse directory is missing: {target}")
    actual = {
        path.name: path
        for path in target.iterdir()
        if path.is_file() and path.suffix == ".whl"
    }
    errors = []
    missing = sorted(manifest.expected_filenames - set(actual))
    unexpected = sorted(set(actual) - manifest.expected_filenames)
    errors.extend(f"missing wheel: {filename}" for filename in missing)
    if unexpected:
        errors.append("unexpected wheels: " + ", ".join(unexpected))
    for spec in manifest.wheels:
        path = actual.get(spec.filename)
        if path is not None and spec.sha256 is not None and _digest(path) != spec.sha256:
            errors.append(f"digest mismatch: {path.name}")
    if errors:
        raise GreedyWheelhouseError(
            f"Greedy {image} wheelhouse validation failed: " + "; ".join(errors)
        )
    return manifest


def validate_all_wheelhouses(*, root: Path = ROOT) -> tuple[WheelManifest, ...]:
    failures = []
    manifests = []
    for image in IMAGE_NAMES:
        try:
            manifests.append(validate_wheelhouse(image, root=root))
        except GreedyWheelhouseError as error:
            failures.append(str(error))
    if failures:
        raise GreedyWheelhouseError("; ".join(failures))
    return tuple(manifests)
