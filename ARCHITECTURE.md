# IBG Testbed Architecture

## Current system

`IBG/` is a working pure-Python simulation. Its active migrated path is the small-scale, decoupled per-stage IBG: `IBG/main.py` constructs experiments, `IBG/runner.py` orchestrates one import-safe decoupled slot through adapter contracts, `IBG/claude.py` computes per-stage utility grids and the exact memoized `BR_EIBG` continuation policy, and `IBG/header.py` contains the replica, learning, embedding, and metric logic. Simulation adapters provide stage-scoped discovery, embedding, reference observations, and CSV storage. Kubernetes adapters provide readiness-filtered discovery and complete-route traffic/telemetry while reusing the same solver, embedding, learning, equilibrium, and metric functions. The separate budgeted/coupled code is retained as reference material but is not part of the current migration.

## IBG Exact solver contract

For each decoupled stage, the solver builds a belief-driven utility grid using 30 Monte Carlo processing-latency samples per replica and load. Each sample draws a possible hidden state from the current belief and then draws from that state's load-conditioned positive latency law. `BR_EIBG` solves the sequential one-replica-per-stage game exactly with respect to the resulting sampled grid.

Each subgame is identified by the next player and the full vector of loads already assigned to the stage's replica slots. The solver branches over every active replica, recursively solves the continuation game, evaluates the current player's choice at its predicted final load, and selects the best continuation-consistent action. Subgames are memoized by load vector, and exact ties select the lowest replica ID for deterministic behavior. The former `backward_d_memoized_simple` name remains only as a compatibility wrapper around `br_eibg_exact`.

This one-of-M generalization is intentionally limited to small instances. With `N` flows and `M` active replicas, the number of cached load vectors through the terminal depth is `C(N+M, M)`. The supported three-flow/five-replica case has 56 states. Scaling beyond this exact testbed would require a different approximate algorithm and is outside the current implemented roadmap.

## Target testbed

```text
Windows 11
  -> WSL2 Ubuntu + native Docker Engine
    -> kind cluster
      -> 1 control-plane node
      -> 2 worker nodes
        -> Stage 1 StatefulSet: 5 HTTP CNF Pods
        -> Stage 2 StatefulSet: 5 HTTP CNF Pods
        -> Stage 3 StatefulSet: 5 HTTP CNF Pods
      -> Python IBG controller Pod
      -> lightweight flow-generator Pod
```

The three kind nodes are cluster machines; the three stage StatefulSets are workloads scheduled across the two workers. Each StatefulSet uses stable Pod ordinals to map directly to `(stage, replica)` and does not use persistent volumes.

Kubernetes schedules the long-running replica Pods onto worker nodes. The IBG solver does not reschedule Pods; it selects one already-running Pod endpoint per stage for each logical flow. A flow therefore becomes a three-hop route through selected stage Pods.

Development tools, source code, Docker Engine, and cluster state live inside the Ubuntu filesystem. Windows provides the WSL2 host only; Docker Desktop is not part of the testbed.

## Runtime flow

1. The controller discovers healthy replica Pods and their stable identities through the Kubernetes API.
2. A slot admits 3 logical flows in one randomized sequential order.
3. The exact decoupled `BR_EIBG` solver selects one replica at each of the three stages for every flow.
4. The controller records/applies those assignments.
5. The flow generator exercises the selected three-Pod paths concurrently through lightweight HTTP requests.
6. Only selected replicas return per-request signals such as latency and concurrent load.
7. The controller updates replica beliefs using the existing learning rule and records utility, SLA, fairness, timing, placement, and belief results.

The HTTP Pods are test doubles, not real AMF/SMF/UPF functions. Their `/health` and `/process` behavior supplies real Kubernetes networking and state/load-conditioned processing latency without specialized dataplane hardware. Selected server processing latency is the continuous private signal used for belief likelihoods. Client request latency, modeled delay, actual admission concurrency, assigned load, and transport overhead remain separately correlated telemetry.

## HTTP replica contract

The FastAPI/Uvicorn replica exposes `GET /health` for readiness, stable identity, and current concurrency. `POST /process` accepts positive slot/flow IDs and final `assigned_load`, samples state-conditioned modeled processing delay, performs the work, and returns modeled/measured processing latency, admitted concurrency, a categorical state estimate, and the four-state load-aware likelihood vector. Transitional `legacy_*` aliases remain in the wire response for trace compatibility but do not define the active belief model.

Replica identity, hidden state, capacity, baseline delay, congestion parameters, and jitter seed are deterministic environment configuration. The service increments a shared request counter before modeled work, applies the sampled state/load-conditioned delay, and decrements the counter in a `finally` block. It computes likelihoods from the selected hop's processing-latency observation but never updates beliefs locally.

## Flow-generator contract

The Phase 4 flow generator is a separate FastAPI service. `POST /run-slot` accepts a slot ID and a nonempty set of complete routes supplied by the controller. Every route contains the configured contiguous stages in order, with an explicit replica identity and HTTP endpoint for each hop.

The generator starts all logical flows concurrently, while each flow awaits its own hops sequentially. A route may contain any positive number of contiguous stages starting at stage 1, and every route in a slot must use the same stage sequence. It calls only selected endpoints, supplies each selected replica's final assigned load, validates response correlation/identity/load, and returns modeled processing latency, measured processing latency, request latency, concurrency, state estimate, and likelihood. A downstream failure or mismatch fails the slot rather than presenting partial telemetry as complete.

For local validation, the replica and flow-generator processes share one non-root container image and run on a private Docker Compose network. This exercises real service-to-service HTTP without introducing Kubernetes concerns before Phase 5.

## Kubernetes integration contract

The `ibg-testbed` namespace contains three headless Services and three five-replica StatefulSets for the supported Phase 6 target, plus a ClusterIP flow-generator Service, one flow-generator Deployment, and a one-shot controller Job. The StatefulSet ordinal is converted to the one-based solver replica ID. A shared ConfigMap supplies deterministic solver and runtime profiles, so the controller and HTTP replica agree on state, capacity, delay, cost, congestion penalty, processing delays, and observation seeds.

The controller uses its mounted ServiceAccount token and CA with the existing HTTP client to list only namespace-scoped replica Pods. Discovery accepts only Running, Ready Pods and requires the exact ordinal set expected for every stage. Narrow RBAC permits `get` and `list` on Pods but does not permit Secret reads or Pod creation. Pod DNS through each headless Service becomes the selected hop endpoint; node and Pod identities are retained as placement metadata.

Simulation keeps its existing stage-by-stage observation path. For Kubernetes, the runner's optional slot-traffic port defers physical execution until all configured stages have been placed. The flow generator then runs all complete routes, and its correlated hop telemetry is converted into the existing `Observation` contract before the unchanged learning and equilibrium logic runs.

The flow generator calculates each selected replica's final assignment load from complete routes and sends it as `assigned_load`. Replica services condition their delay and likelihood on that load while reporting actual admitted concurrency separately. Seeded model samples are derived from replica seed plus slot, flow, and assigned load; they do not consume the controller's NumPy stream.

## Validation contract

Phase 6 compares three controlled seeds at three stages, five replicas per stage, and three flows. `scripts/phase6_compare.py` reruns the simulation backend with the same profiles, solver seed, flow order, final-load observation semantics, and request observation seeds, then compares it with controller Job logs.

Placements, sampled utility grids, processing-latency observations and likelihoods, beliefs, aggregate/per-flow and realized utility, SLA, Jain fairness, and equilibrium must match within numerical tolerance. Kubernetes-only Pod, node, endpoint, admitted concurrency, and measured latency metadata must be complete. Runtime is measured but is not required to match because the Kubernetes result includes API, DNS, HTTP, and telemetry overhead.

The base Kustomization deploys long-running resources only. The controller Job is applied after all StatefulSet and Deployment rollouts complete so discovery and traffic cannot race with endpoint replacement.

## Experiment operation and trace

`scripts/run_experiment.py` is the one-command entry point for an observable Kubernetes experiment. It creates the `ibg` kind cluster when absent, builds and loads the shared runtime image, applies the long-running resources, waits for every rollout, creates a fresh experiment controller Job, and follows that Job until completion. Rebuilding the image also restarts and waits for the long-running workloads before controller traffic begins.

The launcher accepts positive flow, stage, and per-stage replica counts through `--flow`, `--stage`, and `--replica`. It selects the requested portion of the validated profile set and deterministically extends profiles for new stage/replica identities, retaining unique observation seeds. It generates the profile ConfigMap plus one headless Service and StatefulSet per requested stage, scales each StatefulSet to the requested replica count, and removes stage resources left over from a previous larger run. The controller receives the same dimensions through environment variables. The verified three-flow/three-stage/five-replica configuration remains the default and the formal Phase 6 validation target; accepting another configuration does not claim that size has passed the Phase 6 parity gate.

Experiment mode seeds Python and NumPy once, constructs one replica set, and carries that same evolving belief state across successive slots. Each slot still delegates placement, traffic, observations, learning, metrics, and equilibrium detection to `run_decoupled_slot`; the outer experiment loop stops when the existing belief-difference rule reports equilibrium or fails at a configured maximum iteration count. The standard Phase 6 manifest retains its one-slot-per-seed validation behavior when `MAX_ITERATIONS` is not set.

The controller emits newline-delimited `IBG_EVENT` records for run start, each completed iteration, and run completion. Events include initial/final replica snapshots, per-stage flow order and placements, selected observations, utility/SLA/fairness/timing metrics, beliefs before and after the slot, and maximum belief change. Slot durations use a monotonic clock so WSL wall-clock corrections cannot distort elapsed time. The launcher renders those events as concise live text and stores the complete JSONL trace under the ignored local `runs/` directory.

When `--csv 1` is selected, the launcher converts the completed host-side JSONL trace into the five legacy reports: `time.csv`, `sla_violations.csv`, `aggregate_utility.csv`, `jain_index.csv`, and `replica_results.csv`. It writes them under the repository-local ignored `figures/` directory; no Kubernetes volume or controller-side filesystem persistence is involved. Metric reports retain one column per experiment, and belief snapshots include the initial state followed by every completed iteration.

## Migration boundary

Keep the solver and belief mathematics as pure Python. Add replaceable adapters for replica discovery, placement publication, HTTP traffic/telemetry, and result storage. This keeps the simulation logic testable without a cluster and lets testbed integration be verified separately.

The adapter boundary uses discovery, traffic execution, observation collection, link/transport-latency collection, and result storage ports. An optional complete-slot traffic port supports Kubernetes routes. Simulation and Kubernetes observations both carry positive processing latency, assigned load, an optional categorical state estimate, and four load-aware likelihoods. The learning core applies those likelihoods through the existing posterior/aggregation functions. Kubernetes transport overhead is collected as non-negative request-minus-processing latency and is not claimed to be a direct consecutive-Pod link measurement.

The Phase 1 `IBG/` path is now the behavioral reference: latency is the sampled/observed $q$, utility is linear in latency, and state-based SLA is retired from active orchestration. The old tasting functions and `legacy_*` wire aliases remain only for budgeted/reference compatibility. Expansion proceeds through the gated phases in `ROADMAP.md`; cluster-specific code must not be embedded into the solver or replica mathematics.

## Implemented Phase 1 latency model

Each replica has a hidden true performance state $\theta\in\{1,2,3,4\}$ ordered from state 1 (bad) to state 4 (good). Controlled validation assigns states deterministically; exploratory simulation may draw them from a seeded declared prior. The state is configuration known only to the experiment/runtime source, never an observation exposed to flows or the controller, and remains fixed for a controlled run. Kernel versus DPDK/VPP is known experimental context rather than a latent state.

For final assigned load $n$, a selected replica produces processing latency

$$
Q_\theta(n)=\mu_\theta+h_\theta(n,\kappa_\theta)+\epsilon_\theta.
$$

$\mu_\theta$ is state-dependent baseline latency, $\kappa_\theta$ is effective capacity measured in concurrent-flow units, and $\epsilon_\theta$ is Gaussian state-dependent jitter truncated only as needed to keep total latency positive. The initial congestion function is

$$
h_\theta(n,\kappa_\theta)=a_\theta\max(0,n-1)+b_\theta\max(0,n-\kappa_\theta)^2.
$$

$a_\theta$ models ordinary sharing cost and $b_\theta$ creates a sharper post-capacity knee. Profiles must satisfy the intended ordering: bad states have no lower baseline/jitter/congestion penalty and no higher effective capacity than good states. FastAPI applies this delay so the hidden state causally affects actual service behavior.

The continuous private observation is the selected hop's processing latency itself: $s=q$. The learning boundary computes $\ell_\theta=f(q\mid\theta,n,m)$ for every state, where $m$ is the known datapath mode, and passes the four likelihoods through the existing posterior/aggregation structure. A categorical signal may report $\arg\max_\theta\ell_\theta$, but it does not drive the update. Unselected replicas produce no raw latency observation. Assigned final load, actual admitted concurrency, modeled delay, measured server processing latency, client request latency, and link/transport latency remain separate correlated fields.

The planned stage utility is linear in latency:

$$
u_k(q)=R_k-\alpha_k q-c_k,\qquad \alpha_k>0.
$$

Expected stage utility integrates this kernel under the belief-weighted, load-conditioned latency law. Because congestion is already part of $q$, the former additional $(1+\gamma n)$ factor is removed. The realized end-to-end utility is

$$
U_i=\sum_{k=1}^{K}U_{i,k}-\alpha_{\mathrm{link}}\sum_{k=1}^{K-1}L_{\mathrm{link},k}.
$$

Processing and link latency therefore use explicit compatible weights instead of subtracting unscaled milliseconds from an inverse benefit. Per-flow SLA violations compare observed end-to-end latency with a configured latency threshold rather than treating state IDs 1 or 2 as automatic violations.

Variable replica-pair link costs depend on consecutive stage choices and therefore couple stages. The decoupled exact solver may optimize a link term only if it is constant or decomposes into independent per-stage terms. Otherwise Phase 1 records/deducts link latency in realized reporting while coupled placement remains deferred pending its separate scope.

Deterministic unit tests inject latency samples, and replay validation feeds the same captured samples to simulation and Kubernetes controller paths for exact mathematical comparison. Live Kubernetes timing is subject to scheduler and network variation, so its gate is distributional: state ordering, congestion response, likelihood calibration, and selected-only observations must hold; live elapsed values are not required to match an in-process clock sample exactly.

## Planned Phase 2 calibration contract

Phase 1 implements the formulas with provisional test parameters; Phase 2 selects experimental values reproducibly. For each state, define the first negative expected-utility load

$$
n_\theta^*=\min\left\{n\ge1:\mathbb{E}\left[R_k-\alpha_kQ_\theta(n)-c_k\right]<0\right\}.
$$

Calibration declares a load horizon $N_{\mathrm{cal}}$ and target bands satisfying $n_1^*<n_2^*<n_3^*<n_4^*$. State 1 must cross zero early; state 4 must remain positive until a declared high-congestion range. The implied stage-latency zero-utility threshold is $(R_k-c_k)/\alpha_k$, which makes the relationship between latency curves and utility feasibility directly auditable.

Latency parameters $(\mu_\theta,a_\theta,b_\theta,\kappa_\theta,\sigma_\theta)$ are calibrated from state semantics and measured service behavior before reward/cost parameters are selected. Utility parameters $(R_k,\alpha_k,c_k)$ express policy valuation, while $\alpha_{\mathrm{link}}$ and SLA threshold $\tau_i$ retain explicit compatible units. A reproducible grid or constrained search generates expected curves, seeded Monte Carlo bands, zero crossings, SLA probabilities, and sensitivity results; live cluster runs validate representative points rather than serving as undocumented trial-and-error.

The calibration horizon may exceed three flows because utility kernels can be evaluated directly without invoking the exact game. This does not expand the supported equilibrium-validation size. The supported operating range must retain at least one non-negative replica option per stage unless an explicit admission-rejection extension is later approved.

Negative utility currently indicates an unattractive or infeasible assignment but does not reject a flow: the exact decoupled policy enforces one replica per stage. Adding skip/reject changes the action/admission model and must not be smuggled in as a parameter choice. Phase 2 must record the chosen interpretation and defer rejection behavior unless separately authorized and tested.

## Planned Kernel and DPDK/VPP expansion boundary

The current HTTP route is the named `kernel` baseline: the flow generator reaches only controller-selected FastAPI endpoints through ordinary Linux TCP/IP and Kubernetes networking. The planned comparison path is `dpdk-vpp`: a VPP user-space forwarding component using an approved DPDK I/O backend between selected route peers while preserving the same FastAPI `/process` endpoint, route identity, controller placement, and learning contract. VPP can operate with non-DPDK interfaces and can integrate with the Linux control plane, but neither is a separate comparison mode in this roadmap.

Datapath selection belongs behind traffic and telemetry adapters. Every mode must retain slot, flow, stage, replica, endpoint, Pod, and node correlation, and must fail a slot rather than report a partial completion. After Phase 1, FastAPI remains the source of exactly one selected-hop processing-latency observation and its four-state likelihood vector. Kernel and DPDK/VPP counters, transport latency, or queue measurements remain separately identified, and unselected replicas must not be queried or treated as observations.

The future `dpdk-vpp` mode is intentionally not implemented or claimed. It starts only after host preflight establishes safe NIC, IOMMU/VFIO, hugepage, CPU/NUMA, privilege, and Kubernetes device-resource handling. Coupled IBG is a separate future mathematical scope and must not be introduced through these datapath adapters.
