"""Greedy-owned persistent, namespace-scoped Ready Pod discovery adapter."""

from __future__ import annotations

import os
from pathlib import Path
import re
import time
from typing import Callable

import httpx

from .control_plane_footprint import GreedyControlPlaneMeter
from .contracts import GreedyConfiguration, ReplicaIdentity
from .kernel_contracts import (
    DEFAULT_GREEDY_KERNEL_OWNERSHIP,
    GREEDY_KERNEL_DISCOVERY_TIMEOUT_SECONDS,
    GreedyClientLifecycle,
    GreedyKernelContractError,
    GreedyKernelDiscoveredReplica,
    GreedyKernelDiscoverySnapshot,
    GreedyKernelOwnership,
)


SERVICE_ACCOUNT_DIRECTORY = Path("/var/run/secrets/kubernetes.io/serviceaccount")


class GreedyKubernetesApi:
    """Own one synchronous Kubernetes client for the controller lifetime."""

    def __init__(
        self,
        *,
        ownership: GreedyKernelOwnership = DEFAULT_GREEDY_KERNEL_OWNERSHIP,
        base_url: str | None = None,
        token: str | None = None,
        verify: str | bool | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = GREEDY_KERNEL_DISCOVERY_TIMEOUT_SECONDS,
        control_plane_meter: GreedyControlPlaneMeter | None = None,
    ) -> None:
        self.ownership = ownership
        self.base_url = base_url or self._in_cluster_url()
        self.token = token if token is not None else self._service_account_token()
        self.verify = (
            verify
            if verify is not None
            else str(SERVICE_ACCOUNT_DIRECTORY / "ca.crt")
        )
        self.timeout_seconds = float(timeout_seconds)
        self.control_plane_meter = control_plane_meter
        self._last_exchange_payload_bytes: tuple[int, int] | None = None
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}"},
            verify=self.verify,
            transport=transport,
            timeout=self.timeout_seconds,
        )
        self._close_calls = 0

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

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    @property
    def lifecycle(self) -> GreedyClientLifecycle:
        return GreedyClientLifecycle(
            owner="finite-controller-discovery",
            scope="controller-lifetime",
            client_instances=1,
            close_calls=self._close_calls,
            closed=self.is_closed,
        )

    def close(self) -> None:
        if self.is_closed:
            return
        self._client.close()
        self._close_calls += 1

    def __enter__(self) -> GreedyKubernetesApi:
        if self.is_closed:
            raise RuntimeError("Greedy Kubernetes API client is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def list_greedy_replica_pods(self) -> tuple[dict[str, object], ...]:
        if self.is_closed:
            raise RuntimeError("Greedy Kubernetes API client is closed")
        selector = ",".join(
            (
                f"app.kubernetes.io/name={self.ownership.replica_name_label}",
                f"app.kubernetes.io/part-of={self.ownership.part_of_label}",
                "app.kubernetes.io/component=replica-stage",
            )
        )
        response = self._client.get(
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
            raise GreedyKernelContractError(
                "Kubernetes Pod list response must contain an items list"
            )
        return tuple(items)

    def record_last_successful_discovery_exchange(self) -> None:
        if self.control_plane_meter is None:
            return
        if self._last_exchange_payload_bytes is None:
            raise RuntimeError("Greedy Kubernetes discovery exchange is unavailable")
        request_bytes, response_bytes = self._last_exchange_payload_bytes
        self.control_plane_meter.record_exchange(
            request_field="kubernetes_discovery_tx",
            response_field="kubernetes_discovery_rx",
            request_payload_bytes=request_bytes,
            response_payload_bytes=response_bytes,
        )


def _is_ready(status: dict[str, object]) -> bool:
    conditions = status.get("conditions", [])
    return isinstance(conditions, list) and any(
        isinstance(condition, dict)
        and condition.get("type") == "Ready"
        and condition.get("status") == "True"
        for condition in conditions
    )


class GreedyKubernetesReplicaDiscovery:
    """Translate only public Pod identity/readiness/endpoint metadata."""

    def __init__(
        self,
        api: GreedyKubernetesApi,
        configuration: GreedyConfiguration,
        *,
        ownership: GreedyKernelOwnership = DEFAULT_GREEDY_KERNEL_OWNERSHIP,
    ) -> None:
        if api.ownership != ownership:
            raise ValueError("Kubernetes API and discovery ownership must match")
        self.api = api
        self.configuration = configuration
        self.ownership = ownership

    @property
    def lifecycle(self) -> GreedyClientLifecycle:
        return self.api.lifecycle

    def close(self) -> None:
        self.api.close()

    def discover_complete_ready(self) -> GreedyKernelDiscoverySnapshot:
        replicas = []
        for pod in self.api.list_greedy_replica_pods():
            if not isinstance(pod, dict):
                raise GreedyKernelContractError("Pod entry must be a mapping")
            metadata = pod.get("metadata")
            status = pod.get("status")
            spec = pod.get("spec")
            if not all(isinstance(value, dict) for value in (metadata, status, spec)):
                raise GreedyKernelContractError("Pod metadata/status/spec must be mappings")
            labels = metadata.get("labels")
            if not isinstance(labels, dict):
                raise GreedyKernelContractError("Pod labels must be a mapping")
            stage_text = labels.get(self.ownership.stage_label_key)
            if not isinstance(stage_text, str) or not stage_text.isdigit():
                raise GreedyKernelContractError("Greedy Pod stage label is malformed")
            stage = int(stage_text)
            prefix = f"{self.ownership.stage_name(stage)}-"
            pod_name = metadata.get("name")
            if not isinstance(pod_name, str):
                raise GreedyKernelContractError("Greedy Pod name is malformed")
            ordinal = re.fullmatch(re.escape(prefix) + r"(\d+)", pod_name)
            if ordinal is None:
                raise GreedyKernelContractError("Greedy Pod StatefulSet identity mismatch")
            replica_id = int(ordinal.group(1)) + 1
            replicas.append(
                GreedyKernelDiscoveredReplica(
                    identity=ReplicaIdentity(stage, replica_id),
                    namespace=metadata.get("namespace"),
                    pod_name=pod_name,
                    pod_uid=metadata.get("uid"),
                    node_name=spec.get("nodeName"),
                    endpoint=(
                        f"http://{pod_name}.{self.ownership.stage_name(stage)}."
                        f"{self.ownership.namespace}.svc.cluster.local.:8080"
                    ),
                    phase=status.get("phase"),
                    ready=_is_ready(status),
                    labels=tuple(sorted((str(key), str(value)) for key, value in labels.items())),
                )
            )
        snapshot = GreedyKernelDiscoverySnapshot(
            configuration=self.configuration,
            replicas=tuple(sorted(replicas, key=lambda value: value.identity)),
            ownership=self.ownership,
        )
        self.api.record_last_successful_discovery_exchange()
        return snapshot

    def wait_for_complete_ready(
        self,
        *,
        timeout_seconds: float = 120.0,
        poll_seconds: float = 2.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> GreedyKernelDiscoverySnapshot:
        if timeout_seconds <= 0 or poll_seconds <= 0:
            raise ValueError("discovery timeout and poll interval must be positive")
        deadline = float(monotonic()) + float(timeout_seconds)
        last_error: Exception | None = None
        while float(monotonic()) < deadline:
            try:
                return self.discover_complete_ready()
            except (GreedyKernelContractError, httpx.HTTPError) as error:
                last_error = error
                sleep(poll_seconds)
        raise GreedyKernelContractError(
            f"Greedy replicas did not become completely Ready: {last_error}"
        ) from last_error
