"""MILP-specific projection of the frozen lightweight runtime resources."""

from __future__ import annotations

from testbed.kubernetes_resources import build_runtime_resources

from .kernel_contracts import MILP_TWO_HOP_ROUTE_CONTRACT_VERSION


EXACT_FORWARDER_APP = "testbed.route_forwarder:app"
MILP_FORWARDER_APP = "MILP.kernel_route_forwarder:app"


def build_milp_kernel_runtime_resources(
    profiles,
    *,
    num_of_stages: int,
    num_of_replicas: int,
    namespace: str,
    image: str,
):
    """Reuse Exact resources while replacing only the MILP forwarder app."""

    resources = build_runtime_resources(
        profiles,
        num_of_stages=num_of_stages,
        num_of_replicas=num_of_replicas,
        namespace=namespace,
        image=image,
    )
    adapted = 0
    for item in resources["items"]:
        if item.get("kind") != "StatefulSet":
            continue
        template = item["spec"]["template"]
        containers = template["spec"]["containers"]
        forwarder = next(
            (container for container in containers if container.get("name") == "forwarder"),
            None,
        )
        if forwarder is None or EXACT_FORWARDER_APP not in forwarder.get("command", ()):
            raise RuntimeError("unexpected Exact forwarder resource shape")
        forwarder["command"] = [
            MILP_FORWARDER_APP if value == EXACT_FORWARDER_APP else value
            for value in forwarder["command"]
        ]
        template.setdefault("metadata", {}).setdefault("annotations", {})[
            "milp.route-contract-version"
        ] = MILP_TWO_HOP_ROUTE_CONTRACT_VERSION
        adapted += 1
    if adapted != num_of_stages:
        raise RuntimeError(
            f"expected {num_of_stages} MILP StatefulSets, adapted {adapted}"
        )
    return resources
