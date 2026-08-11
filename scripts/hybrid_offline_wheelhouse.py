#!/usr/bin/env python3
"""Validate or explicitly stage Hybrid image wheels without network access.

Validation only reads project files; the ``copy`` command is the sole operation
that writes a wheelhouse and it is always explicitly selected by an operator.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
IMAGE_NAMES = ("service", "controller")
FORBIDDEN_DISTRIBUTIONS = frozenset(
    {"milp", "scipy", "highs", "highspy", "ortools", "pandas"}
)


class HybridWheelhouseError(RuntimeError):
    """A local wheelhouse does not match its versioned Hybrid manifest."""


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


def _manifest_path(image: str, *, root: Path = ROOT) -> Path:
    if image not in IMAGE_NAMES:
        raise HybridWheelhouseError(f"unknown Hybrid image wheelhouse: {image!r}")
    return root / "deploy" / "hybrid-kubernetes" / "wheel-manifests" / f"{image}.json"


def _wheelhouse_path(image: str, *, root: Path = ROOT) -> Path:
    if image not in IMAGE_NAMES:
        raise HybridWheelhouseError(f"unknown Hybrid image wheelhouse: {image!r}")
    return root / ".offline-wheels" / "ibg-hybrid" / image


def load_manifest(image: str, *, root: Path = ROOT) -> WheelManifest:
    path = _manifest_path(image, root=root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise HybridWheelhouseError(f"missing Hybrid wheel manifest: {path}") from error
    except json.JSONDecodeError as error:
        raise HybridWheelhouseError(f"invalid Hybrid wheel manifest: {path}") from error
    if not isinstance(payload, Mapping):
        raise HybridWheelhouseError(f"Hybrid wheel manifest is not an object: {path}")
    if payload.get("contract_version") != "ibg-hybrid-offline-wheelhouse-v1":
        raise HybridWheelhouseError(f"unsupported Hybrid wheel manifest: {path}")
    if payload.get("image") != image:
        raise HybridWheelhouseError(f"Hybrid wheel manifest has wrong image: {path}")
    if payload.get("python") != "cp312" or payload.get("platform") != "linux/amd64":
        raise HybridWheelhouseError(
            f"Hybrid wheel manifest has unsupported Python/platform: {path}"
        )
    lock_filename = payload.get("lock_filename")
    wheel_entries = payload.get("wheels")
    if not isinstance(lock_filename, str) or not lock_filename or not isinstance(wheel_entries, list):
        raise HybridWheelhouseError(f"Hybrid wheel manifest is incomplete: {path}")
    specs = []
    for entry in wheel_entries:
        if not isinstance(entry, Mapping):
            raise HybridWheelhouseError(f"Hybrid wheel manifest has invalid entry: {path}")
        values = tuple(entry.get(key) for key in ("distribution", "version", "filename", "python_tag", "abi_tag", "platform_tag"))
        if not all(isinstance(value, str) and value for value in values):
            raise HybridWheelhouseError(f"Hybrid wheel manifest has incomplete wheel entry: {path}")
        distribution, version, filename, python_tag, abi_tag, platform_tag = values
        digest = entry.get("sha256")
        if digest is not None and (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise HybridWheelhouseError(f"Hybrid wheel manifest has invalid digest: {path}")
        if not filename.endswith(".whl") or not filename.endswith(
            f"-{python_tag}-{abi_tag}-{platform_tag}.whl"
        ):
            raise HybridWheelhouseError(f"Hybrid wheel manifest has incompatible filename tags: {filename}")
        if _canonical_distribution(distribution) in FORBIDDEN_DISTRIBUTIONS:
            raise HybridWheelhouseError(f"forbidden solver distribution in Hybrid manifest: {distribution}")
        specs.append(WheelSpec(distribution, version, filename, python_tag, abi_tag, platform_tag, digest))
    manifest = WheelManifest(image, lock_filename, tuple(specs))
    if len(manifest.expected_filenames) != len(manifest.wheels):
        raise HybridWheelhouseError(f"Hybrid wheel manifest has duplicate wheel filenames: {path}")
    lock_path = path.parent / lock_filename
    try:
        lock_lines = lock_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise HybridWheelhouseError(f"missing Hybrid wheel lock: {lock_path}") from error
    locked = {}
    for line in lock_lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value.count("==") != 1:
            raise HybridWheelhouseError(f"invalid Hybrid wheel lock entry: {value}")
        distribution, version = value.split("==", 1)
        key = _canonical_distribution(distribution)
        if not distribution or not version or key in locked:
            raise HybridWheelhouseError(f"invalid Hybrid wheel lock entry: {value}")
        locked[key] = version
    expected_locked = {
        _canonical_distribution(spec.distribution): spec.version
        for spec in manifest.wheels
    }
    if locked != expected_locked:
        raise HybridWheelhouseError(
            f"Hybrid wheel lock does not exactly match manifest: {lock_path}"
        )
    return manifest


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wheel_errors(manifest: WheelManifest, directory: Path) -> list[str]:
    if not directory.is_dir():
        return [f"wheelhouse directory is missing: {directory}"]
    actual = {path.name: path for path in directory.iterdir() if path.is_file() and path.suffix == ".whl"}
    expected = manifest.expected_filenames
    errors = []
    missing = sorted(expected - set(actual))
    unexpected = sorted(set(actual) - expected)
    errors.extend(f"missing wheel: {filename}" for filename in missing)
    if unexpected:
        errors.append("unexpected wheels: " + ", ".join(unexpected))
    for spec in manifest.wheels:
        path = actual.get(spec.filename)
        if path is None:
            continue
        if not path.name.endswith(f"-{spec.python_tag}-{spec.abi_tag}-{spec.platform_tag}.whl"):
            errors.append(f"incompatible Python ABI/platform wheel: {path.name}")
        if spec.sha256 is not None and _file_digest(path) != spec.sha256:
            errors.append(f"digest mismatch: {path.name}")
    return errors


def validate_wheelhouse(image: str, *, root: Path = ROOT, directory: Path | None = None) -> WheelManifest:
    manifest = load_manifest(image, root=root)
    target = directory if directory is not None else _wheelhouse_path(image, root=root)
    errors = _wheel_errors(manifest, target)
    if errors:
        raise HybridWheelhouseError(f"Hybrid {image} wheelhouse validation failed: " + "; ".join(errors))
    return manifest


def validate_all_wheelhouses(*, root: Path = ROOT) -> tuple[WheelManifest, ...]:
    """Validate both images before a normal build starts either Docker command."""

    failures = []
    manifests = []
    for image in IMAGE_NAMES:
        try:
            manifests.append(validate_wheelhouse(image, root=root))
        except HybridWheelhouseError as error:
            failures.append(str(error))
    if failures:
        raise HybridWheelhouseError("; ".join(failures))
    return tuple(manifests)


def required_wheel_filenames(images: Iterable[str] = IMAGE_NAMES, *, root: Path = ROOT) -> tuple[str, ...]:
    lines = []
    for image in images:
        manifest = load_manifest(image, root=root)
        lines.extend(f"{image}: {spec.filename}" for spec in manifest.wheels)
    return tuple(lines)


def copy_supplied_wheels(image: str, *, source: Path, root: Path = ROOT) -> Path:
    """Explicitly copy a fully validated supplied wheel set into the local cache."""

    manifest = validate_wheelhouse(image, root=root, directory=source)
    destination = _wheelhouse_path(image, root=root)
    destination.mkdir(parents=True, exist_ok=True)
    for spec in manifest.wheels:
        shutil.copy2(source / spec.filename, destination / spec.filename)
    validate_wheelhouse(image, root=root, directory=destination)
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or explicitly stage Hybrid offline image wheels; never downloads packages."
    )
    actions = parser.add_subparsers(dest="action", required=True)
    show = actions.add_parser("show", help="list manifest-required wheel filenames")
    show.add_argument("--image", choices=IMAGE_NAMES, default=None)
    validate = actions.add_parser("validate", help="validate a project-local wheelhouse")
    validate.add_argument("--image", choices=IMAGE_NAMES, default=None)
    copy = actions.add_parser("copy", help="copy already-supplied wheels into the project-local wheelhouse")
    copy.add_argument("--image", choices=IMAGE_NAMES, required=True)
    copy.add_argument("--source", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        if args.action == "show":
            images = (args.image,) if args.image else IMAGE_NAMES
            print("\n".join(required_wheel_filenames(images)))
        elif args.action == "validate":
            images = (args.image,) if args.image else IMAGE_NAMES
            for image in images:
                validate_wheelhouse(image)
                print(f"Hybrid {image} wheelhouse: valid")
        else:
            destination = copy_supplied_wheels(args.image, source=args.source)
            print(f"Hybrid {args.image} wheels copied to {destination}")
    except HybridWheelhouseError as error:
        print(f"Hybrid wheelhouse error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
