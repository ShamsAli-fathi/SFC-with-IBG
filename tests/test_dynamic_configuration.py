import json
from pathlib import Path

from testbed.kubernetes_resources import build_runtime_resources
from testbed.profiles import expand_profiles, load_profiles


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "deploy" / "kubernetes" / "profiles.json"


def test_default_profile_dimensions_preserve_validated_profiles():
    profiles = load_profiles(PROFILE_PATH)

    assert expand_profiles(profiles, 3, 5) == profiles


def test_profiles_extend_deterministically_for_new_stages_and_replicas():
    base = load_profiles(PROFILE_PATH)

    first = expand_profiles(base, 4, 7)
    second = expand_profiles(base, 4, 7)

    assert first == second
    assert len(first) == 28
    assert (4, 7) in first
    seeds = [profile.observation_seed for profile in first.values()]
    assert None not in seeds
    assert len(seeds) == len(set(seeds))


def test_runtime_resources_match_requested_dimensions():
    profiles = expand_profiles(load_profiles(PROFILE_PATH), 4, 7)

    resources = build_runtime_resources(
        profiles,
        num_of_stages=4,
        num_of_replicas=7,
    )

    stateful_sets = {
        item["metadata"]["name"]: item
        for item in resources["items"]
        if item["kind"] == "StatefulSet"
    }
    services = [item for item in resources["items"] if item["kind"] == "Service"]
    config_map = next(
        item for item in resources["items"] if item["kind"] == "ConfigMap"
    )
    document = json.loads(config_map["data"]["profiles.json"])

    assert list(stateful_sets) == ["stage-1", "stage-2", "stage-3", "stage-4"]
    assert len(services) == 4
    assert all(item["spec"]["replicas"] == 7 for item in stateful_sets.values())
    containers = stateful_sets["stage-4"]["spec"]["template"]["spec"][
        "containers"
    ]
    assert [container["name"] for container in containers] == [
        "replica",
        "forwarder",
    ]
    assert containers[0]["env"][0] == {"name": "STAGE", "value": "4"}
    assert containers[0]["command"][-1] == "8081"
    assert containers[0]["ports"] == [
        {"name": "processor", "containerPort": 8081}
    ]
    assert containers[0]["readinessProbe"]["httpGet"]["path"] == "/warmup"
    assert containers[1]["command"][-1] == "8080"
    assert containers[1]["ports"] == [
        {"name": "http", "containerPort": 8080}
    ]
    assert {
        item["name"]: item.get("value") for item in containers[1]["env"]
    }["PROCESSOR_URL"] == "http://127.0.0.1:8081"
    assert len(document["stages"]) == 4
    assert len(document["stages"]["4"]) == 7
