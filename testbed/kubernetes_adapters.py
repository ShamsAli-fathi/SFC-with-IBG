from pathlib import Path
import os
import re
import time

import httpx

from control_plane import ControlPlaneMeter
from datapath import KERNEL_DATAPATH_MODE, require_datapath_mode
from header import Replica, embedding
from latency_model import estimate_state, latency_likelihood
from learning_mode import (
    SEPARATED_LEARNING_SIGNAL_MODE,
    is_physical_only_diagnostic_mode,
    require_learning_signal_mode,
)
from ports import AdapterBundle, Observation, StageExecution
from simulation_adapters import NullResultSink
from testbed.flow_generator import RunSlotResponse, _has_complete_forwarding_path_v3
from testbed.profiles import require_profile


SERVICE_ACCOUNT_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")


class KubernetesApi:
    def __init__(
        self,
        namespace,
        *,
        base_url=None,
        token=None,
        verify=None,
        transport=None,
        timeout_seconds=10.0,
        control_plane_meter=None,
    ):
        self.namespace = namespace
        self.base_url = base_url or self._in_cluster_url()
        self.token = token if token is not None else self._service_account_token()
        self.verify = (
            verify
            if verify is not None
            else str(SERVICE_ACCOUNT_DIR / "ca.crt")
        )
        self.transport = transport
        self.timeout_seconds = timeout_seconds
        self.control_plane_meter = control_plane_meter

    @staticmethod
    def _in_cluster_url():
        host = os.environ.get("KUBERNETES_SERVICE_HOST")
        port = os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")
        if not host:
            raise RuntimeError("KUBERNETES_SERVICE_HOST is not configured")
        return f"https://{host}:{port}"

    @staticmethod
    def _service_account_token():
        return (SERVICE_ACCOUNT_DIR / "token").read_text(encoding="utf-8").strip()

    def list_stage_pods(self, stage):
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
                        "app.kubernetes.io/name=ibg-replica,"
                        f"ibg.stage={stage}"
                    )
                },
            )
            response.raise_for_status()
            payload = response.json()
            if self.control_plane_meter is not None:
                self.control_plane_meter.record_exchange(
                    request_field="kubernetes_discovery_tx",
                    response_field="kubernetes_discovery_rx",
                    request_payload_bytes=len(response.request.content),
                    response_payload_bytes=len(response.content),
                )
        return payload.get("items", [])


def _pod_is_ready(pod):
    status = pod.get("status", {})
    if status.get("phase") != "Running":
        return False
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in status.get("conditions", [])
    )


class KubernetesReplicaDiscovery:
    def __init__(self, api, namespace, expected_replicas):
        self.api = api
        self.namespace = namespace
        self.expected_replicas = expected_replicas

    def discover(self, stage, replica_list):
        discovered = {}
        for pod in self.api.list_stage_pods(stage):
            if not _pod_is_ready(pod):
                continue
            metadata = pod.get("metadata", {})
            pod_name = metadata.get("name", "")
            ordinal = re.search(r"-(\d+)$", pod_name)
            if ordinal is None:
                raise RuntimeError(
                    f"ready stage {stage} Pod has no StatefulSet ordinal: {pod_name}"
                )
            replica_id = int(ordinal.group(1)) + 1
            if replica_id > self.expected_replicas:
                continue
            key = (stage, replica_id)
            if key not in replica_list:
                raise RuntimeError(f"no solver replica configured for {key}")
            replica = replica_list[key]
            replica.pod_name = pod_name
            replica.node_name = pod.get("spec", {}).get("nodeName")
            replica.endpoint = (
                f"http://{pod_name}.stage-{stage}.{self.namespace}"
                ".svc.cluster.local.:8080"
            )
            discovered[key] = replica

        expected_ids = set(range(1, self.expected_replicas + 1))
        actual_ids = {key[1] for key in discovered}
        if actual_ids != expected_ids:
            raise RuntimeError(
                f"stage {stage} ready replicas {sorted(actual_ids)}; "
                f"expected {sorted(expected_ids)}"
            )
        return dict(sorted(discovered.items()))


class KubernetesPlacementExecutor:
    def execute_stage(self, policy, num_of_replicas, embed_dict, flow_list):
        updated_embed, assignments = embedding(
            policy,
            num_of_replicas,
            embed_dict,
            flow_list,
        )
        return StageExecution(updated_embed, assignments)


class KubernetesSlotTrafficExecutor:
    def __init__(
        self,
        flow_generator_url,
        *,
        timeout_seconds=30.0,
        transport=None,
        datapath_mode=KERNEL_DATAPATH_MODE,
        control_plane_meter=None,
        forwarder_cgroup_diagnostics=False,
        forwarding_path_diagnostics=False,
    ):
        self.flow_generator_url = flow_generator_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.datapath_mode = require_datapath_mode(
            datapath_mode,
            runtime=True,
        )
        self.telemetry = None
        self.control_plane_meter = control_plane_meter
        if not isinstance(forwarder_cgroup_diagnostics, bool):
            raise ValueError("forwarder cgroup diagnostics must be boolean")
        self.forwarder_cgroup_diagnostics = forwarder_cgroup_diagnostics
        if not isinstance(forwarding_path_diagnostics, bool):
            raise ValueError("forwarding path diagnostics must be boolean")
        self.forwarding_path_diagnostics = forwarding_path_diagnostics

    def execute_slot(self, slot_id, assignments_by_stage, discovered_by_stage):
        stages = sorted(assignments_by_stage)
        if stages != list(range(1, len(stages) + 1)):
            raise RuntimeError(
                "Kubernetes traffic requires contiguous stages starting at 1"
            )
        flow_ids = set(assignments_by_stage[1])
        if any(set(assignments_by_stage[stage]) != flow_ids for stage in stages):
            raise RuntimeError("stage assignments contain different flow IDs")

        routes = []
        for flow_id in sorted(flow_ids):
            hops = []
            for stage in stages:
                replica_id = assignments_by_stage[stage][flow_id]
                replica = discovered_by_stage[stage][(stage, replica_id)]
                hops.append(
                    {
                        "stage": stage,
                        "replica_id": replica_id,
                        "url": replica.endpoint,
                    }
                )
            routes.append({"flow_id": flow_id, "hops": hops})

        with httpx.Client(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            if self.control_plane_meter is not None:
                self.control_plane_meter.mark_route_dispatch()
            payload = {
                "datapath_mode": self.datapath_mode,
                "slot_id": slot_id,
                "routes": routes,
            }
            if self.forwarder_cgroup_diagnostics:
                payload["forwarder_cgroup_diagnostics"] = True
            if self.forwarding_path_diagnostics:
                payload["forwarding_path_diagnostics"] = True
            response = client.post(
                f"{self.flow_generator_url}/run-slot",
                json=payload,
            )
            if self.control_plane_meter is not None:
                self.control_plane_meter.mark_telemetry_received()
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                raise RuntimeError(
                    f"flow generator rejected slot {slot_id}: "
                    f"HTTP {response.status_code} {response.text}"
                ) from error
            if self.control_plane_meter is not None:
                self.control_plane_meter.record_exchange(
                    request_field="route_command_tx",
                    response_field="selected_telemetry_rx",
                    request_payload_bytes=len(response.request.content),
                    response_payload_bytes=len(response.content),
                )
            self.telemetry = RunSlotResponse.model_validate(response.json())
            if self.telemetry.datapath_mode != self.datapath_mode:
                raise RuntimeError(
                    "flow generator returned datapath mode "
                    f"{self.telemetry.datapath_mode!r}; expected "
                    f"{self.datapath_mode!r}"
                )
            if (
                self.forwarder_cgroup_diagnostics
                and self.telemetry.forwarder_cgroup is None
            ):
                raise RuntimeError(
                    "flow generator omitted requested forwarder cgroup diagnostics"
                )
            if self.forwarding_path_diagnostics and any(
                not _has_complete_forwarding_path_v3(flow.links)
                for flow in self.telemetry.flows
            ):
                raise RuntimeError(
                    "flow generator omitted requested forwarding path v3 diagnostics"
                )
        return self.telemetry


class KubernetesObservationCollector:
    def __init__(
        self,
        traffic_executor,
        learning_signal_mode=SEPARATED_LEARNING_SIGNAL_MODE,
    ):
        self.traffic_executor = traffic_executor
        self.learning_signal_mode = require_learning_signal_mode(
            learning_signal_mode
        )

    def collect(self, stage, assignments, replica_list):
        telemetry = self.traffic_executor.telemetry
        if telemetry is None:
            raise RuntimeError("slot traffic has not completed")

        hops = {
            (flow.flow_id, hop.stage): hop
            for flow in telemetry.flows
            for hop in flow.hops
        }
        observations = []
        for flow_id, replica_id in assignments.items():
            try:
                hop = hops[(flow_id, stage)]
            except KeyError as error:
                raise RuntimeError(
                    f"missing telemetry for flow {flow_id} stage {stage}"
                ) from error
            if hop.replica_id != replica_id:
                raise RuntimeError(
                    f"telemetry replica mismatch for flow {flow_id} stage {stage}"
                )
            if is_physical_only_diagnostic_mode(self.learning_signal_mode):
                signal = hop.processing_latency_ms
                likelihood = latency_likelihood(signal, hop.assigned_load)
                observation_jitter_ms = 0.0
                estimated_state = estimate_state(likelihood)
            else:
                signal = hop.signal_latency_ms
                likelihood = tuple(hop.state_likelihood)
                observation_jitter_ms = hop.observation_jitter_ms
                estimated_state = hop.state_estimate
            observations.append(
                Observation(
                    stage=stage,
                    flow_id=flow_id,
                    replica_id=replica_id,
                    congestion=hop.assigned_load,
                    signal=signal,
                    likelihood=tuple(likelihood),
                    measured_latency_ms=hop.processing_latency_ms,
                    estimated_state=estimated_state,
                    observation_jitter_ms=observation_jitter_ms,
                )
            )
        return observations


class KubernetesLinkLatencyCollector:
    """Sum measured costs across consecutive selected replica pairs."""

    def collect(self, traffic_telemetry):
        if traffic_telemetry is None:
            raise RuntimeError("slot traffic has not completed")
        return {
            flow.flow_id: sum(
                link.link_cost_ms
                for link in flow.links
            )
            for flow in traffic_telemetry.flows
        }


def build_replica_list(profiles, num_of_stages, num_of_replicas):
    replicas = {}
    for stage in range(1, num_of_stages + 1):
        for replica_id in range(1, num_of_replicas + 1):
            profile = require_profile(profiles, stage, replica_id)
            replicas[(stage, replica_id)] = Replica(
                stage=stage,
                replica=replica_id,
                belief=[0.25, 0.25, 0.25, 0.25],
                delay=profile.delay,
                cost=profile.cost,
                gamma=profile.gamma,
                state=profile.state,
                capacity=profile.capacity,
            )
    return replicas


def wait_for_ready_replicas(
    discovery,
    replica_list,
    num_of_stages,
    *,
    timeout_seconds=120.0,
    poll_seconds=2.0,
):
    deadline = time.monotonic() + timeout_seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            return {
                stage: discovery.discover(stage, replica_list)
                for stage in range(1, num_of_stages + 1)
            }
        except (RuntimeError, httpx.HTTPError) as error:
            last_error = error
            time.sleep(poll_seconds)
    raise RuntimeError(f"replicas did not become ready: {last_error}") from last_error


def make_kubernetes_adapters(
    discovery,
    flow_generator_url,
    *,
    result_sink=None,
    transport=None,
    datapath_mode=KERNEL_DATAPATH_MODE,
    control_plane_meter=None,
    learning_signal_mode=SEPARATED_LEARNING_SIGNAL_MODE,
    forwarder_cgroup_diagnostics=False,
    forwarding_path_diagnostics=False,
):
    learning_signal_mode = require_learning_signal_mode(learning_signal_mode)
    meter = control_plane_meter or ControlPlaneMeter()
    if hasattr(discovery, "api"):
        discovery.api.control_plane_meter = meter
    slot_traffic = KubernetesSlotTrafficExecutor(
        flow_generator_url,
        transport=transport,
        datapath_mode=datapath_mode,
        control_plane_meter=meter,
        forwarder_cgroup_diagnostics=forwarder_cgroup_diagnostics,
        forwarding_path_diagnostics=forwarding_path_diagnostics,
    )
    return AdapterBundle(
        replica_discovery=discovery,
        traffic_executor=KubernetesPlacementExecutor(),
        observation_collector=KubernetesObservationCollector(
            slot_traffic,
            learning_signal_mode=learning_signal_mode,
        ),
        result_sink=result_sink or NullResultSink(),
        slot_traffic_executor=slot_traffic,
        link_latency_collector=KubernetesLinkLatencyCollector(),
        control_plane_meter=meter,
        datapath_mode=slot_traffic.datapath_mode,
        learning_signal_mode=learning_signal_mode,
    )
