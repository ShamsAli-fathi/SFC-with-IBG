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

Each Kubernetes replica Pod separates the private processor from the public route forwarder. The processor listens only on Pod-local port 8081 and exposes `GET /health`, `GET /warmup`, and `POST /process`. `POST /process` accepts positive slot/flow IDs and final `assigned_load`, samples state-conditioned modeled processing delay, performs the work, and returns modeled/measured processing latency, admitted concurrency, a categorical state estimate, and the four-state load-aware likelihood vector. The public forwarder listens on port 8080, owns `POST /process-route`, calls its co-located processor, and forwards an already-selected route to the next public forwarder. Thus forwarding I/O cannot share the processor's Uvicorn event loop or inflate its selected processing signal. Transitional `legacy_*` aliases remain in the wire response for trace compatibility but do not define the active belief model.

Replica identity, hidden state, capacity, baseline delay, congestion parameters, and jitter seed are deterministic environment configuration. The service increments a shared request counter before modeled work, applies the sampled state/load-conditioned delay, and decrements the counter in a `finally` block. It computes likelihoods from the selected hop's processing-latency observation but never updates beliefs locally.

## Flow-generator contract

The Phase 4 flow generator is a separate FastAPI service. `POST /run-slot` accepts a slot ID and a nonempty set of complete routes supplied by the controller. Every route contains the configured contiguous stages in order, with an explicit replica identity and HTTP endpoint for each hop.

The generator starts all logical flows concurrently, while each flow awaits its own hops sequentially. A route may contain any positive number of contiguous stages starting at stage 1, and every route in a slot must use the same stage sequence. It calls only the selected stage-1 public forwarder endpoint; the preselected route is then executed between public forwarders. It validates response correlation/identity/load and returns the processor-produced modeled processing latency, measured processing latency, concurrency, state estimate, and likelihood. A downstream failure or mismatch fails the slot rather than presenting partial telemetry as complete.

For local validation, the replica and flow-generator processes share one non-root container image and run on a private Docker Compose network. This exercises real service-to-service HTTP without introducing Kubernetes concerns before Phase 5.

## Kubernetes integration contract

The `ibg-testbed` namespace contains three headless Services and three five-replica StatefulSets for the supported Phase 6 target, plus a ClusterIP flow-generator Service, one flow-generator Deployment, and a one-shot controller Job. The StatefulSet ordinal is converted to the one-based solver replica ID. A shared ConfigMap supplies deterministic solver and runtime profiles, so the controller and HTTP replica agree on hidden state, stage cost, identity, and observation seed. The active processing-latency parameters come from the calibrated state table in `IBG/latency_model.py`; older capacity/delay/gamma fields remain compatibility metadata and are not active latency inputs.

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

Experiment mode seeds Python and NumPy once, constructs one replica set, and carries that same evolving belief state across successive slots. Each slot still delegates placement, traffic, observations, learning, metrics, and equilibrium detection to `run_decoupled_slot`; the outer experiment loop stops when every belief entry changes by strictly less than `0.033` from the preceding slot, or fails at a configured maximum iteration count. The standard Phase 6 manifest retains its one-slot-per-seed validation behavior when `MAX_ITERATIONS` is not set. `scripts/run_experiment.py` defaults to one independent controller Job; `--runs N` starts N fresh Jobs with the same requested configuration and seed while reusing the already-deployed workload, producing separate traces (and, when enabled, separate CSV columns) for every run.

The controller emits newline-delimited `IBG_EVENT` records for run start, each completed iteration, and run completion. Events include the explicit datapath mode, runtime image and environment versions, initial/final replica snapshots, per-stage flow order and placements, selected observations, utility/SLA/fairness/timing metrics, beliefs before and after the slot, and maximum belief change. Slot durations use a monotonic clock so WSL wall-clock corrections cannot distort elapsed time. The launcher renders those events as concise live text and stores the complete JSONL trace under the ignored local `runs/` directory.

When `--csv 1` is selected, the launcher converts the completed host-side JSONL trace into the five legacy reports—`time.csv`, `sla_violations.csv`, `aggregate_utility.csv`, `jain_index.csv`, and `replica_results.csv`—plus `realized_end_to_end_utility.csv`. The added report exports the existing `realized_utility_total` trace metric: summed actual processing utility across all flows and stages minus the trace's recorded link-latency penalty, using the configured link-latency weight. Current traces record only consecutive selected-replica pair costs for that penalty; older traces retain their historical request-overhead meaning and must remain tied to their code version. The added report does not redefine the legacy aggregate series. All reports are written under the repository-local ignored `figures/` directory; no Kubernetes volume or controller-side filesystem persistence is involved. Metric reports retain one column per experiment, identified by a deterministic six-character hexadecimal hash of the timestamp and run configuration; complete provenance remains in the corresponding JSONL trace. Belief snapshots include the initial state followed by every completed iteration.

## Migration boundary

Keep the solver and belief mathematics as pure Python. Add replaceable adapters for replica discovery, placement publication, HTTP traffic/telemetry, and result storage. This keeps the simulation logic testable without a cluster and lets testbed integration be verified separately.

The adapter boundary uses discovery, traffic execution, observation collection, consecutive-link-cost collection, and result storage ports. An optional complete-slot traffic port supports Kubernetes routes. Simulation and Kubernetes observations both carry positive processing latency, assigned load, an optional categorical state estimate, and four load-aware likelihoods. The learning core applies those likelihoods through the existing posterior/aggregation functions. In current Kernel traces, each selected route returns exactly `K-1` pairwise link records, while flow-generator ingress/request overhead remains separately labelled and is not collected as the utility deduction.

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

The implemented stage utility is linear in latency:

$$
u_k(q)=R_k-\alpha_k q-c_k,\qquad \alpha_k>0.
$$

Expected stage utility integrates this kernel under the belief-weighted, load-conditioned latency law. Because congestion is already part of $q$, the former additional $(1+\gamma n)$ factor is removed. The realized end-to-end utility is

$$
U_i=\sum_{k=1}^{K}U_{i,k}-\alpha_{\mathrm{link}}\sum_{k=1}^{K-1}L_{\mathrm{link},k}.
$$

Processing and link latency therefore use explicit compatible weights instead of subtracting unscaled milliseconds from an inverse benefit. Per-flow SLA violations compare observed end-to-end latency with a configured latency threshold rather than treating state IDs 1 or 2 as automatic violations.

Variable replica-pair link costs depend on consecutive stage choices and therefore couple stages. The decoupled exact solver may optimize a link term only if it is constant or decomposes into independent per-stage terms. Otherwise Phase 1 records/deducts link latency in realized reporting while coupled placement remains deferred pending its separate scope.

The current `kernel` implementation provides a post-placement measurement for the paper's consecutive selected-replica cost without coupling placement. The flow generator sends one request to the selected stage-1 public forwarder; each forwarder invokes its co-located private processor and forwards to the next selected public forwarder, continuing for arbitrary configured stage count. For each selected edge, the caller measures the downstream HTTP RPC duration and subtracts the callee-reported complete downstream-route duration: `link_cost_ms=max(0, pair_request_latency_ms-callee_elapsed_ms)`. This is the measured communication/RPC boundary cost for that selected pair, including HTTP serialization and ordinary Kernel networking; it is not claimed as pure one-way physical propagation. Only the `K-1` pairwise costs are summed into post-placement end-to-end latency and utility. The generator-to-stage-1 ingress measurement is separately labelled telemetry and is not deducted. Processor readiness runs a discarded warm-up sample through the same seeded latency path before it is marked ready; it creates no controller observation and does not advance the deterministic experiment stream. None of these measurements enter the utility grid, solver, route choice, observation, or belief update, so the exact decoupled IBG behavior remains unchanged. The Phase 4 boundary now requires current route and flow responses to carry pair/ingress fields, correlates every pair with source/target replica and Pod plus the normalized target endpoint, proves that each flow's pair-cost sum equals `link_latency_ms_per_flow`, and rejects historical/pairwise schema mixing across iterations. Historical all-old traces retain their former semantics and remain replayable.

Deterministic unit tests inject latency samples, and replay validation feeds the same captured samples to simulation and Kubernetes controller paths for exact mathematical comparison. Live Kubernetes timing is subject to scheduler and network variation, so its gate is distributional: state ordering, congestion response, likelihood calibration, and selected-only observations must hold; live elapsed values are not required to match an in-process clock sample exactly.

## Implemented Phase 2 calibration contract

Phase 2 accepts a synthetic design calibration for the FastAPI test doubles. It is reproducible through `scripts/phase2_calibrate.py` and is not an empirical NIC, Kernel-path, DPDK, VPP, or line-rate capacity claim. For each state, the first negative expected-utility load remains

$$
n_\theta^*=\min\left\{n\ge1:\mathbb{E}\left[R_k-\alpha_kQ_\theta(n)-c_k\right]<0\right\}.
$$

The accepted load horizon is $N_{\mathrm{cal}}=12$ concurrent flows. Inclusive crossing bands are state 1: 3--4, state 2: 4--6, state 3: 6--8, and state 4: 10--12. The accepted state table is:

| State | $\mu$ ms | $a$ ms | $b$ ms | $\kappa$ flows | $\sigma$ ms | $n_\theta^*$ |
|---:|---:|---:|---:|---:|---:|---:|
| 1 (bad) | 40 | 8 | 12 | 1 | 4 | 3 |
| 2 | 28 | 6 | 8 | 2 | 3 | 5 |
| 3 | 18 | 4 | 5 | 3 | 2 | 7 |
| 4 (good) | 10 | 2 | 2 | 5 | 1 | 11 |

The accepted policy values are $R_k=100$ utility units per selected stage, $c_k=1$ utility unit, $\alpha_k=1$ utility unit/ms, $\alpha_{\mathrm{link}}=1$ utility unit/ms, and end-to-end SLA threshold $\tau=175$ ms. The user-directed Phase 4 recalibration selected this threshold from six exploratory 12-flow Kernel traces: it lies near their 75th-percentile end-to-end latency (177.62 ms), yielding a meaningful but non-saturating violation signal. Thus the stage-latency zero-utility threshold is 99 ms. Expected low-load utilities for states 1 through 4 are 59, 71, 81, and 89; at the supported exact load of three flows they are -5, 51, 73, and 85. The game still assigns every flow, but a feasible state-4 option remains available in the supported profile set.

The full seeded run uses 5,000 samples per state/load with seed 2050. It achieved 94.42% minimum categorical state accuracy over all loads 1--12, while the complete likelihood vector—not the category—continues to drive belief updates. Scaling all latency parameters or $\alpha_k$ by $\pm10\%$, and changing reward by $\pm5\%$, preserved ordered crossings inside the accepted bands. A three-stage, load-3, zero-transport illustrative SLA sweep produced violation probabilities 1.0, 0.0, 0.0, and 0.0 for homogeneous states 1 through 4; it is a model check, not a prediction for mixed live routes.

Live localhost Uvicorn checks exercised each state at baseline and one post-capacity load, five repetitions per point. All 40 accepted observations preserved assigned-load correlation, positive modeled/measured latency, measured processing latency as the signal, and recomputed likelihood equality. The maximum accepted server sleep/scheduling overshoot was 6.78 ms under a declared tolerance of $\max(10\text{ ms}, 0.1Q_{\mathrm{modeled}})$; minimum per-point categorical accuracy was 80%, reflecting occasional first-request scheduling noise. This remains the localhost conformance result; the separate Kubernetes Kernel-mode result is recorded below.

The calibration horizon exceeds three flows only through direct utility evaluation and does not expand the supported equilibrium-validation size. `deploy/kubernetes/profiles.json` fixes all active stage costs at 1 and maps replicas to states; the calibrated state table supplies active latency parameters. Legacy profile capacity, delay, gamma, base-delay, and congestion-delay fields remain for trace/schema compatibility and must not be interpreted as the accepted latency law.

Negative utility currently indicates an unattractive or infeasible assignment but does not reject a flow: the exact decoupled policy enforces one replica per stage. Adding skip/reject changes the action/admission model and must not be smuggled in as a parameter choice. Phase 2 must record the chosen interpretation and defer rejection behavior unless separately authorized and tested.

## Deferred utility-horizon extension

Before a future experiment or heuristic study uses accepted utility values for per-replica loads above 12, extend the synthetic calibration to $N_{\mathrm{cal}}=50$. This is direct latency/utility evaluation only: it must preserve the active $Q_\theta(n)$ law and $u(q)=R-\alpha q-c$, must not alter `BR_EIBG`, add heuristics, change placement, or claim 50-flow exact-solver scalability.

The user-requested target crossing bands are state 1: 3--6, state 2: 12--20, state 3: 25--35, and state 4: 45--50. The extension must select/fix suitable state parameters, generate utility curves for loads 1--50, rerun seeded Monte Carlo and sensitivity checks, update deterministic tests and all handoffs, and state explicitly that the horizon is per-replica assigned load rather than total logical flows. It is a deferred calibration requirement, not part of the completed Phase 3 Kernel-baseline work.

## Implemented Phase 3 Kernel baseline

`kernel` is now an explicit runtime mode at the adapter, controller, flow-generator request/response, slot-result, validation-summary, and JSONL-event boundaries. The flow generator rejects unimplemented runtime modes and verifies that the requested mode matches its configured mode. Historical Phase 3 traces carry non-negative per-hop `transport_overhead_ms=max(0, request_latency_ms-processing_latency_ms)` fields. Current traces retain compatible hop fields but add explicit `links` and separate generator-ingress fields; only `links[*].link_cost_ms` supplies the runner's link-latency deduction. The private processor retains the `/process` request/response contract; the public forwarder alone exposes `/process-route` for an already-selected route. Solver inputs, processing-latency observation, likelihood, learning, placement, utility kernel, and hard 175 ms SLA behavior are unchanged. Simulation is labelled `simulation` for comparison but is not a deployable datapath mode.

`scripts/phase3_kernel_baseline.py` validates a completed supported-size JSONL trace. It requires one selected observation and one correlated Kernel hop for every placement, exact equality between each selected processing-latency signal and its hop telemetry, preserved likelihood vectors, all four-state ordering at load 1, non-decreasing observed congestion groups, at least 80% categorical accuracy, and equilibrium. It validates historical request-overhead traces under their original schema. For current traces it additionally requires exactly `K-1` consecutive, route-correlated pair records per flow; verifies each cost formula, source/target Pod identity, normalized target endpoint, and equality between the pair sum and the deducted per-flow link metric; checks separately labelled non-negative ingress telemetry; and rejects schema mixing within one run. The Kubernetes live scheduling gate is statistical: at least 95% of selected hops must have measured-minus-modeled server processing overshoot no larger than $\max(10\text{ ms},0.1Q_{\mathrm{modeled}})$. Communication and ingress timings are reported distributionally without an unsupported deterministic upper gate.

The accepted seed-2050 supported-size run used image `ibg-testbed:kernel-phase3`, Docker 29.6.1, kind 0.32.0, and Kubernetes 1.36.1. It reached equilibrium in nine iterations and produced 81 complete selected hops over assigned loads 1--3. Mean/p50/p95/max processing latency was 16.33/13.13/36.59/52.60 ms; server overshoot was 2.07/0.97/7.52/10.54 ms with a 98.77% tolerance pass rate; and transport overhead was 6.85/6.43/11.31/17.87 ms. Load-1 mean processing latency remained ordered at 49.06, 39.27, 21.31, and 12.52 ms for states 1 through 4, observed state-3/state-4 congestion groups were non-decreasing, and categorical accuracy was 83.95%. A preliminary cold single-slot run observed a 60.30 ms transport outlier, which is why no unsupported deterministic transport ceiling is claimed.

The same validator replays every captured selected signal, likelihood, and per-flow transport value through the unchanged simulation runner with Kubernetes-style deferred complete-route observations. All nine replayed slots matched their Kernel trace exactly: 81 placements and observations matched, and maximum drift across utility grids, likelihoods, beliefs, aggregate/per-flow and realized utility, processing/link/end-to-end latency, SLA, fairness, and equilibrium was zero.

## Planned Kernel and DPDK/VPP expansion boundary

The current HTTP route is the named `kernel` baseline: the flow generator reaches the controller-selected first public forwarder, whose co-located private processor produces the selected processing signal; public forwarders relay the remaining already-selected route using `/process-route` over ordinary Linux TCP/IP and Kubernetes networking. The planned comparison path is `dpdk-vpp`: a VPP user-space forwarding component using an approved DPDK I/O backend between selected route peers while preserving FastAPI application processing, route identity, controller placement, and the learning contract. VPP can operate with non-DPDK interfaces and can integrate with the Linux control plane, but neither is a separate comparison mode in this roadmap.

Datapath selection belongs behind traffic and telemetry adapters. Every mode must retain slot, flow, stage, replica, endpoint, Pod, and node correlation, and must fail a slot rather than report a partial completion. After Phase 1, FastAPI remains the source of exactly one selected-hop processing-latency observation and its four-state likelihood vector. Kernel and DPDK/VPP counters, transport latency, or queue measurements remain separately identified, and unselected replicas must not be queried or treated as observations.

The future `dpdk-vpp` mode is intentionally not implemented or claimed. It starts only after host preflight establishes safe NIC, IOMMU/VFIO, hugepage, CPU/NUMA, privilege, and Kubernetes device-resource handling. Coupled IBG is a separate future mathematical scope and must not be introduced through these datapath adapters.
