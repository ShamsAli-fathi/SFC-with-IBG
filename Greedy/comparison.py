"""Typed Phase 1 fixture for matched Greedy/Hybrid comparison inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .contracts import GreedyConfiguration


GREEDY_HYBRID_MATCHED_COMPARISON_VERSION = (
    "greedy-hybrid-matched-comparison-v1"
)

ComparisonValue: TypeAlias = str | int | bool


REQUIRED_MATCHED_FIELDS = (
    "num_flows",
    "num_stages",
    "replicas_per_stage",
    "stage_budget",
    "jobs_per_paired_run",
    "max_iterations",
    "admission_capacity_per_replica",
    "ready_capacity_semantics",
    "materialized_runtime_profile_map",
    "runtime_profile_fingerprint",
    "root_seed",
    "flow_order_derivation",
    "physical_observation_input_schedule",
    "learning_and_metric_semantics",
    "private_processor_request",
    "private_processor_limit",
    "public_forwarder_request",
    "public_forwarder_limit",
    "flow_generator_request",
    "flow_generator_limit",
    "controller_request",
    "controller_limit",
    "private_processor_workers",
    "public_forwarder_workers",
    "private_processor_port",
    "public_forwarder_port",
    "downstream_server_keepalive_seconds",
    "discovery_http_timeout_seconds",
    "controller_flow_generator_timeout_seconds",
    "flow_generator_first_forwarder_timeout_seconds",
    "public_forwarder_request_timeout_seconds",
    "controller_discovery_client_ownership",
    "controller_flow_generator_client_ownership",
    "flow_generator_first_forwarder_client_ownership",
    "forwarder_private_processor_client_ownership",
    "forwarder_downstream_client_ownership",
    "controller_generator_requests_per_slot",
    "first_forwarder_requests_per_slot",
    "selected_hop_records_per_flow",
    "selected_pair_records_per_flow",
    "route_command_semantics",
    "selected_telemetry_semantics",
    "worker_topology",
    "rollout_batch_size",
    "ready_gate",
    "build_reuse_state",
    "warm_cold_state",
    "measurement_boundaries",
    "parity_replay_setting",
)


GREEDY_PHASE3_HYBRID_AUDIT_HEAD = "19229c274038db440f3cfdd62ed2102ea4c2c545"
GREEDY_PHASE4_HYBRID_AUDIT_HEAD = "f2e0065204570d9631f26953c94729b451ff92b5"
GREEDY_PHASE5_HYBRID_AUDIT_HEAD = "f2e0065204570d9631f26953c94729b451ff92b5"


@dataclass(frozen=True)
class Phase3HybridSourceAudit:
    boundary: str
    source_location: str
    git_blob: str
    disposition: str
    finding: str


GREEDY_PHASE3_HYBRID_SOURCE_AUDIT = (
    Phase3HybridSourceAudit("Ready discovery and persistent sync API client", "IBG_Hybrid/kernel_kubernetes_discovery.py:32-245", "b654bbc16eaaaf0e0613d60a2ebc98fff75a0ebc", "adapt", "10-second API request timeout; exact Running/Ready owned identity coverage; one controller-lifetime client."),
    Phase3HybridSourceAudit("finite controller and generator HTTP client", "IBG_Hybrid/kernel_controller.py:56-134,215-334,361-559", "b9408745de6175316481a47915423d16c9b1aea8", "adapt", "One 30-second synchronous generator client, one POST per slot, fail-before-belief-commit, and close-once ownership; policy pools excluded."),
    Phase3HybridSourceAudit("public controller input document", "IBG_Hybrid/kernel_controller_config.py:22-118", "f47ca640ec55cf4b4a199dd708f5a6e1a76e5163", "adapt", "Controller document excludes hidden state and runtime observation seeds; Hybrid planning links are excluded from Greedy."),
    Phase3HybridSourceAudit("controller executable boundary", "IBG_Hybrid/kernel_controller_service.py:20-66", "a9bff39c735e89fa7e39a1206af4ab0c6819d9fb", "adapt", "Finite controller closes owned ports; Hybrid console and policy-mode behavior are excluded."),
    Phase3HybridSourceAudit("two-hop request and telemetry schemas", "IBG_Hybrid/kernel_route_contracts.py:32-304", "c8b54d0183f6cabdc5640c9d875dbe67d43bc838", "adapt", "Two selected hops, final loads, one pair, canonical flows; Greedy generalizes hard-coded K=3/skipped-stage fields to arbitrary K bypass tuples and explicit position/next-hop fields."),
    Phase3HybridSourceAudit("concurrent selected-route executor", "IBG_Hybrid/kernel_route_execution.py:28-291", "aba1b3990a27b94229d576d2f0c20f2b88e524e7", "adapt", "10-second first-forwarder timeout, N concurrent requests, ordered per-flow hops, lifespan pool, direct-test ephemeral fallback, and strict correlation."),
    Phase3HybridSourceAudit("flow-generator ASGI lifecycle", "IBG_Hybrid/kernel_flow_generator.py:23-87", "b60183e4bd3ce3b0565cb6754fc6ece9cd2e6e59", "adapt", "One async pool starts and closes through ASGI lifespan, including startup failure cleanup."),
    Phase3HybridSourceAudit("private processor wrapper", "IBG_Hybrid/kernel_processor_service.py:18-59", "ecb1c8fb539deea1429bd114c6821c20682b7b0e", "reuse", "Shared processor owns hidden profile consumption and emits separated physical/observation telemetry without local learning."),
    Phase3HybridSourceAudit("two-selected-stage forwarder rule", "IBG_Hybrid/kernel_route_forwarder.py:15-38", "6d1e044a7ab94c3c117c7f810febaeb46da6de3b", "adapt", "Exactly one strictly later remaining hop; Greedy removes Hybrid's stage-3 ceiling for arbitrary K."),
    Phase3HybridSourceAudit("forwarder ASGI wrapper", "IBG_Hybrid/kernel_route_forwarder_service.py:15-23", "01c77ea880b95fcd9ca4d5ad809cd5663bb49b93", "adapt", "Shared service owns forwarder shutdown; Greedy supplies its own continuation runtime."),
    Phase3HybridSourceAudit("shared processor/forwarder HTTP behavior", "testbed/route_forwarder.py:29-78,590-625,761-885,1161-1253; testbed/cnf_service.py:29-320,330-523", "c112ba0d54cf3cb27a1997ed4c3312e52c2eebaf/7717aa7d35498491d3659d8ed7d79b589cac1c9b", "reuse", "Ports 8081/8080, separate local/downstream clients, 10-second request timeouts, 30-second downstream/server keep-alive, ordered forwarding, and separated telemetry."),
    Phase3HybridSourceAudit("runtime worker/client/port boundary", "IBG_Hybrid/kernel_infrastructure_contract.py:490-535", "b4b2d651c7903abc7f735983a0cd106e4b75f98b", "adapt", "One private worker, two public workers, ports 8081/8080, distinct local/downstream clients, and 30-second public keep-alive."),
    Phase3HybridSourceAudit("private processor and public forwarder resources", "deploy/hybrid-kubernetes/replicas.yaml:45-110", "830abdb9bbe908c74a43ba2437d0d0aef88c4809", "adapt", "Private 50m/128Mi to 1 CPU/768Mi; public 25m/128Mi to 1 CPU/256Mi; two public workers and 30-second server keep-alive."),
    Phase3HybridSourceAudit("flow-generator resources", "deploy/hybrid-kubernetes/flow-generator.yaml:35-57", "32ec288eeceef9c47ec5f80bcaa294716ac5f4be", "adapt", "Flow generator remains 50m/128Mi request and 1 CPU/768Mi limit."),
    Phase3HybridSourceAudit("controller resources", "deploy/hybrid-kubernetes/dynamic-controller-job.yaml:64-66", "1e4dbde99f3d76ee529192aae624a6ec87a05f61", "adapt", "Controller remains 2 CPU/256Mi request and 4 CPU/1Gi limit for matched comparison."),
)


@dataclass(frozen=True)
class Phase4HybridSourceAudit:
    boundary: str
    source_location: str
    git_blob: str
    disposition: str
    finding: str


GREEDY_PHASE4_HYBRID_SOURCE_AUDIT = (
    Phase4HybridSourceAudit("service image boundary", "deploy/hybrid-kubernetes/Dockerfile.service:1-38", "bdb6333a189a8b5a18ad693fd90654b174b32ed5", "adapt", "Azure Linux Python 3.12, non-root UID 10001, offline wheel-only install, explicit service source inventory, ports 8080/8081; Hybrid service namespace is excluded."),
    Phase4HybridSourceAudit("controller image boundary", "deploy/hybrid-kubernetes/Dockerfile.controller:1-43", "9c528adffa91311f9eb18582584189b65303a5b4", "adapt", "Separate non-root offline controller image; Greedy copies only its sequential controller dependencies and excludes Hybrid policy/MC/process-pool sources."),
    Phase4HybridSourceAudit("offline dependency validator", "scripts/hybrid_offline_wheelhouse.py:1-230", "412e66c89df29b1ea304a2a60fa379b5f981c3b2", "adapt", "Exact version/ABI/platform lock-to-manifest validation with no download boundary; Greedy owns separate manifests and cache paths."),
    Phase4HybridSourceAudit("namespace and discovery RBAC", "deploy/hybrid-kubernetes/namespace.yaml:1-7; deploy/hybrid-kubernetes/rbac.yaml:1-34", "f1a892dafcfac954e0ae5820ca950975f95a2b0a/e5599da43f04a8d0d55b2dd54e1b4a492cb68b62", "adapt", "Dedicated namespace and namespace Role limited to Pod get/list; all names and labels become Greedy-owned."),
    Phase4HybridSourceAudit("replica Pod template", "deploy/hybrid-kubernetes/replicas.yaml:1-286", "830abdb9bbe908c74a43ba2437d0d0aef88c4809", "adapt", "Headless Service/StatefulSet identity, two-container split, exact probes/resources/workers/ports/keep-alive, token disabled, and worker placement; Greedy generation supports arbitrary explicit K and M."),
    Phase4HybridSourceAudit("flow-generator resources", "deploy/hybrid-kubernetes/flow-generator.yaml:1-57", "32ec288eeceef9c47ec5f80bcaa294716ac5f4be", "adapt", "One worker-only token-free Deployment and Service with 50m/128Mi request, 1 CPU/768Mi limit, and health probes."),
    Phase4HybridSourceAudit("finite controller Job", "deploy/hybrid-kubernetes/dynamic-controller-job.yaml:1-75", "1e4dbde99f3d76ee529192aae624a6ec87a05f61", "adapt", "Worker-only one-shot Job, namespace discovery ServiceAccount, controller-only ConfigMap mount, 2 CPU/256Mi request and 4 CPU/1Gi limit; Hybrid planning/source overlays are excluded."),
    Phase4HybridSourceAudit("long-running base separation", "deploy/hybrid-kubernetes/kustomization.yaml:1-20", "2e4fcdfdf039837d74d57c9919b44a4a192e297e", "adapt", "Long-running resources and ConfigMaps exclude the controller Job; Greedy uses a dependency-free deterministic JSON/YAML renderer."),
    Phase4HybridSourceAudit("one-worker kind topology", "deploy/hybrid-kubernetes-phase4-small/kind-config.yaml:1-8", "e756783e3923bf87d69b9df2dc0df613ea1ba727", "adapt", "Exactly one control-plane and one labeled worker; Greedy changes only the ownership label."),
    Phase4HybridSourceAudit("runtime constants", "IBG_Hybrid/kernel_infrastructure_contract.py:490-535", "b4b2d651c7903abc7f735983a0cd106e4b75f98b", "reuse", "One private worker, two public workers, ports 8081/8080, separate clients, and 30-second public keep-alive remain matched."),
)


@dataclass(frozen=True)
class Phase5HybridSourceAudit:
    boundary: str
    source_location: str
    git_blob: str
    disposition: str
    finding: str


GREEDY_PHASE5_HYBRID_SOURCE_AUDIT = (
    Phase5HybridSourceAudit("dedicated cluster/context and fail-closed inventory", "scripts/run_hybrid_kernel_phase4.py:65-170,268-480", "c571940408423410df91480470a79f0007a0f68e", "adapt", "Use Greedy-only cluster/context/namespace/node identities; preserve exact two-node Ready and worker-placement refusal while excluding other baseline targets."),
    Phase5HybridSourceAudit("offline image build and image identity", "scripts/run_hybrid_kernel_phase4.py:482-690", "c571940408423410df91480470a79f0007a0f68e", "adapt", "Preserve wheelhouse-before-Docker, --pull=false, --network=none, normalized node-tag/full-ID validation, and change-scoped role ownership."),
    Phase5HybridSourceAudit("worker allocatable preflight", "scripts/run_hybrid_kernel_phase4.py:1041-1190", "c571940408423410df91480470a79f0007a0f68e", "adapt", "Run before mutation and include serving plus one 2-CPU/256Mi controller; Greedy uses its exact Phase 4 requests for arbitrary K/M."),
    Phase5HybridSourceAudit("bounded replica rollout and exact Ready coverage", "IBG_Hybrid/kernel_rollout.py:194-375", "2a766eb47c1149570b01999335d1cb56772709ff", "adapt", "Preserve append/high-suffix directionality and per-batch exact Running/Ready gates; generalize fixed three stages to arbitrary contiguous K."),
    Phase5HybridSourceAudit("seeded runtime profile allocation and transition validation", "IBG_Hybrid/kernel_profile_expansion.py:407-611,611-991", "8f10eb51ac4fce23a693ccda783f5828f60422d2", "adapt", "Reuse the environment-only 3/3/2/2 keyed state allocation and identity-stable observation-seed prefix; generalize stages and reject retained drift without importing Hybrid policy."),
    Phase5HybridSourceAudit("persistent reconcile and Job ordering", "scripts/run_hybrid_kernel_phase4.py:2534-3150", "c571940408423410df91480470a79f0007a0f68e", "adapt", "Preserve resource refusal, build/reuse split, scale-down-before-profile-projection, Ready-before-Job, and retained-process checks; add Greedy-owned stage changes and transition markers."),
    Phase5HybridSourceAudit("root/profile seed isolation", "scripts/run_hybrid_kernel_phase4.py:3224-3333", "c571940408423410df91480470a79f0007a0f68e", "adapt", "Use the same positive 63-bit system-random experiment-root boundary independently of the explicit profile seed, but create exactly one Greedy Job and no series loop."),
    Phase5HybridSourceAudit("production CLI and skip-build defaults", "scripts/run_hybrid_kernel_phase4.py:3400-3598", "c571940408423410df91480470a79f0007a0f68e", "adapt", "Match explicit dimensions, positive batch default 1, required finite bound, profile seed, skip-build, CSV/parity defaults; exclude runs, policy, MC, resource-profile, refresh, netem, and evidence options."),
    Phase5HybridSourceAudit("offline wheelhouse validator", "scripts/hybrid_offline_wheelhouse.py:1-230", "412e66c89df29b1ea304a2a60fa379b5f981c3b2", "reuse", "Reuse exact lock/manifest/ABI/platform validation through the existing Greedy-owned Phase 4 validator."),
    Phase5HybridSourceAudit("one-control-plane/one-worker kind topology", "deploy/hybrid-kubernetes-phase4-small/kind-config.yaml:1-8", "e756783e3923bf87d69b9df2dc0df613ea1ba727", "adapt", "Retain exactly two nodes and worker-only workload opportunity under Greedy names and labels."),
)

INTENTIONAL_POLICY_DIFFERENCE_FIELDS = (
    "selection_objective",
    "candidate_pruning",
    "activation",
    "planning_link_selection_term",
    "future_flow_lookahead",
    "monte_carlo",
    "policy_cli",
    "mc_workers_cli",
    "policy_process_pool",
    "real_flow_decision_order",
    "runs_cli",
)


@dataclass(frozen=True)
class MatchedComparisonField:
    name: str
    greedy_value: ComparisonValue
    hybrid_value: ComparisonValue
    source_location: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("matched field name must not be empty")
        if not self.source_location or ":" not in self.source_location:
            raise ValueError("matched fields require an exact source location")
        if self.greedy_value != self.hybrid_value:
            raise ValueError(f"required comparison field {self.name} is mismatched")


@dataclass(frozen=True)
class IntentionalPolicyDifference:
    name: str
    greedy_value: str
    hybrid_value: str
    reason: str

    def __post_init__(self) -> None:
        if not all((self.name, self.greedy_value, self.hybrid_value, self.reason)):
            raise ValueError("intentional differences require complete nonempty values")
        if self.greedy_value == self.hybrid_value:
            raise ValueError(f"intentional difference {self.name} must actually differ")


@dataclass(frozen=True)
class GreedyHybridMatchedComparison:
    version: str
    required_matches: tuple[MatchedComparisonField, ...]
    intentional_policy_differences: tuple[IntentionalPolicyDifference, ...]

    def __post_init__(self) -> None:
        matches = tuple(self.required_matches)
        differences = tuple(self.intentional_policy_differences)
        object.__setattr__(self, "required_matches", matches)
        object.__setattr__(self, "intentional_policy_differences", differences)
        if self.version != GREEDY_HYBRID_MATCHED_COMPARISON_VERSION:
            raise ValueError("unexpected Greedy/Hybrid comparison version")
        match_names = tuple(item.name for item in matches)
        difference_names = tuple(item.name for item in differences)
        if match_names != REQUIRED_MATCHED_FIELDS:
            raise ValueError("comparison fixture has incomplete or unordered required fields")
        if difference_names != INTENTIONAL_POLICY_DIFFERENCE_FIELDS:
            raise ValueError(
                "comparison fixture has incomplete or unordered policy differences"
            )

    def matched_value(self, name: str) -> ComparisonValue:
        try:
            return next(
                item.greedy_value
                for item in self.required_matches
                if item.name == name
            )
        except StopIteration as error:
            raise KeyError(name) from error

    @property
    def canonical_configuration(self) -> GreedyConfiguration:
        return GreedyConfiguration(
            num_flows=int(self.matched_value("num_flows")),
            num_stages=int(self.matched_value("num_stages")),
            num_replicas=int(self.matched_value("replicas_per_stage")),
        )


def _match(
    name: str,
    value: ComparisonValue,
    source: str,
) -> MatchedComparisonField:
    return MatchedComparisonField(name, value, value, source)


CANONICAL_MATCHED_COMPARISON = GreedyHybridMatchedComparison(
    version=GREEDY_HYBRID_MATCHED_COMPARISON_VERSION,
    required_matches=(
        _match("num_flows", 10, "scripts/run_hybrid_kernel_phase4.py:3413-3425"),
        _match("num_stages", 3, "scripts/run_hybrid_kernel_phase4.py:3427-3435"),
        _match("replicas_per_stage", 5, "scripts/run_hybrid_kernel_phase4.py:3436-3443"),
        _match("stage_budget", 2, "IBG_Hybrid/contracts.py:35-54"),
        _match("jobs_per_paired_run", 1, "scripts/run_hybrid_kernel_phase4.py:3587-3593"),
        _match("max_iterations", "same-explicit-positive-value", "scripts/run_hybrid_kernel_phase4.py:3502-3507"),
        _match("admission_capacity_per_replica", 2, "IBG_Hybrid/kernel_profile_expansion.py:587-600"),
        _match("ready_capacity_semantics", "ready-and-current-load-plus-one-within-declared-capacity", "IBG_Hybrid/phase0_contract.py:252-289"),
        _match("materialized_runtime_profile_map", "same-identity-aligned-hidden-state-and-observation-seed-map", "IBG_Hybrid/kernel_profile_expansion.py:476-760; Greedy/slot_contracts.py:55-96"),
        _match("runtime_profile_fingerprint", "same-materialized-map-fingerprint", "Greedy/slot_contracts.py:80-96"),
        _match("root_seed", "same-explicit-root-seed", "IBG_Hybrid/runner.py:660-720"),
        _match("flow_order_derivation", "same-versioned-root-and-slot-derivation", "IBG_Hybrid/phase0_contract.py:493-506; Greedy/simulation.py:27-76"),
        _match("physical_observation_input_schedule", "same-keyed-experiment-slot-flow-stage-replica-load-component-schedule", "IBG_Hybrid/simulation.py:21-138; Greedy/simulation.py:28-250"),
        _match("learning_and_metric_semantics", "same-separated-jitter-selected-only-physical-only-raw-pair-80ms-jain-equilibrium-0.04", "IBG_Hybrid/runner.py:277-400; Greedy/learning.py:17-94; Greedy/metrics.py:25-128"),
        _match("private_processor_request", "50m/128Mi", "deploy/hybrid-kubernetes/replicas.yaml:79-81"),
        _match("private_processor_limit", "1CPU/768Mi", "deploy/hybrid-kubernetes/replicas.yaml:79-81"),
        _match("public_forwarder_request", "25m/128Mi", "deploy/hybrid-kubernetes/replicas.yaml:108-110"),
        _match("public_forwarder_limit", "1CPU/256Mi", "deploy/hybrid-kubernetes/replicas.yaml:108-110"),
        _match("flow_generator_request", "50m/128Mi", "deploy/hybrid-kubernetes/flow-generator.yaml:55-57"),
        _match("flow_generator_limit", "1CPU/768Mi", "deploy/hybrid-kubernetes/flow-generator.yaml:55-57"),
        _match("controller_request", "2CPU/256Mi", "deploy/hybrid-kubernetes/dynamic-controller-job.yaml:64-66"),
        _match("controller_limit", "4CPU/1Gi", "deploy/hybrid-kubernetes/dynamic-controller-job.yaml:64-66"),
        _match("private_processor_workers", 1, "IBG_Hybrid/kernel_infrastructure_contract.py:490-527"),
        _match("public_forwarder_workers", 2, "IBG_Hybrid/kernel_infrastructure_contract.py:490-527"),
        _match("private_processor_port", 8081, "IBG_Hybrid/kernel_infrastructure_contract.py:490-527"),
        _match("public_forwarder_port", 8080, "IBG_Hybrid/kernel_infrastructure_contract.py:490-527"),
        _match("downstream_server_keepalive_seconds", 30, "IBG_Hybrid/kernel_infrastructure_contract.py:490-527"),
        _match("discovery_http_timeout_seconds", 10, "IBG_Hybrid/kernel_kubernetes_discovery.py:32-66"),
        _match("controller_flow_generator_timeout_seconds", 30, "IBG_Hybrid/kernel_controller.py:71-93"),
        _match("flow_generator_first_forwarder_timeout_seconds", 10, "IBG_Hybrid/kernel_route_execution.py:32-79"),
        _match("public_forwarder_request_timeout_seconds", 10, "testbed/route_forwarder.py:29-78,590-612"),
        _match("controller_discovery_client_ownership", "one-persistent-sync-controller-lifetime", "IBG_Hybrid/kernel_kubernetes_discovery.py:32-82"),
        _match("controller_flow_generator_client_ownership", "one-persistent-sync-controller-lifetime", "IBG_Hybrid/kernel_controller.py:71-109,361-470"),
        _match("flow_generator_first_forwarder_client_ownership", "one-persistent-async-asgi-lifespan", "IBG_Hybrid/kernel_route_execution.py:53-135; IBG_Hybrid/kernel_flow_generator.py:37-58"),
        _match("forwarder_private_processor_client_ownership", "separate-persistent-async-local-client-default-idle", "testbed/route_forwarder.py:590-625"),
        _match("forwarder_downstream_client_ownership", "separate-persistent-async-downstream-client-30s", "testbed/route_forwarder.py:590-625"),
        _match("controller_generator_requests_per_slot", 1, "IBG_Hybrid/kernel_controller.py:215-261,504-508"),
        _match("first_forwarder_requests_per_slot", "N-one-per-logical-flow", "IBG_Hybrid/kernel_route_execution.py:103-135,137-196"),
        _match("selected_hop_records_per_flow", 2, "IBG_Hybrid/kernel_route_contracts.py:117-204"),
        _match("selected_pair_records_per_flow", 1, "IBG_Hybrid/kernel_route_contracts.py:161-204,239-245"),
        _match("route_command_semantics", "slot-envelope-with-N-complete-two-hop-routes-and-final-loads", "IBG_Hybrid/kernel_route_contracts.py:36-114,248-304"),
        _match("selected_telemetry_semantics", "two-correlated-selected-hops-plus-one-measured-pair-per-flow", "IBG_Hybrid/kernel_route_contracts.py:117-245; IBG_Hybrid/kernel_controller.py:263-334"),
        _match("worker_topology", "one-control-plane-one-worker-worker-only", "deploy/hybrid-kubernetes-phase4-small/kind-config.yaml:1-8; deploy/hybrid-kubernetes/replicas.yaml:46-49"),
        _match("rollout_batch_size", "same-explicit-positive-value", "scripts/run_hybrid_kernel_phase4.py:3445-3449"),
        _match("ready_gate", "same-exact-running-ready-ordinal-coverage", "IBG_Hybrid/kernel_rollout.py:318-375"),
        _match("build_reuse_state", "same-build-or-validated-skip-build-mode", "scripts/run_hybrid_kernel_phase4.py:3405-3411"),
        _match("warm_cold_state", "same-recorded-serving-pod-retention-state", "scripts/run_hybrid_kernel_phase4.py:2700-3001"),
        _match("measurement_boundaries", "same-jsonl-timing-and-controller-footprint-boundaries", "scripts/run_hybrid_kernel_phase4.py:1988-2230"),
        _match("parity_replay_setting", "same-explicit-zero-or-one-setting", "scripts/run_hybrid_kernel_phase4.py:3526-3534"),
    ),
    intentional_policy_differences=(
        IntentionalPolicyDifference("selection_objective", "exhaustive-immediate-stage-utility-sum", "pruned-lookahead-focal-final-load", "Defining policy difference."),
        IntentionalPolicyDifference("candidate_pruning", "absent", "five-per-stage", "Pure Greedy evaluates all feasible actions."),
        IntentionalPolicyDifference("activation", "absent", "lookahead-path", "Pure Greedy has one policy path."),
        IntentionalPolicyDifference("planning_link_selection_term", "absent", "directed-pair-cost", "Pair latency is post-selection telemetry for Greedy."),
        IntentionalPolicyDifference("future_flow_lookahead", "absent", "deterministic-D2", "Pure Greedy is myopic."),
        IntentionalPolicyDifference("monte_carlo", "absent", "manual-mode", "Sampled continuations are excluded."),
        IntentionalPolicyDifference("policy_cli", "absent", "--policy", "Greedy exposes no alternate policy selector."),
        IntentionalPolicyDifference("mc_workers_cli", "absent", "--mc-workers", "Greedy has no MC worker setting."),
        IntentionalPolicyDifference("policy_process_pool", "absent", "persistent-four-process-lookahead-pool", "Greedy decisions remain sequential."),
        IntentionalPolicyDifference("real_flow_decision_order", "sequential-immediate-commit", "sequential-with-parallel-focal-evaluation", "Both commit real flows sequentially; only Hybrid parallelizes focal work."),
        IntentionalPolicyDifference("runs_cli", "absent-one-run-per-invocation", "optional---runs", "Paired comparison invokes Hybrid once and Greedy never repeats internally."),
    ),
)
