"""Host-side validation and atomic JSONL lifecycle persistence for Greedy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Callable, Mapping, Sequence

from .comparison import (
    CANONICAL_MATCHED_COMPARISON,
    GREEDY_HYBRID_MATCHED_COMPARISON_VERSION,
    INTENTIONAL_POLICY_DIFFERENCE_FIELDS,
    LEGACY_GREEDY_HYBRID_MATCHED_COMPARISON_VERSION,
    LEGACY_V1_REQUIRED_MATCHED_FIELDS,
)
from .contracts import GREEDY_POLICY_VERSION, LEGACY_GREEDY_POLICY_VERSION
from .evidence import (
    GREEDY_SLOT_EVIDENCE_PREFIX,
    validate_greedy_slot_evidence,
)
from .kernel_infrastructure import (
    CONTROLLER_RESOURCES,
    FLOW_GENERATOR_RESOURCES,
    GREEDY_CONTROLLER_IMAGE,
    GREEDY_NAMESPACE,
    GREEDY_SERVICE_IMAGE,
    PRIVATE_PROCESSOR_RESOURCES,
    PUBLIC_FORWARDER_RESOURCES,
)
from .kernel_lifecycle import (
    GREEDY_CLUSTER_NAME,
    GREEDY_CONTEXT,
    GreedyLaunchConfiguration,
    GreedyLifecycleResult,
)
from .simulation import (
    GREEDY_FLOW_ORDER_SEED_SCHEME,
    GREEDY_MATCHED_INPUT_SEED_SCHEME,
    GREEDY_OBSERVATION_SEED_SCHEME,
    GREEDY_PHYSICAL_SEED_SCHEME,
)


LEGACY_GREEDY_TRACE_CONTRACT_VERSION = "greedy-experiment-jsonl-v1"
# v1 and v2 recorded the link-free predicted fairness index; v3 records the
# clamped end-to-end index plus its domain flag.  All three stay readable.
PREDICTED_FAIRNESS_GREEDY_TRACE_CONTRACT_VERSION = "greedy-experiment-jsonl-v2"
GREEDY_TRACE_CONTRACT_VERSION = "greedy-experiment-jsonl-v3"
DEFAULT_GREEDY_TRACE_DIR = Path(__file__).resolve().parents[1] / "runs"


@dataclass(frozen=True)
class GreedyTraceWriteResult:
    path: Path
    run_id: str
    events: tuple[dict[str, object], ...]


def project_greedy_controller_output(
    output: str,
    *,
    emit: Callable[[str], None],
) -> tuple[dict[str, object], ...]:
    if not isinstance(output, str):
        raise TypeError("controller output must be text")
    evidence = []
    for line in output.splitlines():
        if line.startswith(GREEDY_SLOT_EVIDENCE_PREFIX):
            payload = line.removeprefix(GREEDY_SLOT_EVIDENCE_PREFIX)
            document = json.loads(payload)
            evidence.append(validate_greedy_slot_evidence(document))
        else:
            emit(line)
    return tuple(evidence)


def _resource_spec() -> dict[str, object]:
    return {
        "private_processor": PRIVATE_PROCESSOR_RESOURCES.kubernetes(),
        "public_forwarder": PUBLIC_FORWARDER_RESOURCES.kubernetes(),
        "flow_generator": FLOW_GENERATOR_RESOURCES.kubernetes(),
        "controller": CONTROLLER_RESOURCES.kubernetes(),
    }


def _matched_comparison() -> dict[str, object]:
    fixture = CANONICAL_MATCHED_COMPARISON
    return {
        "version": fixture.version,
        "required_matches": [asdict(item) for item in fixture.required_matches],
        "intentional_policy_differences": [
            asdict(item) for item in fixture.intentional_policy_differences
        ],
        "unresolved_mismatches": [
            asdict(item) for item in fixture.unresolved_mismatches
        ],
    }


def _validate_legacy_v1_matched_comparison(value: object) -> None:
    """Validate the frozen v1 comparison envelope without relabelling it v2."""

    if not isinstance(value, Mapping) or set(value) != {
        "version", "required_matches", "intentional_policy_differences",
    }:
        raise ValueError("legacy Greedy comparison envelope is malformed")
    if value["version"] != LEGACY_GREEDY_HYBRID_MATCHED_COMPARISON_VERSION:
        raise ValueError("legacy Greedy comparison version drifted")
    required = value["required_matches"]
    differences = value["intentional_policy_differences"]
    if not isinstance(required, list) or tuple(
        item.get("name") for item in required if isinstance(item, Mapping)
    ) != LEGACY_V1_REQUIRED_MATCHED_FIELDS:
        raise ValueError("legacy Greedy comparison fields drifted")
    for item in required:
        if not isinstance(item, Mapping) or set(item) != {
            "name", "greedy_value", "hybrid_value", "source_location",
        }:
            raise ValueError("legacy Greedy matched field is malformed")
        if item["greedy_value"] != item["hybrid_value"]:
            raise ValueError("legacy Greedy matched field is unequal")
    by_name = {item["name"]: item for item in required}
    if (
        by_name["admission_capacity_per_replica"]["greedy_value"] != 2
        or by_name["ready_capacity_semantics"]["greedy_value"]
        != "ready-and-current-load-plus-one-within-declared-capacity"
    ):
        raise ValueError("legacy Greedy admission comparison drifted")
    if not isinstance(differences, list) or tuple(
        item.get("name") for item in differences if isinstance(item, Mapping)
    ) != INTENTIONAL_POLICY_DIFFERENCE_FIELDS:
        raise ValueError("legacy Greedy policy-difference fields drifted")
    for item in differences:
        if not isinstance(item, Mapping) or set(item) != {
            "name", "greedy_value", "hybrid_value", "reason",
        }:
            raise ValueError("legacy Greedy policy difference is malformed")
        if item["greedy_value"] == item["hybrid_value"]:
            raise ValueError("legacy Greedy policy difference is not different")


def build_greedy_trace_events(
    evidence: Sequence[Mapping[str, object]],
    *,
    launch: GreedyLaunchConfiguration,
    lifecycle: GreedyLifecycleResult,
    run_id: str,
    recorded_at: datetime,
) -> tuple[dict[str, object], ...]:
    if not isinstance(launch, GreedyLaunchConfiguration):
        raise TypeError("launch must be GreedyLaunchConfiguration")
    if not isinstance(lifecycle, GreedyLifecycleResult):
        raise TypeError("lifecycle must be GreedyLifecycleResult")
    if (
        lifecycle.configuration != launch.configuration
        or lifecycle.root_seed != launch.root_seed
        or lifecycle.profile_fingerprint != launch.runtime_profiles.fingerprint
        or lifecycle.controller_jobs_created != 1
    ):
        raise ValueError("Greedy lifecycle does not match the one-run launch")
    if not isinstance(run_id, str) or not run_id or any(char in run_id for char in "/\n\r"):
        raise ValueError("Greedy run ID must be a nonempty path-safe line")
    if recorded_at.tzinfo is None:
        raise ValueError("recorded_at must be timezone-aware")
    slots = tuple(validate_greedy_slot_evidence(item) for item in evidence)
    if not slots or len(slots) > launch.max_iterations:
        raise ValueError("Greedy trace must contain one through max_iterations slots")
    configuration = launch.configuration
    expected_configuration = {
        "num_flows": configuration.num_flows,
        "num_stages": configuration.num_stages,
        "num_replicas": configuration.num_replicas,
        "stage_budget": 2,
    }
    previous_beliefs = None
    first_slot = slots[0]["slot_id"]
    for index, slot in enumerate(slots):
        if slot["configuration"] != expected_configuration:
            raise ValueError("Greedy trace configuration is inconsistent")
        if slot["slot_id"] != first_slot + index:
            raise ValueError("Greedy trace slots are not contiguous")
        if (
            slot["root_seed"] != launch.root_seed
            or slot["profile_seed"] != launch.profile_seed
            or slot["runtime_profile_fingerprint"] != lifecycle.profile_fingerprint
        ):
            raise ValueError("Greedy trace seed/profile provenance is inconsistent")
        if slot["pure_kernel_replay_requested"] is not bool(launch.parity_replay):
            raise ValueError("Greedy trace replay setting is inconsistent")
        if bool(launch.csv) != ("control_plane" in slot):
            raise ValueError("Greedy trace footprint setting is inconsistent")
        if "controller_resources" not in slot:
            raise ValueError("Greedy trace lacks controller resource measurements")
        if previous_beliefs is not None and slot["beliefs_before"] != previous_beliefs:
            raise ValueError("Greedy trace belief continuity failed")
        previous_beliefs = slot["beliefs_after"]
    final_equilibrium = bool(slots[-1]["metrics"]["equilibrium"])
    if not final_equilibrium and len(slots) != launch.max_iterations:
        raise ValueError("non-equilibrium Greedy trace stopped before max_iterations")
    started = {
        "event": "run_started",
        "trace_contract_version": GREEDY_TRACE_CONTRACT_VERSION,
        "run_id": run_id,
        "recorded_at_utc": recorded_at.astimezone(timezone.utc).isoformat(),
        "configuration": expected_configuration,
        "max_iterations": launch.max_iterations,
        "experiment_id": launch.experiment_id,
        "root_seed": launch.root_seed,
        "profile_seed": launch.profile_seed,
        "runtime_profile_fingerprint": lifecycle.profile_fingerprint,
        "policy_contract_version": GREEDY_POLICY_VERSION,
        "matched_comparison_version": GREEDY_HYBRID_MATCHED_COMPARISON_VERSION,
        "matched_comparison": _matched_comparison(),
        "flow_order_seed_scheme": GREEDY_FLOW_ORDER_SEED_SCHEME,
        "matched_input_seed_scheme": GREEDY_MATCHED_INPUT_SEED_SCHEME,
        "physical_seed_scheme": GREEDY_PHYSICAL_SEED_SCHEME,
        "observation_seed_scheme": GREEDY_OBSERVATION_SEED_SCHEME,
        "cluster": GREEDY_CLUSTER_NAME,
        "context": GREEDY_CONTEXT,
        "namespace": GREEDY_NAMESPACE,
        "rollout_batch_size": launch.rollout_batch_size,
        "skip_build": launch.skip_build,
        "bootstrap": lifecycle.cluster_created,
        "serving_changed": lifecycle.serving_changed,
        "controller_jobs_created": lifecycle.controller_jobs_created,
        "built_images": list(lifecycle.built_images),
        "loaded_images": list(lifecycle.loaded_images),
        "images": {
            "service": {
                "name": GREEDY_SERVICE_IMAGE,
                "id": lifecycle.service_image_id,
                "source_fingerprint": lifecycle.service_source_fingerprint,
            },
            "controller": {
                "name": GREEDY_CONTROLLER_IMAGE,
                "id": lifecycle.controller_image_id,
                "source_fingerprint": lifecycle.controller_source_fingerprint,
            },
        },
        "worker_allocatable": {
            "cpu_millicores": lifecycle.worker_allocatable_cpu_millicores,
            "memory_mib": lifecycle.worker_allocatable_memory_mib,
        },
        "pod_resources": _resource_spec(),
        "csv_enabled": bool(launch.csv),
        "parity_replay_enabled": bool(launch.parity_replay),
    }
    iterations = tuple(
        {
            **slot,
            "event": "iteration_completed",
            "trace_contract_version": GREEDY_TRACE_CONTRACT_VERSION,
            "run_id": run_id,
            "iteration": index,
            "csv_enabled": bool(launch.csv),
            "parity_replay_enabled": bool(launch.parity_replay),
        }
        for index, slot in enumerate(slots, start=1)
    )
    completed = {
        "event": "run_completed",
        "trace_contract_version": GREEDY_TRACE_CONTRACT_VERSION,
        "run_id": run_id,
        "iterations": len(slots),
        "first_slot_id": slots[0]["slot_id"],
        "last_slot_id": slots[-1]["slot_id"],
        "reached_equilibrium": final_equilibrium,
        "stop_reason": "equilibrium" if final_equilibrium else "max-iterations",
        "final_beliefs": slots[-1]["beliefs_after"],
        "root_seed": launch.root_seed,
        "profile_seed": launch.profile_seed,
        "runtime_profile_fingerprint": lifecycle.profile_fingerprint,
        "csv_enabled": bool(launch.csv),
        "parity_replay_enabled": bool(launch.parity_replay),
    }
    return validate_greedy_trace_events((started, *iterations, completed))


def validate_greedy_trace_events(
    events: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    documents = tuple(dict(item) for item in events)
    if len(documents) < 3:
        raise ValueError("Greedy trace lifecycle is incomplete")
    if [item.get("event") for item in documents].count("run_started") != 1:
        raise ValueError("Greedy trace requires one run_started record")
    if [item.get("event") for item in documents].count("run_completed") != 1:
        raise ValueError("Greedy trace requires one run_completed record")
    if documents[0].get("event") != "run_started" or documents[-1].get("event") != "run_completed":
        raise ValueError("Greedy trace lifecycle ordering is invalid")
    iterations = documents[1:-1]
    if not iterations or any(item.get("event") != "iteration_completed" for item in iterations):
        raise ValueError("Greedy trace requires contiguous iteration records")
    trace_version = documents[0].get("trace_contract_version")
    if trace_version not in {
        LEGACY_GREEDY_TRACE_CONTRACT_VERSION,
        PREDICTED_FAIRNESS_GREEDY_TRACE_CONTRACT_VERSION,
        GREEDY_TRACE_CONTRACT_VERSION,
    } or any(item.get("trace_contract_version") != trace_version for item in documents):
        raise ValueError("Greedy trace mixes schema versions")
    legacy_v1 = trace_version == LEGACY_GREEDY_TRACE_CONTRACT_VERSION
    run_id = documents[0].get("run_id")
    if not isinstance(run_id, str) or not run_id or any(item.get("run_id") != run_id for item in documents):
        raise ValueError("Greedy trace run identity is inconsistent")
    if [item.get("iteration") for item in iterations] != list(range(1, len(iterations) + 1)):
        raise ValueError("Greedy trace iterations are not contiguous")
    if documents[-1].get("iterations") != len(iterations):
        raise ValueError("Greedy trace completion count is inconsistent")
    first_iteration_slot = iterations[0].get("slot_id")
    if (
        isinstance(first_iteration_slot, bool)
        or not isinstance(first_iteration_slot, int)
        or first_iteration_slot < 1
    ):
        raise ValueError("Greedy trace first slot identity is invalid")
    if [item.get("slot_id") for item in iterations] != list(
        range(first_iteration_slot, first_iteration_slot + len(iterations))
    ):
        raise ValueError("Greedy trace slot identities are not contiguous")
    started = documents[0]
    completed = documents[-1]
    started_fields = {
        "event", "trace_contract_version", "run_id", "recorded_at_utc",
        "configuration", "max_iterations", "experiment_id", "root_seed",
        "profile_seed", "runtime_profile_fingerprint", "policy_contract_version",
        "matched_comparison_version", "matched_comparison",
        "flow_order_seed_scheme", "matched_input_seed_scheme",
        "physical_seed_scheme", "observation_seed_scheme", "cluster", "context",
        "namespace", "rollout_batch_size", "skip_build", "bootstrap",
        "serving_changed", "controller_jobs_created", "built_images",
        "loaded_images", "images", "worker_allocatable", "pod_resources",
        "csv_enabled", "parity_replay_enabled",
    }
    completed_fields = {
        "event", "trace_contract_version", "run_id", "iterations",
        "first_slot_id", "last_slot_id", "reached_equilibrium", "stop_reason",
        "final_beliefs", "root_seed", "profile_seed",
        "runtime_profile_fingerprint", "csv_enabled", "parity_replay_enabled",
    }
    if set(started) != started_fields or set(completed) != completed_fields:
        raise ValueError("Greedy trace lifecycle fields are incomplete or unexpected")
    try:
        recorded = datetime.fromisoformat(str(started["recorded_at_utc"]))
    except ValueError as error:
        raise ValueError("Greedy trace timestamp is malformed") from error
    if recorded.tzinfo is None:
        raise ValueError("Greedy trace timestamp must be timezone-aware")
    if legacy_v1:
        if (
            started["policy_contract_version"] != LEGACY_GREEDY_POLICY_VERSION
            or started["matched_comparison_version"]
            != LEGACY_GREEDY_HYBRID_MATCHED_COMPARISON_VERSION
        ):
            raise ValueError("legacy Greedy trace comparison or policy provenance drifted")
        _validate_legacy_v1_matched_comparison(started["matched_comparison"])
    elif (
        started["policy_contract_version"] != GREEDY_POLICY_VERSION
        or started["matched_comparison_version"]
        != GREEDY_HYBRID_MATCHED_COMPARISON_VERSION
        or started["matched_comparison"] != _matched_comparison()
    ):
        raise ValueError("Greedy trace comparison or policy provenance drifted")
    if (
        started["flow_order_seed_scheme"] != GREEDY_FLOW_ORDER_SEED_SCHEME
        or started["matched_input_seed_scheme"] != GREEDY_MATCHED_INPUT_SEED_SCHEME
        or started["physical_seed_scheme"] != GREEDY_PHYSICAL_SEED_SCHEME
        or started["observation_seed_scheme"] != GREEDY_OBSERVATION_SEED_SCHEME
    ):
        raise ValueError("Greedy trace seed-scheme provenance drifted")
    if (
        started["cluster"] != GREEDY_CLUSTER_NAME
        or started["context"] != GREEDY_CONTEXT
        or started["namespace"] != GREEDY_NAMESPACE
        or started["pod_resources"] != _resource_spec()
        or started["controller_jobs_created"] != 1
    ):
        raise ValueError("Greedy trace runtime envelope drifted")
    for name in ("max_iterations", "experiment_id", "rollout_batch_size"):
        value = started[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"Greedy trace {name} is invalid")
    for name in ("root_seed", "profile_seed"):
        value = started[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Greedy trace {name} is invalid")
    for name in ("skip_build", "bootstrap", "serving_changed", "csv_enabled", "parity_replay_enabled"):
        if not isinstance(started[name], bool):
            raise ValueError(f"Greedy trace {name} must be boolean")
    for name in ("built_images", "loaded_images"):
        if (
            not isinstance(started[name], list)
            or len(set(started[name])) != len(started[name])
            or any(not isinstance(item, str) or not item for item in started[name])
        ):
            raise ValueError(f"Greedy trace {name} is malformed")
        if not set(started[name]).issubset({"service", "controller"}):
            raise ValueError(f"Greedy trace {name} contains a foreign image role")
    if started["loaded_images"] != started["built_images"]:
        raise ValueError("Greedy trace build/load role provenance is inconsistent")
    images = started["images"]
    if not isinstance(images, Mapping) or set(images) != {"service", "controller"}:
        raise ValueError("Greedy trace image provenance is incomplete")
    for role in ("service", "controller"):
        image = images[role]
        if not isinstance(image, Mapping) or set(image) != {"name", "id", "source_fingerprint"}:
            raise ValueError("Greedy trace image provenance is malformed")
        if any(not isinstance(image[field], str) or not image[field] for field in image):
            raise ValueError("Greedy trace image provenance is empty")
        expected_name = GREEDY_SERVICE_IMAGE if role == "service" else GREEDY_CONTROLLER_IMAGE
        if image["name"] != expected_name:
            raise ValueError("Greedy trace image ownership drifted")
        digest = image["id"]
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("Greedy trace image ID is not a full sha256 digest")
        source_fingerprint = image["source_fingerprint"]
        if len(source_fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in source_fingerprint
        ):
            raise ValueError("Greedy trace source fingerprint is invalid")
    worker = started["worker_allocatable"]
    if not isinstance(worker, Mapping) or set(worker) != {"cpu_millicores", "memory_mib"}:
        raise ValueError("Greedy trace worker allocatable is incomplete")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in worker.values()):
        raise ValueError("Greedy trace worker allocatable is invalid")
    for item in iterations:
        projection = {
            key: value
            for key, value in item.items()
            if key not in {
                "event", "trace_contract_version", "run_id", "iteration",
                "csv_enabled", "parity_replay_enabled",
            }
        }
        validate_greedy_slot_evidence(projection)
        if item["pure_kernel_replay_requested"] is not item["parity_replay_enabled"]:
            raise ValueError("Greedy trace replay provenance is mixed")
        if (
            item["configuration"] != started["configuration"]
            or item["experiment_id"] != started["experiment_id"]
            or item["root_seed"] != started["root_seed"]
            or item["profile_seed"] != started["profile_seed"]
            or item["runtime_profile_fingerprint"]
            != started["runtime_profile_fingerprint"]
        ):
            raise ValueError("Greedy trace iteration provenance is mixed")
    if any(item.get("parity_replay_enabled") is not documents[0].get("parity_replay_enabled") for item in documents[1:]):
        raise ValueError("Greedy trace parity setting is mixed")
    if any(item.get("csv_enabled") is not documents[0].get("csv_enabled") for item in documents[1:]):
        raise ValueError("Greedy trace CSV setting is mixed")
    if documents[-1].get("final_beliefs") != iterations[-1].get("beliefs_after"):
        raise ValueError("Greedy trace final beliefs are inconsistent")
    if (
        completed["root_seed"] != started["root_seed"]
        or completed["profile_seed"] != started["profile_seed"]
        or completed["runtime_profile_fingerprint"]
        != started["runtime_profile_fingerprint"]
        or completed["first_slot_id"] != iterations[0]["slot_id"]
        or completed["last_slot_id"] != iterations[-1]["slot_id"]
        or completed["reached_equilibrium"] is not bool(iterations[-1]["metrics"]["equilibrium"])
        or completed["stop_reason"]
        != ("equilibrium" if completed["reached_equilibrium"] else "max-iterations")
    ):
        raise ValueError("Greedy trace completion provenance is inconsistent")
    if not completed["reached_equilibrium"] and len(iterations) != started["max_iterations"]:
        raise ValueError("non-equilibrium Greedy trace stopped before max_iterations")
    return documents


def load_greedy_trace(path: Path) -> tuple[dict[str, object], ...]:
    with Path(path).open(encoding="utf-8") as source:
        events = [json.loads(line) for line in source if line.strip()]
    return validate_greedy_trace_events(events)


def persist_greedy_trace(
    evidence: Sequence[Mapping[str, object]],
    *,
    launch: GreedyLaunchConfiguration,
    lifecycle: GreedyLifecycleResult,
    trace_dir: Path = DEFAULT_GREEDY_TRACE_DIR,
    recorded_at: datetime | None = None,
    run_id: str | None = None,
) -> GreedyTraceWriteResult:
    timestamp = recorded_at or datetime.now(timezone.utc)
    resolved_run_id = run_id or timestamp.astimezone(timezone.utc).strftime(
        "%Y%m%dT%H%M%S.%fZ"
    )
    events = build_greedy_trace_events(
        evidence,
        launch=launch,
        lifecycle=lifecycle,
        run_id=resolved_run_id,
        recorded_at=timestamp,
    )
    directory = Path(trace_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"greedy-experiment-{resolved_run_id}.jsonl"
    if target.exists():
        raise FileExistsError(f"Greedy trace already exists: {target}")
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="x", encoding="utf-8", dir=directory,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as destination:
            temporary = destination.name
            for event in events:
                destination.write(json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False))
                destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        loaded = load_greedy_trace(Path(temporary))
        if loaded != events:
            raise RuntimeError("persisted Greedy trace failed round-trip validation")
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    return GreedyTraceWriteResult(target, resolved_run_id, events)
