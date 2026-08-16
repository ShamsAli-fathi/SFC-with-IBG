"""Hybrid-owned, Ready-only Kubernetes Pod discovery adapter."""

from __future__ import annotations

import os
from pathlib import Path
import re
import time
from typing import Callable

import httpx

from .contracts import HybridConfiguration, ReplicaChoice
from .control_plane_footprint import HybridControlPlaneDataMeter
from .kernel_infrastructure_contract import (
    DEFAULT_HYBRID_KERNEL_OWNERSHIP,
    HybridKernelContractError,
    HybridKernelDiscoveredReplica,
    HybridKernelDiscoverySnapshot,
    HybridKernelOwnership,
)


HYBRID_KERNEL_KUBERNETES_DISCOVERY_ADAPTER_VERSION = (
    "ibg-hybrid-kubernetes-ready-discovery-adapter-v1"
)
SERVICE_ACCOUNT_DIRECTORY = Path(
    "/var/run/secrets/kubernetes.io/serviceaccount"
)


class HybridKubernetesApi:
    """Namespace-scoped Kubernetes Core API reader for Hybrid replica Pods."""

    def __init__(
        self,
        *,
        ownership: HybridKernelOwnership = DEFAULT_HYBRID_KERNEL_OWNERSHIP,
        base_url: str | None = None,
        token: str | None = None,
        verify: str | bool | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 10.0,
        control_plane_meter: HybridControlPlaneDataMeter | None = None,
    ) -> None:
        self.ownership = ownership
        self.base_url = base_url or self._in_cluster_url()
        self.token = token if token is not None else self._service_account_token()
        self.verify = (
            verify
            if verify is not None
            else str(SERVICE_ACCOUNT_DIRECTORY / "ca.crt")
        )
        self.transport = transport
        self.timeout_seconds = float(timeout_seconds)
        self.control_plane_meter = control_plane_meter
        self._last_exchange_payload_bytes: tuple[int, int] | None = None
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    @staticmethod
    def _in_cluster_url() -> str:
        host = os.environ.get("KUBERNETES_SERVICE_HOST")
        port = os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")
        if not host:
            raise RuntimeError("KUBERNETES_SERVICE_HOST is not configured")
        return f"https://{host}:{port}"

    @staticmethod
    def _service_account_token() -> str:
        return (SERVICE_ACCOUNT_DIRECTORY / "token").read_text(
            encoding="utf-8"
        ).strip()

    def list_hybrid_replica_pods(self) -> tuple[dict[str, object], ...]:
        selector = ",".join(
            (
                f"app.kubernetes.io/name={self.ownership.replica_name_label}",
                f"app.kubernetes.io/part-of={self.ownership.part_of_label}",
                "app.kubernetes.io/component=replica-stage",
            )
        )
        with httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}"},
            verify=self.verify,
            transport=self.transport,
            timeout=self.timeout_seconds,
        ) as client:
            response = client.get(
                f"/api/v1/namespaces/{self.ownership.namespace}/pods",
                params={"labelSelector": selector},
            )
            response.raise_for_status()
            payload = response.json()
            self._last_exchange_payload_bytes = (
                len(response.request.content),
                len(response.content),
            )
        items = payload.get("items")
        if not isinstance(items, list):
            raise HybridKernelContractError(
                "Kubernetes Pod list response must contain an items list"
            )
        return tuple(items)

    def record_last_successful_discovery_exchange(self) -> None:
        if self.control_plane_meter is None:
            return
        if self._last_exchange_payload_bytes is None:
            raise RuntimeError("Hybrid Kubernetes discovery exchange is unavailable")
        request_bytes, response_bytes = self._last_exchange_payload_bytes
        self.control_plane_meter.record_exchange(
            request_field="kubernetes_discovery_tx",
            response_field="kubernetes_discovery_rx",
            request_payload_bytes=request_bytes,
            response_payload_bytes=response_bytes,
        )


def _is_ready(pod: dict[str, object]) -> bool:
    status = pod.get("status", {})
    if not isinstance(status, dict) or status.get("phase") != "Running":
        return False
    conditions = status.get("conditions", [])
    return isinstance(conditions, list) and any(
        isinstance(condition, dict)
        and condition.get("type") == "Ready"
        and condition.get("status") == "True"
        for condition in conditions
    )


class HybridKubernetesReplicaDiscovery:
    """Convert one exact Hybrid Pod list into the immutable Phase 0 snapshot."""

    def __init__(
        self,
        api: HybridKubernetesApi,
        configuration: HybridConfiguration,
        *,
        ownership: HybridKernelOwnership = DEFAULT_HYBRID_KERNEL_OWNERSHIP,
    ) -> None:
        if api.ownership != ownership:
            raise ValueError("Kubernetes API and discovery ownership must match")
        self.api = api
        self.configuration = configuration
        self.ownership = ownership

    def discover_complete_ready(self) -> HybridKernelDiscoverySnapshot:
        replicas = []
        for pod in self.api.list_hybrid_replica_pods():
            metadata = pod.get("metadata", {})
            status = pod.get("status", {})
            spec = pod.get("spec", {})
            if not all(isinstance(value, dict) for value in (metadata, status, spec)):
                raise HybridKernelContractError("Pod metadata/status/spec must be mappings")
            labels = metadata.get("labels", {})
            if not isinstance(labels, dict):
                raise HybridKernelContractError("Pod labels must be a mapping")
            stage_text = labels.get(self.ownership.stage_label_key)
            if not isinstance(stage_text, str) or not stage_text.isdigit():
                raise HybridKernelContractError("Hybrid Pod stage label is missing or invalid")
            stage = int(stage_text)
            pod_name = metadata.get("name")
            expected_prefix = f"{self.ownership.stage_name(stage)}-"
            if not isinstance(pod_name, str) or not pod_name.startswith(expected_prefix):
                raise HybridKernelContractError("Hybrid Pod StatefulSet identity mismatch")
            ordinal = re.fullmatch(re.escape(expected_prefix) + r"(\d+)", pod_name)
            if ordinal is None:
                raise HybridKernelContractError("Hybrid Pod has no exact StatefulSet ordinal")
            replica = int(ordinal.group(1)) + 1
            namespace = metadata.get("namespace")
            uid = metadata.get("uid")
            phase = status.get("phase")
            node_name = spec.get("nodeName")
            replicas.append(
                HybridKernelDiscoveredReplica(
                    choice=ReplicaChoice(stage, replica),
                    namespace=namespace,
                    pod_name=pod_name,
                    pod_uid=uid,
                    node_name=node_name,
                    endpoint=(
                        f"http://{pod_name}.{self.ownership.stage_name(stage)}."
                        f"{self.ownership.namespace}.svc.cluster.local.:8080"
                    ),
                    labels=tuple(sorted(labels.items())),
                    phase=phase,
                    ready=_is_ready(pod),
                )
            )
        snapshot = HybridKernelDiscoverySnapshot(
            configuration=self.configuration,
            replicas=tuple(replicas),
            ownership=self.ownership,
        )
        # Count only the aggregate Pod-list response that produced the accepted
        # complete Ready snapshot.  Transient incomplete polling attempts never
        # become part of completed-slot evidence.
        self.api.record_last_successful_discovery_exchange()
        return snapshot

    def wait_for_complete_ready(
        self,
        *,
        timeout_seconds: float = 120.0,
        poll_seconds: float = 2.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> HybridKernelDiscoverySnapshot:
        if timeout_seconds <= 0 or poll_seconds <= 0:
            raise ValueError("discovery timeout and poll interval must be positive")
        deadline = monotonic() + timeout_seconds
        last_error: Exception | None = None
        while monotonic() < deadline:
            try:
                return self.discover_complete_ready()
            except (HybridKernelContractError, httpx.HTTPError) as error:
                last_error = error
                sleep(poll_seconds)
        raise HybridKernelContractError(
            f"Hybrid replicas did not become completely Ready: {last_error}"
        ) from last_error
