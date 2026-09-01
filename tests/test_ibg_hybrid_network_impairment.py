import json
from pathlib import Path

import pytest

from IBG_Hybrid.kernel_infrastructure_contract import (
    DEFAULT_HYBRID_KERNEL_OWNERSHIP,
)
from IBG_Hybrid.network_impairment import (
    HYBRID_NETEM_INIT_CONTAINER_NAME,
    HYBRID_NETWORK_IMPAIRMENT_ANNOTATION,
    HYBRID_NETWORK_IMPAIRMENT_DISTRIBUTION,
    HYBRID_NETWORK_IMPAIRMENT_INTERFACE,
    HYBRID_NETWORK_IMPAIRMENT_SCHEMA,
    HYBRID_NETWORK_IMPAIRMENT_SCOPE,
    HybridNetworkImpairment,
    validate_hybrid_network_impairment_events,
)
from scripts import run_hybrid_kernel_phase4 as runner


ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP = DEFAULT_HYBRID_KERNEL_OWNERSHIP


def _statefulset(
    stage: int,
    *,
    impairment: HybridNetworkImpairment | None = None,
):
    labels = dict(OWNERSHIP.replica_labels(stage))
    template = {
        "metadata": {"labels": labels},
        "spec": {
            "nodeSelector": {
                runner.WORKLOAD_NODE_LABEL: runner.WORKLOAD_NODE_LABEL_VALUE
            },
            "containers": [
                {"name": "private-processor"},
                {"name": "public-forwarder"},
            ],
        },
    }
    if impairment is not None and impairment.enabled:
        template["metadata"]["annotations"] = {
            HYBRID_NETWORK_IMPAIRMENT_ANNOTATION: impairment.to_json()
        }
        template["spec"]["initContainers"] = [
            impairment.init_container(image=runner.NETEM_IMAGE)
        ]
    return {
        "apiVersion": "apps/v1",
        "kind": "StatefulSet",
        "metadata": {
            "name": f"hybrid-stage-{stage}",
            "namespace": OWNERSHIP.namespace,
            "labels": labels,
        },
        "spec": {
            "serviceName": f"hybrid-stage-{stage}",
            "replicas": 2,
            "selector": {
                "matchLabels": dict(OWNERSHIP.replica_selector(stage))
            },
            "template": template,
        },
    }


def _statefulsets(
    impairment: HybridNetworkImpairment | None = None,
):
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            _statefulset(stage, impairment=impairment)
            for stage in range(1, 4)
        ],
    }


def _trace_slot(slot_id: int, *, root_seed: int | None = None):
    return {
        "configuration": {
            "num_flows": 1,
            "num_stages": 3,
            "num_replicas": 1,
            "stage_budget": 2,
        },
        "slot_id": slot_id,
        "root_seed": slot_id if root_seed is None else root_seed,
        "policy_mode": "lookahead",
        "mc_workers": None,
        "placements": [{"flow_id": 1, "measured_pair_ms": 5.0}],
        "observations": [
            {"flow_id": 1, "stage": 1},
            {"flow_id": 1, "stage": 3},
        ],
        "beliefs_before": {"1:1": [0.25, 0.25, 0.25, 0.25]},
        "beliefs_after": {"1:1": [0.25, 0.25, 0.25, 0.25]},
        "pure_kernel_replay_performed": False,
        "metrics": {
            "elapsed_seconds": 1.0,
            "end_to_end_sla_violations": 0,
            "end_to_end_sla_excess_ms": 0.0,
            "sla_latency_threshold_ms": 80.0,
            "raw_end_to_end_latency_ms_per_flow": [[1, 80.0]],
            "raw_end_to_end_reference_utility": 1.0,
            "jain_fairness": 1.0,
            "equilibrium": True,
        },
    }


def test_disabled_configuration_is_explicit_and_has_no_tc_or_init_container():
    impairment = HybridNetworkImpairment.disabled()

    assert impairment.to_dict() == {
        "schema": HYBRID_NETWORK_IMPAIRMENT_SCHEMA,
        "enabled": False,
        "interface": HYBRID_NETWORK_IMPAIRMENT_INTERFACE,
        "delay_ms": 0.0,
        "jitter_ms": 0.0,
        "distribution": HYBRID_NETWORK_IMPAIRMENT_DISTRIBUTION,
        "scope": HYBRID_NETWORK_IMPAIRMENT_SCOPE,
    }
    with pytest.raises(ValueError, match="has no tc command"):
        impairment.tc_command()
    with pytest.raises(ValueError, match="has no tc command"):
        impairment.init_container(image=runner.NETEM_IMAGE)


def test_enabled_configuration_matches_exact_tc_syntax_and_zero_jitter_rule():
    impairment = HybridNetworkImpairment.enabled_with(
        delay_ms=10,
        jitter_ms=3,
    )
    zero_jitter = HybridNetworkImpairment.enabled_with(
        delay_ms=10,
        jitter_ms=0,
    )

    assert impairment.tc_command() == (
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
    )
    assert zero_jitter.tc_command() == impairment.tc_command()[:9]
    assert HybridNetworkImpairment.from_json(impairment.to_json()) == impairment


@pytest.mark.parametrize(
    ("delay_ms", "jitter_ms", "message"),
    [
        (True, 0, "must be numeric"),
        (10, False, "must be numeric"),
        (float("nan"), 0, "finite and nonnegative"),
        (float("inf"), 0, "finite and nonnegative"),
        (-1, 0, "finite and nonnegative"),
        (10, -1, "finite and nonnegative"),
        (0, 0, "positive delay_ms"),
        (2, 3, "cannot exceed"),
    ],
)
def test_enabled_configuration_rejects_invalid_values(
    delay_ms,
    jitter_ms,
    message,
):
    with pytest.raises(ValueError, match=message):
        HybridNetworkImpairment.enabled_with(
            delay_ms=delay_ms,
            jitter_ms=jitter_ms,
        )


def test_production_cli_defaults_off_and_validates_option_combinations():
    required = [
        "run",
        "--flow", "2",
        "--stage", "3",
        "--replica", "1",
        "--profile-seed", "42",
        "--max-iterations", "1",
    ]

    default = runner.parse_args(required)
    enabled = runner.parse_args(
        [*required, "--netem", "1", "--netem-delay-ms", "8.5",
         "--netem-jitter-ms", "2.25"]
    )
    assert default.network_impairment == HybridNetworkImpairment.disabled()
    assert enabled.network_impairment == HybridNetworkImpairment.enabled_with(
        delay_ms=8.5,
        jitter_ms=2.25,
    )

    invalid_options = (
        [*required, "--netem", "0", "--netem-delay-ms", "1"],
        [*required, "--netem", "1", "--netem-delay-ms", "nan"],
        [*required, "--netem", "1", "--netem-jitter-ms", "inf"],
        [*required, "--netem", "1", "--netem-delay-ms", "2",
         "--netem-jitter-ms", "3"],
    )
    for arguments in invalid_options:
        with pytest.raises(SystemExit):
            runner.parse_args(arguments)


def test_enabled_init_container_is_bounded_and_does_not_change_service_contracts():
    impairment = HybridNetworkImpairment.enabled_with(
        delay_ms=10,
        jitter_ms=3,
    )
    container = impairment.init_container(image=runner.NETEM_IMAGE)

    assert container["name"] == HYBRID_NETEM_INIT_CONTAINER_NAME
    assert container["command"] == ["/usr/sbin/tc"]
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "capabilities": {"add": ["NET_ADMIN"], "drop": ["ALL"]},
        "runAsNonRoot": False,
        "runAsUser": 0,
    }
    assert "privileged" not in container["securityContext"]
    assert "hostNetwork" not in json.dumps(container)
    service_manifest = (
        ROOT / "deploy" / "hybrid-kubernetes" / "replicas.yaml"
    ).read_text(encoding="utf-8")
    assert "initContainers:" not in service_manifest
    assert "NET_ADMIN" not in service_manifest


def test_dynamic_patch_targets_only_all_three_replica_statefulsets(tmp_path):
    impairment = HybridNetworkImpairment.enabled_with(
        delay_ms=10,
        jitter_ms=3,
    )

    kustomization_fragment = runner._write_network_impairment_patches(
        tmp_path,
        impairment,
    )
    assert kustomization_fragment == (
        "patches:\n"
        "  - path: netem-stage-1.json\n"
        "  - path: netem-stage-2.json\n"
        "  - path: netem-stage-3.json\n"
    )
    patches = [
        json.loads((tmp_path / f"netem-stage-{stage}.json").read_text())
        for stage in range(1, 4)
    ]
    assert [patch["metadata"]["name"] for patch in patches] == [
        "hybrid-stage-1",
        "hybrid-stage-2",
        "hybrid-stage-3",
    ]
    for patch in patches:
        assert set(patch["spec"]["template"]) == {"metadata", "spec"}
        assert patch["spec"]["template"]["spec"]["initContainers"] == [
            impairment.init_container(image=runner.NETEM_IMAGE)
        ]
    assert runner._write_network_impairment_patches(
        tmp_path,
        HybridNetworkImpairment.disabled(),
    ) == ""


def test_reconciliation_preserves_external_template_annotations_without_netem(
    tmp_path,
):
    statefulsets = _statefulsets(
        HybridNetworkImpairment.enabled_with(delay_ms=2, jitter_ms=2)
    )
    for item in statefulsets["items"]:
        item["spec"]["template"]["metadata"]["annotations"][
            "kubectl.kubernetes.io/restartedAt"
        ] = "2026-08-22T16:40:55+03:30"

    paths = runner._write_preserved_template_annotation_patches(
        tmp_path,
        statefulsets,
    )

    assert paths == tuple(
        f"preserve-hybrid-stage-{stage}-template-annotations.json"
        for stage in range(1, 4)
    )
    for path in paths:
        patch = json.loads((tmp_path / path).read_text())
        annotations = patch["spec"]["template"]["metadata"]["annotations"]
        assert annotations == {
            "kubectl.kubernetes.io/restartedAt": "2026-08-22T16:40:55+03:30"
        }
        assert HYBRID_NETWORK_IMPAIRMENT_ANNOTATION not in annotations

    fragment = runner._write_network_impairment_patches(
        tmp_path,
        HybridNetworkImpairment.disabled(),
        additional_paths=paths,
    )
    assert fragment == "patches:\n" + "".join(
        f"  - path: {path}\n" for path in paths
    )


def test_statefulset_inventory_requires_one_consistent_exact_configuration():
    enabled = HybridNetworkImpairment.enabled_with(
        delay_ms=10,
        jitter_ms=3,
    )
    disabled_inventory = _statefulsets()
    enabled_inventory = _statefulsets(enabled)
    # Kubernetes adds these fields to persisted containers; they are not drift.
    for statefulset in enabled_inventory["items"]:
        init = statefulset["spec"]["template"]["spec"]["initContainers"][0]
        init["terminationMessagePath"] = "/dev/termination-log"
        init["terminationMessagePolicy"] = "File"

    assert runner._statefulset_network_impairment(
        disabled_inventory
    ) == HybridNetworkImpairment.disabled()
    assert runner._statefulset_network_impairment(enabled_inventory) == enabled

    mixed = _statefulsets(enabled)
    mixed["items"][0] = _statefulset(1)
    with pytest.raises(RuntimeError, match="mixed network-impairment"):
        runner._statefulset_network_impairment(mixed)

    malformed = _statefulsets(enabled)
    malformed["items"][0]["spec"]["template"]["spec"]["initContainers"][0][
        "securityContext"
    ]["capabilities"]["add"] = ["NET_ADMIN", "SYS_ADMIN"]
    with pytest.raises(RuntimeError, match="init container drifted"):
        runner._statefulset_network_impairment(malformed)


def test_network_fields_are_the_only_allowed_template_transition():
    enabled = HybridNetworkImpairment.enabled_with(
        delay_ms=10,
        jitter_ms=3,
    )
    disabled = _statefulsets()
    impaired = _statefulsets(enabled)

    assert runner._statefulset_template_snapshot(
        runner._without_network_impairment(disabled)
    ) == runner._statefulset_template_snapshot(
        runner._without_network_impairment(impaired)
    )

    impaired["items"][0]["spec"]["template"]["spec"]["containers"][0][
        "resources"
    ] = {"requests": {"cpu": "999m"}}
    assert runner._statefulset_template_snapshot(
        runner._without_network_impairment(disabled)
    ) != runner._statefulset_template_snapshot(
        runner._without_network_impairment(impaired)
    )


def test_impairment_rollout_replaces_replicas_and_preserves_flow_generator():
    def snapshot(name, uid):
        containers = (
            (("flow-generator", 0),)
            if name.startswith("ibg-hybrid-flow-generator-")
            else (("private-processor", 0), ("public-forwarder", 0))
        )
        return runner.ServingPodProcessSnapshot(name, uid, containers)

    flow = snapshot("ibg-hybrid-flow-generator-abcde", "flow-uid")
    before = tuple(
        [
            snapshot(f"hybrid-stage-{stage}-0", f"old-{stage}")
            for stage in range(1, 4)
        ]
        + [flow]
    )
    after = tuple(
        [
            snapshot(f"hybrid-stage-{stage}-0", f"new-{stage}")
            for stage in range(1, 4)
        ]
        + [flow]
    )

    runner._validate_network_impairment_rollout(
        before,
        after,
        requested_count=1,
    )
    unchanged = tuple(before)
    with pytest.raises(RuntimeError, match="did not replace"):
        runner._validate_network_impairment_rollout(
            before,
            unchanged,
            requested_count=1,
        )


def test_enabled_image_build_is_offline_conditional_and_hybrid_owned(monkeypatch):
    commands = []
    required_images = []
    monkeypatch.setattr(runner, "_validate_offline_wheelhouses", lambda: None)
    monkeypatch.setattr(
        runner,
        "_require_local_image",
        lambda execute, image: required_images.append(image),
    )
    enabled = HybridNetworkImpairment.enabled_with(
        delay_ms=10,
        jitter_ms=3,
    )

    runner._build_images_offline(
        lambda command, capture: commands.append(command) or "",
        network_impairment=enabled,
    )

    assert required_images == [runner.PYTHON_BASE_IMAGE, runner.NETEM_BASE_IMAGE]
    assert len(commands) == 3
    assert commands[-1][commands[-1].index("--tag") + 1] == runner.NETEM_IMAGE
    assert all("--pull=false" in command for command in commands)
    assert all("--network=none" in command for command in commands)
    dockerfile = runner.NETEM_DOCKERFILE.read_text(encoding="utf-8")
    assert f"FROM {runner.NETEM_BASE_IMAGE}" in dockerfile
    assert "FROM scratch" in dockerfile
    assert "RUN test -x /usr/sbin/tc" in dockerfile
    assert "normal.dist" in dockerfile
    assert "ibg-testbed:kernel-phase3" not in dockerfile


def test_trace_records_complete_identical_provenance_without_bumping_v3(tmp_path):
    impairment = HybridNetworkImpairment.enabled_with(
        delay_ms=10,
        jitter_ms=3,
    )
    trace = runner._persist_hybrid_experiment_trace(
        json.dumps(_trace_slot(1)),
        trace_dir=tmp_path,
        requested_flows=1,
        requested_stages=3,
        requested_replicas=1,
        max_iterations=1,
        network_impairment=impairment,
    )
    events = [json.loads(line) for line in trace.read_text().splitlines()]

    assert [event["event"] for event in events] == [
        "run_started",
        "iteration_completed",
        "run_completed",
    ]
    assert all(
        event["trace_contract_version"]
        == "ibg-hybrid-experiment-jsonl-v3"
        for event in events
    )
    assert all(
        event["network_impairment"] == impairment.to_dict()
        for event in events
    )
    assert "network_impairment" not in events[1]["metrics"]
    assert validate_hybrid_network_impairment_events(
        events,
        expected=impairment,
    ) == impairment


def test_trace_provenance_rejects_missing_mixed_malformed_and_controller_owned(
    tmp_path,
):
    disabled = HybridNetworkImpairment.disabled().to_dict()
    enabled = HybridNetworkImpairment.enabled_with(
        delay_ms=10,
        jitter_ms=3,
    ).to_dict()

    with pytest.raises(ValueError, match="lacks network_impairment"):
        validate_hybrid_network_impairment_events([{"event": "run_started"}])
    with pytest.raises(ValueError, match="mixes or drifts"):
        validate_hybrid_network_impairment_events(
            [
                {"network_impairment": disabled},
                {"network_impairment": enabled},
            ]
        )
    malformed = dict(disabled)
    malformed["delay_ms"] = -1
    with pytest.raises(ValueError, match="finite and nonnegative"):
        validate_hybrid_network_impairment_events(
            [{"network_impairment": malformed}]
        )

    slot = _trace_slot(1)
    slot["network_impairment"] = disabled
    with pytest.raises(RuntimeError, match="must not supply host"):
        runner._persist_hybrid_experiment_trace(
            json.dumps(slot),
            trace_dir=tmp_path,
            requested_flows=1,
            requested_stages=3,
            requested_replicas=1,
            max_iterations=1,
        )
    assert not list(tmp_path.iterdir())


def test_random_series_reuses_one_impairment_configuration(monkeypatch, tmp_path):
    impairment = HybridNetworkImpairment.enabled_with(
        delay_ms=8,
        jitter_ms=2,
    )
    monkeypatch.setattr(
        runner,
        "_resolve_random_series_profile_seed",
        lambda execute: 42,
    )
    seeds = iter((101, 202))
    monkeypatch.setattr(
        runner,
        "_random_positive_seed",
        lambda excluded=None: next(seeds),
    )
    calls = []

    def fake_run_experiment(**kwargs):
        calls.append(kwargs)
        return json.dumps(
            _trace_slot(
                kwargs["first_slot_id"],
                root_seed=kwargs["policy_root_seed"],
            )
        )

    monkeypatch.setattr(runner, "run_experiment", fake_run_experiment)
    traces = runner.run_experiment_series(
        runs=2,
        trace_dir=tmp_path,
        skip_build=False,
        requested_flows=1,
        requested_stages=3,
        requested_replicas=1,
        rollout_batch_size=1,
        max_iterations=1,
        network_impairment=impairment,
    )

    assert [call["network_impairment"] for call in calls] == [
        impairment,
        impairment,
    ]
    assert [call["skip_build"] for call in calls] == [False, True]
    for trace in traces:
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        assert validate_hybrid_network_impairment_events(events) == impairment


def test_nonproduction_cli_exposes_no_netem_option():
    with pytest.raises(SystemExit):
        runner.parse_args(["run-small", "--netem", "1"])
    assert not hasattr(
        runner.parse_args(["run-small"]),
        "network_impairment",
    )


def test_policy_metrics_and_controller_resources_are_not_part_of_netem_patch():
    impairment = HybridNetworkImpairment.enabled_with(
        delay_ms=10,
        jitter_ms=3,
    )
    patch = runner._network_impairment_patch_document(
        stage=1,
        network_impairment=impairment,
    )
    text = json.dumps(patch, sort_keys=True)

    assert "controller" not in text
    assert "flow-generator" not in text
    assert "nodeSelector" not in text
    assert "affinity" not in text
    assert "SLA" not in text
    assert "belief" not in text
    assert "utility" not in text
