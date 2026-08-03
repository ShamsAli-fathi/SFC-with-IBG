"""MILP-owned Kubernetes discovery API and readiness predicate."""

from __future__ import annotations

import os
from pathlib import Path

import httpx


SERVICE_ACCOUNT_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")
MILP_REPLICA_APP_LABEL = "milp-replica"


class MILPKubernetesApi:
    """Namespace-scoped Ready discovery for the isolated MILP testbed."""

    def __init__(
        self,
        namespace: str,
        *,
        base_url: str | None = None,
        token: str | None = None,
        verify: bool | str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not namespace:
            raise ValueError("namespace must not be empty")
        self.namespace = namespace
        self.base_url = base_url if base_url is not None else self._in_cluster_url()
        self.token = token if token is not None else self._service_account_token()
        self.verify = verify if verify is not None else str(SERVICE_ACCOUNT_DIR / "ca.crt")
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _in_cluster_url() -> str:
        host = os.environ.get("KUBERNETES_SERVICE_HOST")
        port = os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")
        if not host:
            raise RuntimeError("KUBERNETES_SERVICE_HOST is not configured")
        return f"https://{host}:{port}"

    @staticmethod
    def _service_account_token() -> str:
        return (SERVICE_ACCOUNT_DIR / "token").read_text(encoding="utf-8").strip()

    def list_stage_pods(self, stage: int) -> list[dict[str, object]]:
        headers = {"Authorization": f"Bearer {self.token}"}
        with httpx.Client(
            base_url=self.base_url,
            headers=headers,
            verify=self.verify,
            transport=self.transport,
            timeout=self.timeout_seconds,
        ) as client:
            response = client.get(
                f"/api/v1/namespaces/{self.namespace}/pods",
                params={
                    "labelSelector": (
                        f"app.kubernetes.io/name={MILP_REPLICA_APP_LABEL},"
                        f"milp.stage={stage}"
                    )
                },
            )
            response.raise_for_status()
            payload = response.json()
        return payload.get("items", [])


def milp_pod_is_ready(pod: dict[str, object]) -> bool:
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
