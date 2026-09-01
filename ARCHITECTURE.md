# IBG Testbed Architecture

## Current system

`IBG/` is a working pure-Python simulation. Its active migrated path is the small-scale, decoupled per-stage IBG: `IBG/main.py` constructs experiments, `IBG/runner.py` orchestrates one import-safe decoupled slot through adapter contracts, `IBG/claude.py` computes per-stage utility grids and the exact memoized `BR_EIBG` continuation policy, and `IBG/header.py` contains the replica, learning, embedding, and metric logic. Simulation adapters provide stage-scoped discovery, embedding, reference observations, and CSV storage. Kubernetes adapters provide readiness-filtered discovery and complete-route traffic/telemetry while reusing the same solver, embedding, learning, equilibrium, and metric functions. The separate budgeted/coupled code is retained as reference material but is not part of the current migration.

## IBG Exact solver contract

For each decoupled stage, the solver builds a belief-driven utility grid using 30 Monte Carlo processing-latency samples per replica and load. Each sample draws a possible hidden state from the current belief and then draws from that state's load-conditioned positive latency law. `BR_EIBG` solves the sequential one-replica-per-stage game exactly with respect to the resulting sampled grid.

Each subgame is identified by the next player and the full vector of loads already assigned to the stage's replica slots. The solver branches over every active replica, recursively solves the continuation game, evaluates the current player's choice at its predicted final load, and selects the best continuation-consistent action. Subgames are memoized by load vector, and exact ties select the lowest replica ID for deterministic behavior. The former `backward_d_memoized_simple` name remains only as a compatibility wrapper around `br_eibg_exact`.

This one-of-M generalization is intentionally limited to small instances. With `N` flows and `M` active replicas, the number of cached load vectors through the terminal depth is `C(N+M, M)`. The supported three-flow/five-replica case has 56 states. Scaling beyond this exact testbed would require a different approximate algorithm and is outside the current implemented roadmap.

## Target testbed

```text
Development host
  -> native Docker Engine
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

Development tools, source code, Docker Engine, and cluster state live in the local development environment. Docker Desktop is not part of the testbed.

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

Each Kubernetes replica Pod separates the private processor from the public route forwarder. The processor listens only on Pod-local port 8081 and exposes `GET /health`, `GET /warmup`, and `POST /process`. It remains one Uvicorn worker. `POST /process` accepts positive slot/flow IDs and final `assigned_load`, samples state-conditioned physical processing delay, performs the work, independently samples observation-only jitter, and returns modeled/measured processing latency, observation jitter, noisy learning signal, admitted concurrency, a categorical state estimate, and the four-state load-aware likelihood vector. The public forwarder listens on port 8080, owns `POST /process-route`, calls its co-located processor, and forwards an already-selected route to the next public forwarder. Phase 4.1 runs two Uvicorn workers only for this public-forwarder application so concurrent route RPCs do not all depend on one application worker. Its downstream HTTPX client and public Uvicorn server use the matched 30-second idle keep-alive window; its separate local-processor HTTPX client keeps the processor-compatible default idle window. This is a connection-lifetime setting only, not an IBG or metric change. Thus forwarding I/O cannot share the processor's Uvicorn event loop or inflate physical processing latency, and adding forwarder workers does not replicate or change the processor's stateful sampling path. Transitional `legacy_*` aliases remain in the wire response for trace compatibility but do not define the active belief model.

Replica identity, hidden state, capacity, baseline delay, congestion parameters, and jitter seed are deterministic environment configuration. The service increments a shared request counter before modeled work, applies the sampled state/load-conditioned physical delay, and decrements the counter in a `finally` block. It computes likelihoods from the selected hop's noisy learning signal using the convolved physical/observation density but never updates beliefs locally.

## Flow-generator contract

The Phase 4 flow generator is a separate FastAPI service. `POST /run-slot` accepts a slot ID and a nonempty set of complete routes supplied by the controller. Every route contains the configured contiguous stages in order, with an explicit replica identity and HTTP endpoint for each hop.

The generator starts all logical flows concurrently, while each flow awaits its own hops sequentially. A route may contain any positive number of contiguous stages starting at stage 1, and every route in a slot must use the same stage sequence. It calls only the selected stage-1 public forwarder endpoint; the preselected route is then executed between public forwarders. It validates response correlation/identity/load and returns the processor-produced modeled processing latency, measured processing latency, concurrency, state estimate, and likelihood. A downstream failure or mismatch fails the slot rather than presenting partial telemetry as complete.

For local validation, the replica and flow-generator processes share one non-root container image and run on a private Docker Compose network. This exercises real service-to-service HTTP without introducing Kubernetes concerns before Phase 5.

## Kubernetes integration contract

The `ibg-testbed` namespace contains three headless Services and three five-replica StatefulSets for the supported Phase 6 target, plus a ClusterIP flow-generator Service, one flow-generator Deployment, and a one-shot controller Job. The StatefulSet ordinal is converted to the one-based solver replica ID. A shared ConfigMap supplies deterministic solver and runtime profiles, so the controller and HTTP replica agree on hidden state, stage cost, identity, and observation seed. The active processing-latency parameters come from the calibrated state table in `IBG/latency_model.py`; older capacity/delay/gamma fields remain compatibility metadata and are not active latency inputs.

The controller uses its mounted ServiceAccount token and CA with the existing HTTP client to list only namespace-scoped replica Pods. Discovery accepts only Running, Ready Pods and requires the exact ordinal set expected for every stage. Narrow RBAC permits `get` and `list` on Pods but does not permit Secret reads or Pod creation. The controller reaches the flow-generator Service through an absolute namespace FQDN with a trailing DNS root label; selected Pod DNS through each headless Service is likewise absolute. This avoids resolver search-list ambiguity while retaining node and Pod identities as placement metadata.

Simulation keeps its existing stage-by-stage observation path. For Kubernetes, the runner's optional slot-traffic port defers physical execution until all configured stages have been placed. The flow generator then runs all complete routes, and its correlated hop telemetry is converted into the existing `Observation` contract before the unchanged learning and equilibrium logic runs.

The flow generator calculates each selected replica's final assignment load from complete routes and sends it as `assigned_load`. Replica services condition their delay and likelihood on that load while reporting actual admitted concurrency separately. Seeded model samples are derived from replica seed plus slot, flow, and assigned load; they do not consume the controller's NumPy stream.

## Validation contract

Phase 6 compares three controlled seeds at three stages, five replicas per stage, and three flows. `scripts/phase6_compare.py` reruns the simulation backend with the same profiles, solver seed, flow order, final-load observation semantics, and request observation seeds, then compares it with controller Job logs.

Placements, sampled utility grids, selected noisy observations and likelihoods, beliefs, aggregate/per-flow and realized utility, SLA, Jain fairness, and equilibrium must match within numerical tolerance. Kubernetes-only Pod, node, endpoint, admitted concurrency, physical processing, observation-jitter, and transport metadata must be complete. Runtime is measured but is not required to match because the Kubernetes result includes API, DNS, HTTP, and telemetry overhead.

The base Kustomization deploys long-running resources only. The controller Job is applied after all StatefulSet and Deployment rollouts complete so discovery and traffic cannot race with endpoint replacement.

## Experiment operation and trace

`scripts/run_experiment.py` is the one-command entry point for an observable Kubernetes experiment. It creates the `ibg` kind cluster when absent, builds and loads the shared runtime image, applies the long-running resources, waits for every rollout, creates a fresh experiment controller Job, and follows that Job until completion. Rebuilding the image also restarts and waits for the long-running workloads before controller traffic begins.

The launcher accepts positive flow, stage, and per-stage replica counts through `--flow`, `--stage`, and `--replica`. It selects the requested portion of the validated profile set and deterministically extends profiles for new stage/replica identities, retaining unique observation seeds. It generates the profile ConfigMap plus one headless Service and StatefulSet per requested stage, scales each StatefulSet to the requested replica count, and removes stage resources left over from a previous larger run. The controller receives the same dimensions through environment variables. The verified three-flow/three-stage/five-replica configuration remains the default and the formal Phase 6 validation target; accepting another configuration does not claim that size has passed the Phase 6 parity gate.

Experiment mode seeds Python and NumPy once, constructs one replica set, and carries that same evolving belief state across successive slots. Each slot still delegates placement, traffic, observations, learning, metrics, and equilibrium detection to `run_decoupled_slot`; the outer experiment loop stops when every belief entry changes by strictly less than `0.033` from the preceding slot, or fails at a configured maximum iteration count. The standard Phase 6 manifest retains its one-slot-per-seed validation behavior when `MAX_ITERATIONS` is not set. `scripts/run_experiment.py` defaults to one independent controller Job; `--runs N` starts N fresh Jobs with the same requested configuration and seed while reusing the already-deployed workload, producing separate traces (and, when enabled, separate CSV columns) for every run.

The controller emits newline-delimited `IBG_EVENT` records for run start, each completed iteration, and run completion. Events include the explicit datapath mode, runtime image and environment versions, initial/final replica snapshots, per-stage flow order and placements, selected observations, utility/SLA/fairness/timing metrics, beliefs before and after the slot, and maximum belief change. Slot durations use a monotonic clock so host wall-clock corrections cannot distort elapsed time. The launcher renders those events as concise live text and stores the complete JSONL trace under the repository-local versionable `runs/` directory.

`netem_v1` is an opt-in Kernel transport-robustness boundary. `--netem 1 --netem-delay-ms D --netem-jitter-ms J` adds a root `tc/netem` qdisc to each replica Pod's `eth0` through a short-lived init container with only `NET_ADMIN`; ordinary runs have no init container or qdisc. The configured scope, interface, normal distribution, delay, and jitter are copied into every trace event. The qdisc affects replica-Pod egress traffic and response timing, while localhost private-processor work and the processor-generated selected learning signal retain their existing laws. Therefore this mode tests whether the unchanged game still converges and favors Good/Excellent hidden states while its transport is impaired; it does not reinterpret network jitter as an observation or alter utility, SLA, raw pair cost, placement, or belief mathematics. Replacing the StatefulSet Pod removes the qdisc, so disabling the option restores the default deployment without host mutation. Packet loss is not part of `netem_v1`.

When `--csv 1` is selected, the launcher converts the completed host-side JSONL trace into the five legacy reports—`time.csv`, `sla_violations.csv`, `aggregate_utility.csv`, `jain_index.csv`, and `replica_results.csv`—plus current-schema `realized_utility.csv`, `physical_processing_utility.csv`, `realized_end_to_end_utility.csv`, and, when every completed slot records `learning_signal_v1`, `logical_learning_footprint.csv`. `realized_utility.csv` is the selected outcome mode: currently `physical-only-v1`, summed observed selected processing utility. The physical and raw physical-plus-pair views are exported separately for reference; pair costs and raw end-to-end latency are never discarded. Historical traces retain their historical `realized_end_to_end_utility.csv` meaning rather than receiving fabricated new metrics. The logical-footprint report exports each slot's `learning_signal.logical_payload_bytes`; it is the canonical selected-only learning-information size model, not actual HTTP or wire bytes. The added reports do not redefine the legacy aggregate series. All reports are written under the repository-local ignored `figures/` directory; no Kubernetes volume or controller-side filesystem persistence is involved. Metric reports retain one column per experiment, identified by a deterministic six-character hexadecimal hash of the timestamp and run configuration; complete provenance remains in the corresponding JSONL trace. Belief snapshots include the initial state followed by every completed iteration.

`Chart/` is a user-directed legacy plotting area rather than a source of experiment data or metric definitions. Compatibility work may inspect and change only explicitly requested Python plot scripts, one report at a time. Each authorized `Chart/<plot>/` folder is self-contained: its script defaults to its primary current CSV and any optional baseline CSVs beside that script, never to the shared generated `figures/` directory. Such scripts must consume the current host-side CSV/JSONL contracts without reinterpreting legacy metrics, and must label trace/schema scope when it affects a plotted claim. Preserve each original script's visual design/theme and embedded text unless the user explicitly requests a change. Once a plot is authorized, iterative visual changes such as axis ranges, titles, labels, and styling stay local and are recorded here only when the user explicitly marks them final. The finalized Jain-fairness plot discovers exactly one headered `*_IBG.csv` input in `Chart/jain/` (or accepts `--input` to disambiguate) and renders its per-iteration IBG-Exact mean headlessly. The finalized `Chart/sla-small/2/sla-small.py` plot similarly discovers its one `*_IBG.csv`, applies the original five-slot moving average over the first 50 timeslots, and is explicitly scoped to the small-scale experiment. The finalized `Chart/util-small/util-small.py` discovers its local `realized_end_to_end_utility_IBG.csv`, smooths its IBG-Exact mean and standard-deviation band with a trailing five-timeslot average, uses integer timeslots and a 2,500--3,500 y-axis, and writes its image beside the script. Optional legacy baselines remain modular and are skipped when absent.

## Migration boundary

Keep the solver and belief mathematics as pure Python. Add replaceable adapters for replica discovery, placement publication, HTTP traffic/telemetry, and result storage. This keeps the simulation logic testable without a cluster and lets testbed integration be verified separately.

The adapter boundary uses discovery, traffic execution, observation collection, consecutive-link-cost collection, and result storage ports. An optional complete-slot traffic port supports Kubernetes routes. Simulation and Kubernetes observations both carry positive processing latency, assigned load, an optional categorical state estimate, and four load-aware likelihoods. The learning core applies those likelihoods through the existing posterior/aggregation functions. In current Kernel traces, each selected route returns exactly `K-1` pairwise link records, while flow-generator ingress/request overhead remains separately labelled and is not collected as the utility deduction.

The Phase 1 `IBG/` path is now the behavioral reference: latency is the sampled/observed $q$, utility is linear in latency, and state-based SLA is retired from active orchestration. The old tasting functions and `legacy_*` wire aliases remain only for budgeted/reference compatibility. Expansion proceeds through the gated phases in `ROADMAP.md`; cluster-specific code must not be embedded into the solver or replica mathematics.

## Implemented Phase 1 latency model

Each replica has a hidden true performance state $\theta\in\{1,2,3,4\}$ ordered from state 1 (bad) to state 4 (good). Controlled validation assigns states deterministically; exploratory simulation may draw them from a seeded declared prior. The state is configuration known only to the experiment/runtime source, never an observation exposed to flows or the controller, and remains fixed for a controlled run. Kernel versus DPDK/VPP is known experimental context rather than a latent state.

For final assigned load $n$, a selected replica produces processing latency

$$
Q_\theta(n)=\mu_\theta+h_\theta(n,\kappa_\theta)+J_\theta,
\qquad J_\theta=|Z_\theta|,\quad Z_\theta\sim\mathcal N(0,\sigma_\theta^2).
$$

$\mu_\theta$ is state-dependent baseline latency, $\kappa_\theta$ is effective capacity measured in concurrent-flow units, and $J_\theta$ is a nonnegative additive half-normal processing-delay disturbance. Jitter therefore never reduces the deterministic state/load latency. The congestion function is

$$
h_\theta(n,\kappa_\theta)=a_\theta\max(0,n-1)+b_\theta\max(0,n-\kappa_\theta)^2.
$$

$a_\theta$ models ordinary sharing cost and $b_\theta$ creates a sharper post-capacity knee. Profiles must satisfy the intended ordering: bad states have no lower baseline/jitter/congestion penalty and no higher effective capacity than good states. The active physical half-normal scales for states 1 through 4 are 6, 5.25, 4, and 3.25 ms. FastAPI applies this physical delay so the hidden state causally affects actual service behavior. Physical sampling and expected-latency calculations use this `half-normal-additive-v1` law.

The selected-only continuous learning signal is deliberately noisier than physical processing latency:

$$
S_\theta(n)=Q_\theta(n)+E_\theta,
\qquad E_\theta=|W_\theta|,\quad
W_\theta\sim\mathcal N(0,\omega_\theta^2),
$$

where $E_\theta$ is independent observation-only noise with active state-1-through-state-4 scales $\omega_\theta=7.2,6.3,4.8,3.9$ ms. This `half-normal-observation-v1` term never enters actual processing latency, the active physical-only SLA/outcome metric, or either recorded utility reference. The learning boundary computes $\ell_\theta=f_S(s\mid\theta,n,m)$ from the exact convolution of the physical and observation half-normal densities and passes all four likelihoods through the existing posterior/aggregation structure. A categorical estimate may report $\arg\max_\theta\ell_\theta$, but it does not drive the update. Unselected replicas produce no observation. Assigned final load, modeled and measured physical processing latency, observation jitter, noisy learning signal, admitted concurrency, client latency, and link/transport latency remain separate correlated fields.

The implemented stage utility is linear in latency:

$$
u_k(q)=R_k-\alpha_k q-c_k,\qquad \alpha_k>0.
$$

Expected stage utility integrates this kernel under the belief-weighted, load-conditioned latency law. Because congestion is already part of $q$, the former additional $(1+\gamma n)$ factor is removed. The retained raw physical-plus-pair reference utility is

$$
U_i=\sum_{k=1}^{K}U_{i,k}-\alpha_{\mathrm{link}}\sum_{k=1}^{K-1}L_{\mathrm{link},k}.
$$

Processing and link latency use explicit compatible weights instead of subtracting unscaled milliseconds from an inverse benefit. The active, reversible outcome policy is `physical-only-v1`: realized utility and per-flow SLA compare the observed selected processing total against the 110-ms threshold. `physical-plus-pair-v1` restores the raw physical-plus-pair utility and end-to-end SLA comparison. Both bases remain in every current trace; state IDs never determine violations.

Variable replica-pair link costs depend on consecutive stage choices and therefore couple stages. The decoupled exact solver may optimize a link term only if it is constant or decomposes into independent per-stage terms. Otherwise Phase 1 records/deducts link latency in realized reporting while coupled placement remains deferred pending its separate scope.

The current `kernel` implementation provides a post-placement measurement for the paper's consecutive selected-replica cost without coupling placement. The flow generator sends one request to the selected stage-1 public forwarder; each forwarder invokes its co-located private processor and forwards to the next selected public forwarder, continuing for arbitrary configured stage count. For each selected edge, the caller measures the downstream HTTP RPC duration and subtracts the callee-reported complete downstream-route duration: `link_cost_ms=max(0, pair_request_latency_ms-callee_elapsed_ms)`. This is the measured communication/RPC boundary cost for that selected pair, including HTTP serialization and ordinary Kernel networking; it is not claimed as pure one-way physical propagation. The `K-1` costs are always summed into recorded raw end-to-end latency and the physical-plus-pair reference utility. The active physical-only outcome deliberately does not deduct them while the unresolved runtime residual is isolated; switching `physical-plus-pair-v1` restores historical outcome behavior without changing measurement or selection. The generator-to-stage-1 ingress measurement is separately labelled telemetry and is not deducted. Processor readiness runs a discarded warm-up sample through the same seeded latency path before it is marked ready; it creates no controller observation and does not advance the deterministic experiment stream. None of these measurements enter the utility grid, solver, route choice, observation, or belief update, so the exact decoupled IBG behavior remains unchanged. The Phase 4 boundary now requires current route and flow responses to carry pair/ingress fields, correlates every pair with source/target replica and Pod plus the normalized target endpoint, proves that each flow's pair-cost sum equals `link_latency_ms_per_flow`, and rejects historical/pairwise schema mixing across iterations. Historical all-old traces retain their former semantics and remain replayable.

Deterministic unit tests inject latency samples, and replay validation feeds the same captured samples to simulation and Kubernetes controller paths for exact mathematical comparison. Live Kubernetes timing is subject to scheduler and network variation, so its gate is distributional: state ordering, congestion response, likelihood calibration, and selected-only observations must hold; live elapsed values are not required to match an in-process clock sample exactly.

## Implemented Phase 2 calibration contract

Phase 2 accepts a synthetic design calibration for the FastAPI test doubles. It is reproducible through `scripts/phase2_calibrate.py` and is not an empirical NIC, Kernel-path, DPDK, VPP, or line-rate capacity claim. For each state, the first negative expected-utility load remains

$$
n_\theta^*=\min\left\{n\ge1:\mathbb{E}\left[R_k-\alpha_kQ_\theta(n)-c_k\right]<0\right\}.
$$

The accepted load horizon is $N_{\mathrm{cal}}=12$ concurrent flows. Inclusive crossing bands are state 1: 3--4, state 2: 4--6, state 3: 6--8, and state 4: 10--12. The accepted state table is:

| State | $\mu$ ms | $a$ ms | $b$ ms | $\kappa$ flows | $\sigma$ ms | $n_\theta^*$ |
|---:|---:|---:|---:|---:|---:|---:|
| 1 (bad) | 40 | 8 | 12 | 1 | 6 | 3 |
| 2 | 28 | 6 | 8 | 2 | 5.25 | 5 |
| 3 | 18 | 4 | 5 | 3 | 4 | 7 |
| 4 (good) | 10 | 2 | 2 | 5 | 3.25 | 11 |

The accepted policy values are $R_k=100$ utility units per selected stage, $c_k=1$ utility unit, $\alpha_k=1$ utility unit/ms, and $\alpha_{\mathrm{link}}=1$ utility unit/ms. The active, user-authorized outcome threshold is $\tau=90$ ms under `physical-only-v1`; the former 110-ms physical-plus-pair calibration is historical and remains version-bound to its traces. Thus the stage-latency zero-utility threshold is 99 ms. Under the active physical law, expected low-load utilities for states 1 through 4 are approximately 54.21, 66.81, 77.81, and 86.41; at the supported exact load of three flows they are approximately -9.79, 46.81, 69.81, and 82.41. The game still assigns every flow, but a feasible state-4 option remains available in the supported profile set.

The full seeded run uses 5,000 samples per state/load with seed 2050. With the separate observation law, minimum categorical accuracy is 81.38% and mean load-1 accuracy is 87.74%; the gate requires at least 80% minimum accuracy and at most 90% mean load-1 accuracy so the design is both usable and deliberately imperfect. The complete likelihood vector—not the category—continues to drive belief updates. Scaling all physical latency parameters or $\alpha_k$ by $\pm10\%$, and changing reward by $\pm5\%$, preserved ordered crossings inside the accepted bands. The unchanged physical-latency SLA sweep for homogeneous three-stage, load-3, zero-transport routes produced violation probabilities 1.0, 1.0, 0.0002, and 0.0 for states 1 through 4; observation-only noise is excluded from this calculation. These are model checks, not predictions for mixed live routes.

The earlier localhost Uvicorn conformance result predates the separated learning signal and remains version-bounded historical evidence. Current live validation additionally requires nonnegative observation jitter, exact equality $s=q_{\mathrm{measured}}+e$, and likelihood equality under the convolved density while retaining the physical scheduler-overshoot check. After a successful normal image build/deploy, fresh current-image supported trace `runs/ibg-experiment-20260721T145856Z.jsonl` reached equilibrium in 16 slots and passed the Kernel gate (86.11% classification and 97.22% server-overshoot compliance) plus exact 16-slot replay with zero drift. The supported trace was launched with `--skip-build` only after that normal build/deploy had succeeded.

The calibration horizon exceeds three flows only through direct utility evaluation and does not expand the supported equilibrium-validation size. `deploy/kubernetes/profiles.json` fixes all active stage costs at 1 and maps replicas to states; the calibrated state table supplies active latency parameters. Legacy profile capacity, delay, gamma, base-delay, and congestion-delay fields remain for trace/schema compatibility and must not be interpreted as the accepted latency law.

Negative utility currently indicates an unattractive or infeasible assignment but does not reject a flow: the exact decoupled policy enforces one replica per stage. Adding skip/reject changes the action/admission model and must not be smuggled in as a parameter choice. Phase 2 must record the chosen interpretation and defer rejection behavior unless separately authorized and tested.

## Deferred utility-horizon extension

Before a future experiment or heuristic study uses accepted utility values for per-replica loads above 12, extend the synthetic calibration to $N_{\mathrm{cal}}=50$. This is direct latency/utility evaluation only: it must preserve the active $Q_\theta(n)$ law and $u(q)=R-\alpha q-c$, must not alter `BR_EIBG`, add heuristics, change placement, or claim 50-flow exact-solver scalability.

The user-requested target crossing bands are state 1: 3--6, state 2: 12--20, state 3: 25--35, and state 4: 45--50. The extension must select/fix suitable state parameters, generate utility curves for loads 1--50, rerun seeded Monte Carlo and sensitivity checks, update deterministic tests and all handoffs, and state explicitly that the horizon is per-replica assigned load rather than total logical flows. It is a deferred calibration requirement, not part of the completed Phase 3 Kernel-baseline work.

## Implemented Phase 3 Kernel baseline

`kernel` is now an explicit runtime mode at the adapter, controller, flow-generator request/response, slot-result, validation-summary, and JSONL-event boundaries. The flow generator rejects unimplemented runtime modes and verifies that the requested mode matches its configured mode. Historical Phase 3 traces carry non-negative per-hop `transport_overhead_ms=max(0, request_latency_ms-processing_latency_ms)` fields. Current traces retain compatible hop fields but add explicit observation jitter, noisy learning signal, `links`, separate generator-ingress fields, and the explicit outcome mode; physical processing supplies the active outcome utility/SLA, while physical plus `links[*].link_cost_ms` remains the raw end-to-end reference. The private processor retains the `/process` request/response contract; the public forwarder alone exposes `/process-route` for an already-selected route. Simulation is labelled `simulation` for comparison but is not a deployable datapath mode.

`scripts/phase3_kernel_baseline.py` validates a completed supported-size JSONL trace. It requires one selected observation and one correlated Kernel hop for every placement, exact correlation of physical processing, observation jitter, noisy signal, and likelihood vectors, all four-state ordering at load 1, non-decreasing observed congestion groups, at least 80% categorical accuracy, and equilibrium. It validates historical request-overhead traces under their original schema. For current traces it additionally requires exactly `K-1` consecutive, route-correlated pair records per flow; verifies each cost formula, source/target Pod identity, normalized target endpoint, and equality between the pair sum and the deducted per-flow link metric; checks separately labelled non-negative ingress telemetry; and rejects schema mixing within one run. The Kubernetes live scheduling gate is statistical: at least 95% of selected hops must have measured-minus-modeled server processing overshoot no larger than $\max(10\text{ ms},0.1Q_{\mathrm{modeled}})$. Communication and ingress timings are reported distributionally without an unsupported deterministic upper gate.

The accepted seed-2050 supported-size run used image `ibg-testbed:kernel-phase3`, Docker 29.6.1, kind 0.32.0, and Kubernetes 1.36.1. It reached equilibrium in nine iterations and produced 81 complete selected hops over assigned loads 1--3. Mean/p50/p95/max processing latency was 16.33/13.13/36.59/52.60 ms; server overshoot was 2.07/0.97/7.52/10.54 ms with a 98.77% tolerance pass rate; and transport overhead was 6.85/6.43/11.31/17.87 ms. Load-1 mean processing latency remained ordered at 49.06, 39.27, 21.31, and 12.52 ms for states 1 through 4, observed state-3/state-4 congestion groups were non-decreasing, and categorical accuracy was 83.95%. A preliminary cold single-slot run observed a 60.30 ms transport outlier, which is why no unsupported deterministic transport ceiling is claimed.

The same validator replays every captured selected signal, likelihood, and per-flow transport value through the unchanged simulation runner with Kubernetes-style deferred complete-route observations. All nine replayed slots matched their Kernel trace exactly: 81 placements and observations matched, and maximum drift across utility grids, likelihoods, beliefs, aggregate/per-flow and realized utility, processing/link/end-to-end latency, SLA, fairness, and equilibrium was zero.

## Implemented Phase 4 control-plane measurement contract

The future Kernel--DPDK/VPP comparison needs a datapath-neutral controller metric, but it must not confuse selected-route execution with control-plane work. A versioned `control_plane_v1` block is therefore emitted once per completed Kubernetes slot. It records monotonic-wall and controller-CPU timing for discovery; admission/planning from slot start through route-plan dispatch; feedback processing from returned telemetry through validation, observation conversion, belief update, metrics, and equilibrium; and their sum as active control time. Time spent awaiting the dispatched selected route is recorded separately as `data_plane_wait_ms` and is never presented as control-plane decision time.

The same block counts controller-boundary HTTP application-payload bytes and messages, partitioned into Kubernetes discovery, controller-to-flow-generator route command, flow-generator-to-controller selected telemetry, and reserved zero-valued belief-exchange fields. Forwarder-to-forwarder RPCs on the selected route remain data-plane traffic and are excluded. Counts use application-body bytes rather than unsupported TCP/IP or protocol-header wire-byte claims. The contract preserves the current selected-only noisy learning signal and does not change route selection, solver inputs, pair-cost deduction, learning, SLA, or equilibrium behavior.

A separate versioned `learning_signal_v1` block measures the logical selected-only learning-information footprint without reclassifying the larger telemetry response. It canonically projects each selected observation to UTF-8 JSON containing only stage, flow, selected replica, assigned load, noisy selected learning signal, and the four-state likelihood vector. Physical processing latency and observation-jitter diagnostics are excluded alongside route endpoints, Pod/node metadata, transport, pair costs, ingress data, categorical state estimates, and legacy aliases. A completed slot must contain exactly `flows * stages` records; the number of available but unselected replicas cannot increase it. The block reports record count, canonical logical-payload bytes, and mean bytes per selected hop.

`learning_signal_v1` is a reproducible size model for the information contract used by selected-only learning. It is not the actual flow-generator HTTP response size, a TCP/IP wire-byte measurement, or evidence that the current reporting envelope transmits only this projection. The actual aggregate response remains measured independently as `control_plane_v1.payload_bytes.selected_telemetry_rx`. No raw-telemetry counterfactual or byte-saving ratio is inferred.

The opt-in `solver_resource_v1` measurement is enabled only by `--memory 1`. A per-slot controller meter reads current RSS from `/proc/self/statm` immediately before admission, samples it every 5 ms while the slot is active, explicitly samples around each exact-policy cache disposal, and reads it after feedback. The trace records baseline, active-slot peak, post-feedback RSS, and peak incremental working-memory bytes. Each exact stage also records the memo-table size immediately before the existing clear and the residual size immediately afterward; overall cache values are the maxima across sequential stages. `scripts/solver_resource_summary.py` validates completed memory-enabled traces and reports RSS in bytes/MiB while keeping memo counts in entries. This schema is deliberately separate from `control_plane_v1` payload bytes and timing metrics; default runs emit no resource block, old traces cannot be backfilled, and the measurement changes no solver recurrence, placement, learning, route, SLA, utility, pair-cost behavior, or runtime resource allocation. It establishes the identical future contract required for Exact and a separately authorized heuristic solver.

## Current exploratory 15x8 runtime investigation

Observation-only jitter is excluded from every latency input. The earlier exploratory 15-flow/8-replica traces used a 110-ms physical-plus-pair SLA: physical processing averaged 67.01 and 70.74 ms/flow in the final slot, while selected pair costs averaged 50.95 and 60.36 ms/flow, producing 10/15 and 13/15 historical violations. No final flow exceeded 110 ms before pair cost. The active 110-ms physical-only outcome is a separately versioned reporting basis, adopted because that raw pair residual remains unresolved rather than because the residual was fixed or dismissed.

The prolonged controller symptom has a concrete exact-solver cache-lifetime cause and is repaired. A 15x8 stage evaluates 490,314 exact load-vector subgames. Recursive `lru_cache` creates a wrapper/function self-cycle, so merely dropping a completed policy left that entire memo table alive until cyclic garbage collection. The policy now uses an exact-equivalent packed load-state key and clears its memo table in a `finally` block immediately after `embedding` completes. The recurrence, candidate actions, sampled utility grid, ordered placement, and lowest-replica-ID tie rule are unchanged. A normal-build 15x8 trace, `runs/ibg-experiment-20260721T144252Z.jsonl`, completed 19 slots without OOM and replayed with zero drift; median elapsed/admission/controller-CPU times were 10.41/10.06/9.91 s, respectively, versus the previous roughly 15 s slots. The controller cgroup remained at about 207 MiB with zero OOM events during the run.

The pair metric is deliberately a selected RPC-boundary residual, `max(0, caller HTTP elapsed - callee route-handler elapsed)`. It includes ordinary public-forwarder queueing/scheduling and HTTP/Kubernetes work outside the callee handler, not only a stable network-link delay. The newly added selected-forwarder cgroup before/after measurements disconfirmed the prior throttling hypothesis: the separated-mode diagnostic run recorded zero throttling deltas across 299 selected-forwarder samples, and the physical-only A/B had just one 6.104 ms event that did not coincide with a high pair cost. The cgroup probes themselves add route-wait work, so a clean no-probe run was also retained. Do not change forwarder CPU resources on the basis of cumulative lifetime counters.

The opt-in forwarding-path diagnostic further decomposes a selected pair residual without redefining it. Historical `forwarding_path_v1` records the source request start, target public-forwarder handler start/finish, and source response receipt on the current shared Unix-epoch clock. Historical `forwarding_path_v2` retains those aggregates and adds target ASGI ingress/dispatch, target-to-private-processor request/ingress/handler/work/response, optional remaining-route round trip, handler completion, and the source local-response-to-outbound-request gap. Active `forwarding_path_v3` adds source HTTP Core milestones through `http_client_path_v2`: pool wait, optional TCP connect, request-header/body send, response-read start and header wait, response-body/close, and application resume. The processor work interval still surrounds the existing modeled `asyncio.sleep`; it observes but does not redefine `processing_latency_ms`. These are same-clock Kernel diagnosis aids, not wire, one-way, or portable cross-host latency measurements. `link_cost_ms` remains caller duration minus callee route-handler duration; none of these fields affect placement, learning, utility, SLA, or equilibrium. `scripts/forwarding_path_summary.py` validates historical v1/v2/v3 traces and reports available components globally and per stage pair.

When forwarding-path diagnostics are enabled in the current runtime, a v3 pair additionally carries `forwarder_runtime_v1`: request-correlated source/target public-worker PID, diagnostic active-handler/downstream-request counts, a bounded 5-ms per-worker event-loop scheduling-lag sample window, and best-effort source local-socket metadata. The sampler is active only while diagnostic requests exist and does not time, gate, or alter the route. `pool_wait_ms` retains its historical field name, but is only the source request-to-first-transport milestone interval; because the current HTTPX client has unbounded connection capacity, it must not be interpreted as a proven HTTPX capacity-pool queue. Summary schema v4 exposes these runtime values separately while preserving all historical v1/v2/v3 reports and the raw pair formula.

Normal-build exploratory trace `runs/ibg-experiment-20260721T202043Z.jsonl` supplies the first live `forwarding_path_v2` evidence. Across 450 selected links, source local-response-to-request preparation averaged only 0.10 ms, while source request start to target ASGI ingress averaged 13.48 ms (p95 34.55), target ingress-to-handler dispatch averaged 2.97 ms (p95 9.45), and target-handler finish to source response receipt averaged 5.68 ms (p95 15.07). Those three pair-residual boundaries sum to 22.12 ms per selected link, matching the 44.24-ms mean per-flow two-link deduction. Same-worker and cross-worker link means were nearly identical at 22.06 and 22.18 ms, respectively. Private-processor admission/response boundaries were also variable but remain inside the callee handler and therefore are excluded by the unchanged pair formula. This localizes the reported pair variance to burst-time HTTP/runtime admission and return boundaries rather than modeled processor work, target locality, or CFS throttling, but the source-request-to-target-ingress segment still combines source HTTP-client waiting, Kernel/network transit, and pre-ASGI server admission.

Normal-build current-schema trace `runs/ibg-experiment-20260721T205120Z.jsonl` resolves that combined source boundary. Of 420 selected pair RPCs, 418 opened a new TCP connection. Source HTTP pool wait averaged 2.63 ms (p95 7.80) and TCP connect averaged 7.31 ms (p95 19.14), within a 13.23-ms mean request-to-target-ingress interval. Every measured inter-slot idle gap was 7.74--8.08 seconds, while the then-default HTTPX `keepalive_expiry` and Uvicorn `timeout_keep_alive` were both 5 seconds. Consequently almost every pooled connection expired before the next traffic burst and the concurrent route wave repeatedly paid pool/connect setup. Same- and cross-worker links both reconnected, and all selected-forwarder cgroup throttle deltas remained zero. The controlled runtime-only A/B now sets both public-forwarder idle windows to 30 seconds, above the observed gap, while retaining default HTTPX connection limits and every metric/IBG behavior.

The normal-build 30-second keep-alive A/B trace `runs/ibg-experiment-20260721T210935Z.jsonl` confirms the connection-lifetime mechanism but not a complete pair-variance correction. Across the same 14 slots and 420 links, new TCP connections fell from 418 to 243 (42.14% reuse), and mean source-request-to-target-ingress fell from 13.23 to 11.38 ms. The all-slot pair-cost mean changed only from 43.22 to 42.19 ms per flow and its upper tail remained variable, so keep-alive reuse alone is insufficient to declare stable forwarding behavior. Final pair/end-to-end means were 28.26/97.08 ms with 0/15 SLA violations and realized utility 2998.76, but those final values are exploratory runtime outcomes, not a replacement metric or a formal 15x8 gate. Every selected-forwarder cgroup delta remained zero, all replica containers stayed Ready with zero restarts, and exact replay had zero drift.

The independent pair-residual/SLA symptom was subsequently localized with no-controller fixed-route probes to concurrent HTTP/1.1 scheduling/queueing across single-worker public forwarders. Phase 4.1 applies a runtime-only correction: each public-forwarder container runs two Uvicorn workers, while its private processor remains single-worker and unchanged. The forwarder request remains 25m CPU, its measured two-worker CPU limit is 1 CPU, and its memory request/limit is 128/256 MiB. The 1-CPU limit is evidence-based: the initial two-worker/500m probe produced correlated quota stalls, while the repeated same-/cross-worker probe at 1 CPU recorded zero throttle deltas. The one-worker forwarder peaked at 52.4 MiB; two-worker validation peaked at about 141 MiB with zero memory events or restarts, leaving headroom under 256 MiB.

In the post-correction fixed-route probe, five-wave means were 6.57/5.75 ms for six simultaneous same-/cross-worker requests and 7.73/8.01 ms for fifteen, compared with the diagnosed one-worker six-request waves of 9.46/21.07/24.50 ms and 23--38 ms first-wave fifteen-request costs. Clean exploratory trace `runs/ibg-experiment-20260721T191634Z.jsonl` reduced all-slot pair cost from 45.78 to 36.81 ms per flow and p95 from 80.09 to 63.22 ms relative to diagnostic trace `runs/ibg-experiment-20260721T180604Z.jsonl`; source-to-target-handler mean/p95 fell from 18.18/40.11 to 13.65/31.72 ms. It ended at 0/15 SLA violations with 67.71/27.58/95.29 ms final physical/pair/end-to-end means and realized utility 3025.72, and exact replay had zero drift. This is favorable exploratory evidence, not a formal 15x8 gate or a guarantee that every run beats the earlier healthy snapshot; the unchanged raw pair metric still records real runtime variation.

`scripts/control_plane_summary.py` validates complete traces and reports per-run median and p95 admission, feedback, active-control, controller CPU, payload-byte, message-count, separately labelled data-plane-wait values, actual selected-telemetry response bytes, and—when present—the separate logical learning-signal record and byte metrics. Future comparisons must hold seed, dimensions, profiles, controller image, and measurement schema fixed. `data_plane_wait_ms` may differ by datapath mode but remains a separately reported execution outcome.

## Planned Kernel and DPDK/VPP expansion boundary

The current HTTP route is the named `kernel` baseline: the flow generator reaches the controller-selected first public forwarder, whose co-located private processor produces physical processing latency and the separate noisy selected learning signal; public forwarders relay the remaining already-selected route using `/process-route` over ordinary Linux TCP/IP and Kubernetes networking. The planned comparison path is `dpdk-vpp`: a VPP user-space forwarding component using an approved DPDK I/O backend between selected route peers while preserving FastAPI application processing, route identity, controller placement, and the learning contract. VPP can operate with non-DPDK interfaces and can integrate with the Linux control plane, but neither is a separate comparison mode in this roadmap.

Datapath selection belongs behind traffic and telemetry adapters. Every mode must retain slot, flow, stage, replica, endpoint, Pod, and node correlation, and must fail a slot rather than report a partial completion. FastAPI remains the source of exactly one selected-hop noisy learning signal and its four-state likelihood vector, with physical processing and observation jitter retained as separate diagnostics. Kernel and DPDK/VPP counters, transport latency, or queue measurements remain separately identified, and unselected replicas must not be queried or treated as observations.

Phase 5 now exposes `dpdk-vpp` as a known launcher target while keeping the runtime allow-list Kernel-only. `./scripts/run_experiment.py --datapath dpdk-vpp --dpdk-preflight-only` and the standalone `scripts/dpdk_vpp_preflight.py` perform the same versioned, read-only `dpdk_vpp_preflight_v1` gate before any Docker, kind, or Kubernetes action. The gate reports architecture/CPU visibility, VPP and DPDK tooling, configured hugepages, IOMMU groups, `/dev/vfio/vfio`, and a PCI dataplane interface distinct from the visible default-route interface. If default-route ownership is not visible, it conservatively refuses to label a PCI NIC safe. The report explicitly records that it performed no host changes.

The 2026-07-27 host is blocked: it is a four-vCPU VMware guest with only one visible VMXNET3 PCI NIC, no safe non-management dataplane NIC, zero hugepages, no IOMMU groups or VFIO device, and no VPP/DPDK executables. Therefore `--datapath dpdk-vpp` fails before cluster mutation and no DPDK/VPP image, Pod, adapter, traffic, counter, or performance claim exists. Kernel remains independently runnable through the unchanged default. Phase 6 can begin only on a host that passes the gate and has an approved resource-ownership/rollback design; unsafe no-IOMMU VFIO or detaching the only management NIC is outside scope. Coupled IBG remains a separate mathematical scope.

The user has deferred all DPDK/VPP work until further notice. Treat this entire expansion boundary and its dormant preflight as inactive reference material: do not invoke, extend, test, or revise it unless the user explicitly reopens DPDK/VPP. The active implementation remains Kernel-only.

## Temporarily frozen IBG-Exact baseline

The current decoupled IBG-Exact implementation is the temporarily frozen reference baseline for a future IBG-Hybrid chapter. The explicitly authorized `netem_v1` test wrapper does not unfreeze or modify its mathematics. Its exact recurrence, packed-state memoization and immediate cache disposal, selected-only learning, physical/observation latency laws, physical-only outcome contract, 110-ms SLA, raw pair/end-to-end references, and Kernel telemetry schemas must remain reproducible and unchanged. IBG-Hybrid has not been designed or implemented; its solver approximation, information boundary, metrics, and validation plan require explicit user-defined scope before any code or runtime work begins.

## Active IBG-Hybrid architecture extension

The preceding freeze statement records the earlier project state and is
superseded only with respect to whether Hybrid scope is authorized. The
IBG-Exact implementation remains frozen. The user has now authorized
IBG-Hybrid as the active coupled/budgeted evolution of that system.

IBG-Hybrid is not a second testbed architecture. It should reuse the current
IBG-Exact replica model, latency and learning laws, selected-only observation
boundary, slot traffic, metrics, trace provenance, and Kernel Kubernetes
runtime wherever their semantics are unchanged. The principal change is the
decision engine: instead of solving each stage independently, Hybrid chooses a
complete SFC route jointly and approximates strategic continuation play with
candidate pruning, limited lookahead, and optional Monte Carlo rollouts.

The current files under `IBG_Hybrid/` are an old standalone prototype. They
are reference material for the intended pruning/lookahead direction, not the
target contract, and may be substantially revised where they disagree with
the paper or the current IBG-Exact implementation.

The initial Hybrid configuration is 20 sequential flows, 3 ordered stages,
and 10 available replicas per stage. Each flow must select exactly one
replica from every stage, producing one complete three-replica route. General
budgeted-IBG notation permits subsets up to a budget `L`, but the
paper-specific SFC action is strict: `L = K` and every stage is represented.

Hybrid directly reuses these Exact contracts unless later Hybrid evidence
explicitly authorizes a versioned change:

- Four hidden performance states and belief vectors.
- Linear latency utility and the calibrated state/load latency model.
- Nonnegative `half-normal-additive-v1` physical scales 6/5.25/4/3.25 ms.
- Independent nonnegative `half-normal-observation-v1` learning scales
  7.2/6.3/4.8/3.9 ms.
- The exact convolution likelihood for the two half-normal laws.
- Selected-only learning, belief retention 0.8, and strict equilibrium
  `<0.033`.
- `physical-only-v1` as the active realized-utility and 110-ms SLA basis,
  while physical, pair, raw end-to-end, and physical-plus-pair reference
  values remain recorded.
- Discovery, complete-route traffic, observation, link-cost, result-sink,
  control-plane, learning-footprint, and resource-measurement adapters.

One public `IBGHybridPolicy` composes pruning, limited lookahead, and Monte
Carlo; the paper may discuss them separately, but this project treats them as
internal stages of one algorithm. A Hybrid action is a complete ordered route.
The coupled state contains all pre-decision replica loads and known
availability, host, node-capacity, budget, and consecutive-link metadata.
Hidden true replica states must never be used by pruning, route scoring,
lookahead, or Monte Carlo.

The Hybrid slot lifecycle is:

1. Discover the complete Ready replica set for every stage.
2. Choose one randomized flow order for the slot.
3. Sequentially select and commit one complete feasible route per flow.
4. Execute the committed routes concurrently after placement, while each flow
   traverses its stages sequentially.
5. Collect exactly one observation from each selected hop and none from
   unselected replicas.
6. Apply the shared learning update and compute the existing utility, SLA,
   fairness, timing, resource, and equilibrium metrics.
7. Store complete structured trace detail while printing only a compact
   metrics line after the slot.

Unlike the decoupled Exact runner, Hybrid must not reshuffle flows
independently at each stage because the complete route is one coupled action.

The Kernel runtime remains structurally unchanged: each replica Pod retains a
single-worker private processor on port 8081 and a two-worker public forwarder
on port 8080; the current CPU/memory allocations, separate local/downstream
HTTP clients, and 30-second downstream keep-alive configuration remain
unchanged. Hybrid needs a solver/controller selection boundary and coupled
replay support, not a second processor, forwarder, flow generator, or cluster
topology.

Existing forwarding, cgroup, control-plane, learning-footprint, and
solver-resource diagnostics must be audited only after the main lookahead
implementation. Algorithm-neutral schemas should be reused; Exact-specific
replay and memo-cache assumptions require Hybrid extensions. `netem_v1`
integration is postponed until the baseline Hybrid simulation and Kernel
replay gates pass.

Bandit-based adaptation from the paper is not part of the required initial
Hybrid policy. It is a later optional extension: a contextual bandit such as
UCB or Thompson Sampling may become a low-overhead fallback or a rollout
kernel only after the core pruning/lookahead/Monte-Carlo policy and its
selected-only learning boundary are validated.

### IBG-Hybrid budget-action correction

The preceding Hybrid extension initially interpreted the paper through its
SFC-specific `L=K` statement. The user has clarified the intended active model
is instead the paper's general budgeted action: every flow has budget `L=2`
and must select exactly two replicas from two distinct stages out of the three
available stages. The unselected stage is bypassed entirely; it is not
processed through a default replica.

Thus a Hybrid action is a two-hop partial chain such as
`((stage 1, replica r1), (stage 3, replica r3))`, not a three-stage complete
route. The two selected stages and their replicas are chosen jointly under
beliefs, load, link cost, feasibility, pruning, lookahead, and Monte Carlo.
The old prototype's two-stage action direction is therefore relevant, though
its implementation remains non-authoritative for the other reasons recorded
above.

The code-level source of truth is `IBG_Hybrid/budgeted.py`:
`HYBRID_STAGE_BUDGET = 2`. The current planner rejects a different supplied
value because its policy and embedding structures are explicitly two-stage.
Changing `L` later is a deliberate code change requiring corresponding action,
embedding, route-execution, and test updates.

This differs from the current Exact traffic contract, whose flow generator
requires a contiguous stage sequence beginning at stage 1. Hybrid can reuse
the replica processor, public forwarder, latency/learning contracts, and most
infrastructure, but it requires an explicitly versioned traffic-route
extension that can execute and correlate two selected stages even when they
are noncontiguous or do not begin at stage 1. It must not mislabel a skipped
stage as an observation or a completed hop.

## IBG-Hybrid Phase 1 package boundary

The import-safe Hybrid boundary now lives under the `IBG_Hybrid` package.
Importing any Hybrid module does not launch an experiment, print progress,
change the recursion limit, or write CSV/pickle output. `IBG_Hybrid/main.py`
constructs only the default 20-flow/3-stage/10-replica configuration at import
time; its executable path reports that the production policy is deferred.

`IBG_Hybrid/contracts.py` defines the initial pure Hybrid types:

- `ReplicaChoice` identifies one positive `(stage, replica)` pair.
- `TwoStageAction` contains exactly two choices in increasing stage order.
- `HybridConfiguration` fixes the active three-stage shape and validates its
  budget through `IBG_Hybrid/budgeted.py`.
- `GlobalLoadState` is an immutable stage-major load matrix. Applying an
  action increments only its two selected replicas, leaving the bypassed stage
  untouched.
- `FeasibilityResult` separates accepted actions from explicit rejection
  reasons.
- `HybridSolverResult` carries the chosen action, objective value,
  post-action loads, feasibility, and candidate counts.

`HYBRID_STAGE_BUDGET = 2` remains the single budget source in
`IBG_Hybrid/budgeted.py`. The prototype planner and embedding entry points now
reject another budget, and embedding also rejects malformed same-stage or
out-of-range selections.

`IBG_Hybrid/oracle.py` is a deliberately bounded exhaustive oracle for small
tests only. It enumerates canonical two-stage actions, applies caller-injected
objective and feasibility functions over copied global load states, and
retains the first canonical plan on exact ties. Hard flow/action limits reject
the production 20x3x10 problem. The oracle deliberately does not define or
implement the production pruning, lookahead, Monte Carlo, link, utility, or
feasibility semantics.

No latency, learning, outcome, adapter, telemetry, or Kubernetes
implementation was copied into Hybrid during this phase. Those
algorithm-neutral Exact components remain frozen and are to be reused at
their later roadmap boundaries. The old Hybrid utility, learning, reporting,
and prototype policy functions remain non-authoritative compatibility
material.

## Final IBG-Hybrid Phase 0 policy contract

`IBG_Hybrid/phase0_contract.py` is the versioned
`ibg-hybrid-policy-contract-v1` source for the decisions that were still open
after Phase 1. It fixes meanings and deterministic fixtures only; the
production policy remains Phase 2--4 work.

The initial policy parameters are `C=5`, `D=2`, `S=50`, and rollout
`epsilon=0.10`. `C` counts retained replicas per stage, not complete actions.
For the active `K=3`, `L=2` model, the maximum pruned complete-action count is

$$
|\Phi_C|=\binom{K}{L}\min(C,M)^L=\binom{3}{2}5^2=75.
$$

Before pruning, structurally valid replicas are filtered by Ready status and
a declared `max_assigned_flows` limit measured in assigned flows per slot.
This admission limit is known policy metadata, not the hidden performance
state or its state-conditioned latency capacity. Existing Kubernetes Pod
CPU/memory requests are scheduling allocations for already-running Pods and
are not charged again for every flow. A future per-flow CPU/memory/bandwidth
resource model requires a separately versioned demand contract; it is not an
implicit Phase 2 input.

For each stage, feasible replicas are ranked at the current decision state by
belief-driven expected stage utility at projected load `current_load + 1`.
Ties use the lowest replica ID. This resolves the paper's conflict between a
static zero-congestion pruning sentence and its load-aware greedy/fast-path
descriptions in favor of the active load-aware IBG model. Pair cost is not
used in this per-stage ranking. All complete `L=2` combinations over the
retained per-stage sets are then enumerated; the old prototype's additional
top-`X` route cut and local search are not part of the initial contract.

Every feasible complete action must have one configured, nonnegative directed
pair-link cost in milliseconds from its lower-stage selected replica to its
higher-stage selected replica. This is a known planning input and never comes
from hidden true states or the volatile post-placement measured pair residual.
A noncontiguous selection such as stages 1 and 3 has exactly one direct
selected-pair planning cost. The route score is the two belief-driven expected
stage utilities minus that one pair cost with the shared weight of one utility
unit per millisecond.

Lookahead preserves the budgeted game's individual best-response meaning. For
each focal candidate, it commits that candidate exactly once, simulates the
next `min(D, remaining flows)` arrivals with the deterministic joint greedy
base policy over feasible pruned actions, and evaluates only the focal flow's
route utility at the resulting projected loads. Future players' utilities are
not summed, and the focal immediate value is not added a second time. `D`
therefore counts future flows after the focal decision; `D=0` is myopic.

Monte Carlo uses the same focal-value definition. For each focal candidate it
runs `S=50` candidate-specific continuations of up to `D` future flows.
Each future action is the deterministic greedy feasible pruned joint action
with probability `0.90`, or a uniform draw from all feasible pruned joint
actions with probability `0.10`. The candidate value is the mean of the 50
once-evaluated focal utilities. The bandit kernel mentioned elsewhere in the
paper remains optional Phase 10 and is not part of this core contract.

All decisions pass through one public policy with deterministic internal-path
precedence:

1. Monte Carlo when maximum normalized four-state belief entropy in the
   feasible pruned pool is at least `0.75`.
2. Otherwise deterministic lookahead when the flow is high priority or
   contention is at least `0.70`.
3. Otherwise the pruned joint greedy path.

Contention is the maximum, over Ready replicas in the active feasibility
pool, of `current assigned load / declared max assigned flows`, clipped to
`[0,1]`. Entropy is Shannon entropy divided by `log(4)`. The paper supplies
the `0.70` contention example but no entropy number; `0.75` is the explicit
initial project threshold, not an empirical performance claim.

Seed ownership is independent by purpose. A root solver seed and slot ID
derive one `blake2b-hybrid-flow-order-v1` flow-order seed. Each MC sample uses
`blake2b-hybrid-rollout-v1` over root seed, slot ID, decision position, flow
ID, canonical focal action, and sample index. Rollouts use local generators
and cannot consume or perturb flow-order, utility-grid, physical-processing,
or observation-jitter streams. Traces must record the contract version,
parameter set, activation inputs/path/reason, root and derived seed schemes,
flow order, candidate identity, and sample count.

Planning semantics do not change the shared outcome boundary. A bypassed stage
has no processing or observation. The active `physical-only-v1` realized
utility and 110-ms SLA use the two observed selected processing values; the
raw two-hop end-to-end view and `physical-plus-pair-v1` add exactly one
measured selected-pair residual. Configured planning link cost and measured
outcome pair cost remain separately named.

## IBG-Hybrid Phase 2 pure policy boundary

The production-facing Phase 2 decision boundary is
`IBG_Hybrid.policy.IBGHybridPolicy`. It is a pure Python component over the
Phase 1 global load/action types and the authoritative Phase 0 feasibility,
pruning, and complete-action scoring helpers. It does not call the tiny
exhaustive oracle, the old prototype planner, a slot runner, traffic, or
Kubernetes.

The policy input surface contains only:

- The immutable pre-decision `GlobalLoadState`.
- `ReplicaAdmission` metadata with Ready state and the declared
  assigned-flow-per-slot limit.
- Four-state belief vectors keyed by `ReplicaChoice`.
- Configured nonnegative directed planning pair-link costs keyed by the two
  selected choices.

Runtime replica objects, hidden true replica state, legacy replica cost, and
post-placement measured pair residuals are absent from this interface.
`IBG_Hybrid.expected_utility.expected_stage_utility_from_belief` normalizes
each belief and mixes the four state hypotheses by delegating the underlying
state/load utility calculation to the frozen
`IBG.latency_model.expected_state_utility`. Hybrid therefore reuses the Exact
latency/linear-utility implementation without copying or changing it.

For one decision, the policy performs these deterministic steps:

1. Enumerate all canonical structural `L=2` actions for accounting.
2. Apply the Phase 0 replica-local Ready/capacity filter before pruning.
3. Score each locally feasible replica at `current_load + 1`, retain at most
   `C=5` per stage, and break pruning ties by lowest replica ID.
4. Enumerate every canonical two-stage action from the retained per-stage
   pools. At 3 stages and 10 replicas this is bounded by 75 actions.
5. Apply complete Phase 0 feasibility, including the required directed pair
   link, and score every feasible action as its two stage utilities minus the
   configured pair cost.
6. Select the strict highest score; exact joint ties retain the first
   canonical action.

`CandidateAccounting` records available replica counts by stage, locally
feasible counts, all structural actions, complete feasible actions before
pruning, the retained replica identities per stage, pruned action count,
feasible pruned action count, and deterministic rejection-reason counts.
`HybridGreedyDecision` returns that accounting together with all feasible
`ScoredHybridAction` values and the selected `HybridSolverResult`. If no
complete feasible action survives, `NoFeasiblePrunedAction` carries the
completed accounting rather than fabricating a placement.

Phase 2 commits only the selected two replicas in its returned load state; the
third stage remains unchanged. Deterministic `D=2` continuation, seeded Monte
Carlo, slot orchestration, traffic, learning, metrics, replay, Kubernetes,
diagnostics, and netem remain later phases.

## IBG-Hybrid Phase 3 deterministic-lookahead boundary

Deterministic limited lookahead is now an additional method on the same
production-facing `IBGHybridPolicy`; it is not a separate algorithm or policy
object. `select_greedy` remains the unchanged Phase 2 feasibility, pruning,
joint-scoring, tie-breaking, and candidate-accounting boundary. Phase 3 calls
that method once to obtain the canonical feasible focal pool and again at
every branch-local continuation state.

The number of flows already committed is derived from the immutable global
assignment count divided by `L=2`. For each root-feasible focal action,
lookahead creates a new state by committing that action exactly once, then
simulates `min(D, remaining flows after focal)` future arrivals. Each future
arrival recomputes Phase 2 Ready/capacity/link feasibility, belief/load-aware
per-stage pruning, complete-action scoring, and deterministic joint greedy at
the updated branch state. Admission metadata, beliefs, configured planning
links, the pre-decision state, and other candidate branches are never
mutated.

After the continuation, the branch value is only the focal action's two
belief-driven stage utilities at their projected final loads, minus its one
configured directed planning pair-link cost. The focal immediate score is not
added, continuation-player utility is not summed, and the skipped stage
remains absent. Strict improvement over the canonical Phase 2 focal order
retains the first canonical action on an exact lookahead tie.

`HybridLookaheadDecision` records the selected focal result, root Phase 2
candidate accounting, every completed focal evaluation, and any continuation
dead ends. Each evaluation records its focal action, state immediately after
the focal commit, projected final state, requested/effective depth, focal
value, and ordered `HybridLookaheadStep` values. Each step retains its
branch-local pre-decision state and full Phase 2 greedy decision/accounting.
The solver result's `state_after` contains only the selected focal commit;
simulated future placements remain diagnostic projections. A root-feasible
candidate whose continuation cannot place a required future flow is recorded
and excluded; if all branches dead-end, `NoFeasibleLookaheadAction` exposes
their accounting rather than fabricating a placement.

Phase 3 remains pure Python and belief-only. It adds no Monte Carlo,
activation, flow-order generation, slot runner, traffic, learning, metrics,
replay, Kubernetes, diagnostics, netem, or bandit behavior.

## IBG-Hybrid Phase 4 seeded Monte Carlo boundary

Seeded Monte Carlo is now a third internal decision method on the same
production-facing `IBGHybridPolicy`. `select_monte_carlo` does not replace or
alter `select_greedy` or `select_lookahead`. It obtains the canonical
root-feasible focal pool from Phase 2 and evaluates every focal action through
`S=50` independently seeded continuations of the same
`min(D, remaining flows after focal)` horizon, with `D=2`.

Every candidate/sample pair constructs the authoritative `RolloutSeedKey`
from root seed, slot ID, decision position, flow ID, canonical focal action,
and sample index, then derives its local
`blake2b-hybrid-rollout-v1` seed. A private standard-library RNG owned by that
sample makes all epsilon decisions. It does not consume a shared RNG or any
flow-order, utility-grid, physical-processing, or observation-jitter stream.

At every future arrival, the sample calls the unchanged Phase 2 boundary at
its current immutable branch state. With probability `0.90`, it commits that
decision's canonical greedy action. With probability `0.10`, it draws
uniformly by index from that same decision's complete feasible-pruned joint
action tuple. Thus exploration cannot produce an unavailable, over-capacity,
unretained, same-stage, malformed, or missing-link action. The selected
continuation affects only its candidate/sample branch.

After its continuation, a completed sample evaluates only its focal action's
two expected stage utilities at the sample's final projected loads and
subtracts the focal configured directed pair-link cost once. The focal
immediate value and continuation-player welfare remain absent. A candidate's
score is the arithmetic mean of completed sample focal values. A dead-end
sample is recorded and excluded from that mean; a focal candidate is
non-selectable only when every requested sample dead-ends. If every candidate
is rejected, `NoFeasibleMonteCarloAction` exposes the deterministic failure
detail rather than returning a partial placement.

`HybridMonteCarloDecision` records root candidate accounting, seed
provenance, requested sample count, completed and rejected focal candidates,
and the selected focal-only solver result. Each candidate records requested
and effective depth, completed/failed sample counts, and mean focal value.
Each completed sample records its seed key/derived seed, focal state,
projected final state, continuation steps, and focal value. Every step records
its branch-local state, Phase 2 accounting and feasible action tuple,
canonical greedy action, actual chosen action, greedy/exploration mode, and
resulting state. Failed samples retain the same provenance plus their failing
state and Phase 2 accounting.

Phase 4 provides this forceable pure Monte Carlo method only. Automatic
entropy/contention/priority activation, slot flow ordering and orchestration,
traffic, learning, metrics, replay, Kubernetes, diagnostics, netem, and the
optional bandit remain later work.

## IBG-Hybrid Phase 5 pure simulation-slot boundary

Phase 5 adds an import-safe, in-memory orchestration boundary without changing
the completed Phase 0--4 policy. `IBG_Hybrid.runner.run_hybrid_slot` owns slot
lifecycle only; all placement mathematics remains in the existing
`IBGHybridPolicy`. `IBG_Hybrid.slot_contracts` contains immutable flow,
replica, pair, slot-input, placement, observation, metric, and slot-result
records. `IBG_Hybrid.simulation.InProcessHybridSimulationAdapter` is the
replaceable pure execution port for this phase. It performs no HTTP,
container, Kubernetes, or filesystem result work.

One `blake2b-hybrid-flow-order-v1` seed derived from root seed and slot ID
creates one local-RNG permutation of all flows. The runner uses that same
order for every coupled decision. For each current immutable global load
state, it calls Phase 2 greedy once to obtain the feasible pruned pool used by
activation. Entropy is the maximum normalized four-state belief entropy over
replicas participating in feasible pruned complete actions. Contention is the
maximum current-load/declared-capacity ratio over that same active pool.
Phase 0 precedence then selects exactly one existing method: Monte Carlo for
entropy at least `0.75`; otherwise lookahead for contention at least `0.70`
or explicit high priority; otherwise greedy. Only the returned focal action
is committed. A placement record retains activation values/reason, action,
bypassed stage, pre/post real loads, objective, Phase 2 accounting, and the
complete selected greedy/lookahead/Monte-Carlo detail.

Physical execution begins only after all focal actions have been committed.
For every selected `(flow, stage, replica)`, the in-process adapter derives
independent `blake2b-hybrid-physical-v1` and
`blake2b-hybrid-observation-v1` local seeds. It delegates physical sampling,
observation-only half-normal sampling, exact convolved likelihood, and state
estimate to the unchanged `IBG.latency_model`. The selected replica's final
assigned load conditions both physical generation and likelihood. True state
is read only inside this adapter. The adapter returns exactly two selected
observations and one separately named simulated measured-pair outcome per
flow; the runner rejects missing, duplicate, unselected, wrong-load, or
wrong-route results before learning.

Learning is a single post-execution batch. The runner calls the unchanged
`IBG.learning.apply_observations` against frozen Exact `Replica.local_update`
and `Replica.aggregation`, preserving selected-only posterior aggregation,
rounding, and retention `0.8`. No bypassed or unselected replica receives an
observation. The result retains beliefs before and after and supports explicit
next-slot construction from the learned belief snapshot.

Hybrid metrics use only each flow's two selected stages. Belief-driven
expected utility is evaluated at final assigned loads and deducts the
configured planning link. Physical realized utility uses the unchanged Exact
linear utility over observed physical processing only. The unchanged Exact
outcome selector and `SLA_v` enforce the active physical-only `110`-ms SLA.
Exactly one simulated measured-pair latency per flow is added only to the raw
end-to-end latency and physical-plus-pair reference utility. Planning and
measured pair values are never substituted for one another. Jain fairness
and strict `<0.04` equilibrium call the unchanged Exact helpers. Slot timing
is monotonic and covers placement, simulation, learning, and metric
calculation.

`run_hybrid_slot` prints nothing and retains results only in memory.
`run_and_print_hybrid_slot` and the executable module print exactly one
compact metrics line after a successful slot. Imports do not run a slot,
print, write CSV/pickle data, or create result files. Phase 5 adds no replay,
HTTP/Kubernetes traffic, diagnostics, netem, or bandit behavior.

## IBG-Hybrid activation correction pending

The preceding Phase 5 activation description is historical. Paper review of
`misc/vesal_tex.tex` identified that it incorrectly made high normalized
belief entropy alone sufficient to activate the `S=50` Monte Carlo method.
Because fresh uniform beliefs have entropy `1.0`, that rule sends every flow
in a normal new 20x3x10 slot through Monte Carlo and is not the intended
Hybrid operating mode.

The corrected architecture will carry explicit immutable slot-level
uncertainty-event metadata. Normal initialization, including uniform beliefs,
does not set that event. Automatic selection will remain deterministic:
Monte Carlo only when the uncertainty event is present *and* entropy is at
least `0.75`; otherwise deterministic `D=2` lookahead under contention at
least `0.70` or explicit high priority; otherwise Phase 2 greedy. The three
existing policy methods and their focal-only objectives remain unchanged.
This correction is pending implementation and validation; the historical
non-terminal uniform-belief attempt is not performance evidence for the
corrected normal path.

### IBG-Hybrid lookahead-default clarification

The preceding pending correction still incorrectly described greedy as the
normal final Hybrid path. The paper's **Pruned Lookahead Rollout** defines the
Hybrid Lookahead algorithm as: prune to `Phi_C`, then, for each focal
candidate, simulate the next `D` flows using greedy as the continuation/base
policy. Its evaluation explicitly identifies Hybrid IBG (Lookahead) as
`C=5, D=2`. Therefore, for this project's active IBG-Hybrid algorithm, every
normal feasible focal decision must use pruned `D=2` lookahead (clamped only
when fewer future flows remain), then commit that focal action. Greedy remains
the internal continuation policy and a separately named fast-pruning variant,
not the ordinary final Hybrid decision path.

The dynamic-composition text's low-contention fast commit is an optional
operational variant in the paper, not the accepted replacement for the
user-authorized Hybrid Lookahead implementation. Monte Carlo remains an
exceptional uncertainty/churn path. The pending correction must consequently
replace the runner's default greedy activation with default lookahead as well
as prevent uniform belief entropy alone from selecting Monte Carlo.

### IBG-Hybrid sequencing: core lookahead before Monte Carlo

Hybrid work is now explicitly split. First, correct and validate the core
production algorithm: per-flow `C=5` pruning followed by default pruned
`D=2` lookahead, with greedy used only for its simulated continuation flows.
That core path must complete normal 20x3x10 slots, learn from completed
selected observations, and provide runtime evidence without invoking Monte
Carlo.

Second, handle Monte Carlo as a separate future design and validation phase.
The completed Phase 4 implementation evaluates up to 75 focal actions times
50 rollouts per real decision and is therefore a correctness boundary, not a
production-ready fallback at 20 flows. It must not be selected automatically
until a separately accepted bounded/scalable MC design, semantics, tests, and
runtime evidence exist. This sequencing does not remove the MC method or
alter its historical contract; it removes it from the core Hybrid completion
path.

### IBG-Hybrid core-lookahead correction implemented

The pure slot runner now implements the corrected core path under
`ibg-hybrid-policy-contract-v2`. Every real focal decision obtains the
current feasible `C=5` pruned pool for diagnostics and then calls the existing
deterministic lookahead method. The requested depth remains `D=2`; effective
depth is clamped only to the actual later flows. All projected continuation
actions use the unchanged Phase 2 joint-greedy policy and remain branch-local;
only the selected focal action enters real slot loads.

Entropy, contention, and priority remain immutable recorded activation
diagnostics but no longer select greedy or Monte Carlo. Automatic orchestration
cannot call the Phase 4 MC method. The separate explicit MC method and its
correctness tests remain present for the later redesign phase.

The Phase 2 implementation now reuses immutable configured choices/actions and
memoizes the pure shared expected-stage-utility result by complete belief value
and load. It also composes precomputed replica admission results when
accounting for complete actions instead of repeatedly revalidating identical
structure. These are semantics-preserving pure-policy optimizations: readiness,
capacity, directed-link rejection reasons, canonical ordering, pruning,
scores, selected actions, and complete accounting remain covered by the
unchanged Phase 2--4 characterization tests.

### Current manual lookahead-depth override

At user direction, the active default is now `D=3` under
`ibg-hybrid-policy-contract-v3` for manual Hybrid inspection. Normal slots
therefore project the next three flows where available; only the final three
decisions clamp to depths 2, 1, and 0. This is a current user-selected
parameter override, not a new latency, learning, MC, or infrastructure
contract.

### Professor-authorized MC root selection

The earlier statement that paper-aligned MC must evaluate every action in the
pruned set is superseded by the user's professor's implementation direction.
MC is MCTS-inspired and has an explicit root-selection stage: rank the
complete feasible pruned actions by their current deterministic joint score,
retain the canonical top `Q=10` actions, and evaluate only those actions by
rollout. The professor's 125-path value is an illustrative larger candidate
set; the active `L=2`, three-stage, `C=5` configuration has at most 75
complete pruned actions before this root selection.

For each of the retained ten focal actions, run exactly `S=50` independently
seeded continuations. Each continuation simulates up to the active `D=3`
later flows, clamped at the end of a slot. No simulated future flow invokes
deterministic lookahead: it uses the current Phase 2 greedy policy, with the
existing epsilon-greedy noise only where that rollout contract applies.
Only the selected focal action enters real loads. Bandit/UCB/Thompson methods
are prohibited from this MC path.

### Active depth restored to `D=2`

The user has reverted the temporary manual `D=3` inspection override. The
active default is again `D=2`, versioned as
`ibg-hybrid-policy-contract-v4`. This applies to core lookahead and the
future MC greedy-continuation horizon; the final two core decisions clamp to
depths 1 and 0.

## MILP baseline architecture

This section opens a separate MILP workstream and does not replace or remove
the preceding IBG-Exact or IBG-Hybrid history. IBG-Hybrid core lookahead and
its professor-directed top-`Q` Monte Carlo redesign are temporarily paused in
their current state. No Hybrid or Exact behavior is to change while the MILP
baseline is developed.

The active MILP target is the centralized, coupled/budgeted benchmark using
the user-selected `L=2` action model. The initial default configuration is 15 flows,
3 stages, and 10 replicas per stage (`M=30` total), matching the
largest small-scale MILP topology stated in `misc/vesal_tex.tex`. Every flow
must select exactly `L=2` replicas from two distinct stages; at the initial
three-stage profile the third stage is bypassed completely, while a run with
`K` stages bypasses `K-2` stages. This is an explicit project override of the paper's
separate SFC-specific `L=K` remark.

MILP is not another IBG equilibrium solver. It receives the complete batch of
flows and solves one centralized whole-slot social-welfare problem. Its
planner is intentionally clairvoyant: the paper defines the MILP baseline as
having perfect knowledge of each replica's true state. True state is therefore
an authorized MILP planning input, while it remains forbidden in Exact and
Hybrid selection. Flow beliefs, private-signal learning, sequential
best-response continuation, pruning, lookahead, and Monte Carlo do not enter
the MILP objective.

The target pure formulation uses explicit binary placement and stage-selection
variables, final replica-load/count indicators, and linearized selected-pair
variables. Its constraints must enforce:

- exactly two selected stages per flow and exactly one replica in each of
  those stages;
- no assignment or outcome contribution from the bypassed stage;
- Ready/availability and declared assigned-flow capacity;
- one configured nonnegative directed planning-link value for the selected
  ordered pair; and
- any later node-resource constraint only through an explicit versioned
  demand/capacity contract, never by treating existing Pod requests as a
  per-flow charge.

The objective maximizes aggregate final-load social welfare. Replica welfare
uses the frozen state/load-conditioned physical-latency and linear-utility
concepts under the known true state. The one configured selected-pair planning
cost is deducted per flow through the linearized pair choice. Measured runtime
pair latency and observation-only jitter are outcome telemetry and must never
be substituted into the optimization coefficients.

An optimal result is accepted only when the backend reports a proven optimal
status. A time-limited feasible incumbent must retain the best bound, gap,
runtime, solver/backend version, and termination reason and must not be called
optimal. The paper names Gurobi 10.0; the implementation will keep a
backend-neutral model boundary so small deterministic tests can use an
available open solver, while paper-replication claims require the actual
backend and version to be recorded.

The existing files under `MILP/` are disposable prototype material. The audit
found that they currently:

- run fifty experiments, print, and write CSV/pickle-related output from the
  import path;
- default to the decoupled solver (`is_budgeted = 0`);
- configure 30 replicas *per stage* rather than the paper's 30 total;
- define `budget = num_of_stages + 2` but ignore it in the budgeted solver,
  which instead hard-codes `B=20`;
- model budget as a sum of legacy random replica costs rather than exact
  cardinality `L=2`;
- allow arbitrary stage skipping and do not require exactly two selected
  stages;
- omit selected-pair link cost, Ready availability, and declared capacity
  from the optimization;
- optimize obsolete two-state inverse utility and positive-seat filtering
  rather than the active four-state physical-latency/linear-utility contract;
- use beliefs and iterative learning even though the paper's MILP baseline
  has perfect state information;
- shuffle global RNG state and accept a merely feasible solver status without
  preserving bound/gap provenance;
- contain a broken budgeted orchestration path whose solver returns
  `(assignment, counts)` but whose caller passes that tuple to the old
  per-stage update function; and
- depend on OR-Tools without declaring it in `requirements.txt`.

The replacement must be import-safe and pure at its solver boundary. A later
MILP slot runner may reuse algorithm-neutral Exact latency, physical versus
observation jitter, utility/SLA/fairness, result, and simulation/Kubernetes
adapter concepts. It may reuse the stable two-selected-stage route shape from
Hybrid, but must not import Hybrid pruning, lookahead, Monte Carlo, activation,
or belief-driven scoring. MILP-specific contracts remain under `MILP/`.

For simulation and Kernel execution, solve all placements first and then run
only the selected two-hop routes. The existing private-processor/public-
forwarder split, Ready discovery, final-assigned-load conditioning, and one
selected-pair telemetry record per flow should be reused through adapters.
Physical realized utility, the active physical-only 110-ms SLA, raw
physical-plus-pair latency, Jain fairness, and runtime must keep their existing
units and separation. Because MILP already knows the true states, selected
observations may be retained for matched traffic/telemetry evidence but do not
update or steer the MILP policy, and MILP runs do not stop on belief
equilibrium.
### MILP per-run cutoff contract

The future MILP executable must accept `--cutoff SECONDS` on every run. The
value is a finite positive number of wall-clock seconds supplied by the user
and passed to the selected solver backend through its native time-limit API;
it is not a hard-coded model constant. Structured results must retain the
requested cutoff, actual solve duration, termination status, incumbent, best
bound, and optimality gap. Reaching the cutoff with an incumbent yields a
usable but unproven feasible result; it must never be labelled optimal.

## MILP Phase 0 formulation boundary

`MILP/phase0_contract.py` is the import-safe, solver-free source of truth for
`milp-coupled-phase0-contract-v1`. The paper supplies the centralized
perfect-state baseline envelope, Gurobi 10.0 identity, and the maximum
reported `N=15`, `K=3`, `M=30` topology; it does not give a complete MILP
linearization. The variable families and constraints below are therefore an
explicit project contract for the user-authorized `L=2` override, not a claim
that the paper prints this exact model.

All mathematical indices are one-based and runtime-configurable: flow count,
stage count, and replicas per stage vary per run. The initial default profile
is 15 flows, 3 stages, and `(10,10,10)` replicas, for 30 replicas total. A per-flow action
is an immutable canonical pair ordered by `(stage, replica)`, with exactly two
distinct stages and one replica in each. The initial three-stage profile has
one bypassed stage; a general `K`-stage run has `K-2` bypassed stages.
Whole-slot records are ordered by
flow ID and replica records by stage then replica; this deterministic record
order does not pretend that a backend's arbitrary symmetric optimum is itself
canonical.

The future backend-neutral formulation has four binary variable families:

- `x[i,k,j]` places flow `i` on replica `(k,j)`.
- `y[i,k]` selects stage `k` for flow `i`.
- `z[k,j,n]`, including `n=0`, selects the final assigned load of a replica.
- `p[i,k,j,k2,j2]` linearizes the selected directed pair for `k<k2`.

The frozen constraints are `sum_k y[i,k]=2`,
`sum_j x[i,k,j]=y[i,k]`, Ready availability, a declared nonnegative
assigned-flow-per-slot capacity, exactly one final-load indicator, equality
between placement counts and the selected final load, standard binary-AND
pair linearization, and exactly one directed pair per flow. Model input must
provide one finite nonnegative planning-link coefficient for every
structurally possible lower-stage/higher-stage replica pair: 300 coefficients
at the initial topology. Node CPU, memory, and bandwidth vectors remain
absent until per-flow demand units are separately accepted.

The objective is centralized final-load welfare:

```text
maximize sum[k,j,n] n * U_true_state[k,j,n] * z[k,j,n]
         - sum[i,selected directed pair] planning_link_ms * p
```

`U_true_state` is deterministic expected physical utility under the known
true replica state and the final assigned load, using the frozen shared
state/load physical-latency and linear-utility semantics in Phase 2. Each
flow contributes its two selected stage utilities and exactly one configured
planning-link deduction. Observation-only jitter and measured selected-pair
latency are outcome-only values and cannot enter these coefficients.

The Phase 0 result boundary distinguishes proven optimal, time limit with a
feasible incumbent, time limit without an incumbent, infeasible, unbounded,
and solver/configuration error. Proven optimal requires matching incumbent
and bound with zero gaps. A timed incumbent remains non-optimal and must carry
its bound and normalized gaps. The normalized absolute gap is
`abs(best_bound-incumbent)` and relative gap divides that value by
`max(1,abs(incumbent))`. Every result also carries the positive finite
requested cutoff, build and solve durations in seconds, backend/version,
termination reason, and supported variable/constraint counts.

The local environment has SciPy 1.18.0 with `scipy.optimize.milp` backed by
HiGHS 1.12.0; a one-binary-variable development smoke solve completed
optimally. This is the available Phase 1/2 candidate for deterministic small
correctness tests. OR-Tools/CBC, Gurobi/gurobipy, PuLP, python-mip, highspy,
Pyomo, GLPK, and standalone HiGHS are not locally available. No dependency
was installed. Only a recorded Gurobi 10.0 run may be described as the
paper-named backend; SciPy/HiGHS timing is separate local evidence.

Phase 1 must expose the runtime dimension inputs through `--flow`, `--stage`,
and `--replica`, together with the independently validated `--cutoff SECONDS`.
The current Phase 0 module deliberately has no executable CLI.

## MILP Phase 1 package boundary

MILP Phase 1 is implemented as `milp-coupled-phase1-boundary-v1`. The
`MILP` package is now import-safe: importing its package, contract, backend,
oracle, CLI, executable, or legacy compatibility modules does not parse
arguments, run an experiment or solve, print, seed an RNG, or create output
files. Explicit execution is available through `python -m MILP` (and the
guarded compatibility module), but Phase 1 accepts configuration only and
states that the production solve remains deferred to Phase 2.

`MILPConfiguration` carries one Phase 0 `MILPDimensions` value and the exact
per-run cutoff. The CLI maps `--flow N --stage K --replica M` to runtime
dimensions `(N, (M,...,M))`, with 15, 3, and 10 as defaults. `--cutoff
SECONDS` is required and is retained without rounding or clamping. All
dimensions are positive, `K>=2`, and `L=2` cannot be overridden. Thus a
general run selects two stages and bypasses `K-2`; only the default `K=3`
case has exactly one bypassed stage.

The complete immutable planner boundary contains canonical replica records
with the authorized true state and Phase 0 admission metadata, every required
directed planning-link coefficient, canonical whole-slot placements and
final loads, the unchanged Phase 0 social-welfare breakdown, and the
unchanged Phase 0 normalized solver provenance. Mapping-shaped adapter data
is validated and converted to ordered tuples so callers cannot mutate the
stored solver input through a shared dictionary.

`MILP.backend` performs read-only capability discovery for the selected free
development family. It verifies that `scipy.optimize.milp` and embedded
HiGHS version metadata are available without constructing or solving a
model, and raises an explicit configuration error when they are absent. The
local result is SciPy 1.18.0 with embedded HiGHS 1.12.0. This boundary makes
no Gurobi or paper-runtime claim.

`MILP.oracle` is an exhaustive centralized final-load welfare oracle for
tests only. It enumerates canonical exact-`L=2` actions, applies the Phase 0
Ready/capacity/link feasibility rules, reconstructs the Phase 0 objective,
and keeps the first canonical placement on an exact tie. It refuses more
than four flows or more than 100,000 complete placements, explicitly
excluding the default 15x3x10 profile. It is not a production solver or a
fallback backend.

The former import-time experiment entry point is replaced by a guarded CLI
shim. The invalid legacy budgeted solver is an explicit retired tombstone,
and the remaining legacy header no longer imports unavailable OR-Tools at
module import time. Phase 0's twelve prototype mismatch records remain the
historical characterization; they are not current behavior to preserve.

## MILP Phase 2 pure solver architecture

MILP Phase 2 is implemented through two import-safe layers. `MILP/model.py`
constructs `milp-coupled-phase2-model-v1` as a backend-neutral immutable
binary linear model. `MILP/solver.py` translates that model to the selected
SciPy/HiGHS backend and returns the existing Phase 1 result wrapped around
the unchanged Phase 0 status and provenance semantics. Neither layer imports
or depends on Hybrid policy code.

The pure model allocates all four frozen variable families in canonical
order: per-flow/replica `x`, per-flow/stage `y`, per-replica/final-load `z`
including zero, and per-flow/directed-pair `p`. It emits explicit rows for
exact `L=2` stage cardinality, one replica in each selected stage, Ready
availability, assigned-flow capacity, one load indicator, final-load
reconstruction, all three binary-AND inequalities, and one selected directed
pair per flow. Complete planning-link metadata remains a validated input, so
there is no fabricated zero-cost link or partial action fallback.

Known-state stage coefficients call the unchanged
`IBG.latency_model.expected_state_utility` for each replica and possible
positive final load. The model minimizes the negated replica welfare term on
`z` plus the configured planning-link term on `p`, which is exactly the Phase
0 maximization objective. Observation jitter, measured pair latency,
beliefs, learning, flow order, and runtime telemetry do not appear in the
model or callback boundary.

The SciPy adapter builds a sparse constraint matrix only at invocation time,
sets every variable binary on `[0,1]`, passes the requested Phase 1 cutoff to
SciPy's native `time_limit`, and requests zero relative MIP gap. The primary
solve receives the exact requested cutoff. When a primary optimum is proven,
deterministic secondary solves preserve the primary objective exactly and
lexicographically minimize the selected directed-pair rank for each flow in
flow order. Each secondary solve receives only the remaining per-run time.
If the cutoff prevents completion, the result remains an honestly proven
primary optimum but records `canonicalization=flow-label-only`; flow-label
permutations are still normalized by sorting the selected action multiset.

Backend output is independently checked for vector length, finiteness,
binary bounds, integrality, every linear constraint, exact two-stage action
extraction, Phase 0 feasibility, final-load reconstruction, and agreement
between the backend objective and reconstructed social welfare. Invalid
output becomes a solver/configuration error rather than a partial placement.
SciPy status 0, 1, 2, 3, and 4 map respectively to proven optimal, one of the
two time-limit states, infeasible, unbounded, and solver/configuration error.
For maximization, SciPy's minimized primal and dual values are sign-corrected
before applying the Phase 0 normalized absolute and relative gaps.

The default 15x3x10 model has 5,475 binary variables and 14,115 explicit
constraints: 450 `x`, 45 `y`, 480 `z`, and 4,500 `p` variables. Phase 2 only
builds this boundary to verify its dimensions; it does not solve or time the
default target. The public API is `MILP.solve_coupled_milp`. The guarded CLI
continues to validate dimensions/cutoff and reports that problem-input and
slot execution are deferred to Phase 3, because no fabricated true-state,
admission, or planning-link profile is authorized.

## MILP Phase 3 pure simulation-slot architecture

MILP Phase 3 is implemented under `milp-coupled-phase3-slot-v1` without
changing the Phase 0--2 formulation or solver. `MILP/runner.py` calls the
public `solve_coupled_milp` boundary once for the complete slot. It executes
only a proven optimum or a validated time-limited feasible incumbent; every
non-incumbent status and every invalid placement fails before simulation.
The requested cutoff and the complete backend, termination, incumbent,
bound, gap, model-count, build-time, and solve-time provenance remain attached
to the slot result. A timed incumbent remains explicitly unproven.

`MILP/simulation.py` is a pure in-process adapter. Placement is complete
before it samples anything, and every selected physical latency and exact
convolved likelihood is conditioned on the selected replica's final assigned
load. Each flow produces exactly two selected observations and one measured
selected-pair outcome. A `K`-stage action still bypasses `K-2` stages, which
produce no load, sample, utility, SLA contribution, or pair endpoint.

The adapter derives independent BLAKE2b seeds for physical processing,
observation-only jitter, and measured-pair outcome streams from immutable
root-seed/slot/flow/identity data; final endpoint loads are included where
relevant. Every sample uses a local NumPy generator, so slot execution does
not seed or consume Python or NumPy process-global RNG state. True replica
state remains available only in the already-authorized clairvoyant planner
input and inside the physical observation generator; it is not emitted as an
observed value and does not create a learning loop.

Measured-pair profiles are explicit outcome-only inputs, separate from the
configured directed planning-link coefficients. Their in-process law is
`base_ms + |Normal(0,jitter_ms)|`. This does not replace or feed back into the
MILP objective. Likewise, physical processing, observation-only jitter, noisy
telemetry signal, measured pair latency, and raw physical-plus-pair latency
remain distinct fields. Observation-only jitter is excluded from physical
realized utility and the active physical-only 110-ms SLA.

The immutable slot result retains all Phase 0--3 contract versions,
configuration/cutoff, root seed and slot ID, placement and bypasses, final
loads, observations, pair outcomes, expected planner welfare/link deduction,
physical realized and reference utility, per-flow and total latency, SLA,
Jain fairness, and build/solve/simulation/total timing. Jain fairness retains
the Exact/Hybrid comparison basis of expected per-flow planner utility;
realized per-flow utility is recorded separately. The pure runner is silent;
only the explicit wrapper prints one compact line. The guarded dimension CLI
still refuses to fabricate true-state, admission, link, seed, or outcome
profiles and instead points callers to a fully supplied `MILPSlotInput`.

## MILP Phase 4 scale-evidence architecture

MILP Phase 4 adds `milp-coupled-phase4-scale-v1` without changing the model,
solver, or slot contracts. `MILP/scaling.py` builds a declared synthetic
benchmark profile from stable BLAKE2b values rather than global RNG state.
The profile supplies complete true states, Ready/capacity records, configured
planning links, and separate measured-pair outcome profiles. It is versioned
as `milp-scale-synthetic-profile-v1` and is scale evidence only, not a
deployment or paper input profile.

One scale case owns runtime dimensions, exact `L=2`, the user-requested
cutoff, profile/root seeds, and slot ID. It calls the public Phase 2 solver
exactly once through the Phase 3 runner. A proven optimum or timed feasible
incumbent executes the in-process slot; a timeout without an incumbent or
another terminal failure remains solver evidence and skips simulation. No
heuristic placement is substituted.

Scale evidence retains backend/version, status/proof flag, incumbent, bound,
normalized gaps, model-build/solve/simulation/total wall time, variable and
constraint counts, and current-process peak RSS. Memory is explicitly the
`resource.getrusage(RUSAGE_SELF).ru_maxrss` process-lifetime high-water mark,
converted to bytes; it is not a solver-only allocation measurement. The
native solver cutoff remains distinct from total process time and is not a
hard process kill, so model construction, result normalization, simulation,
imports, and small backend-return overhead may make total wall time—and even
reported solve-call duration—larger than the requested native limit.

`python -m MILP.benchmark --flow N --stage K --replica M --cutoff SECONDS`
is a guarded one-case benchmark entry point. It prints exactly one compact
evidence line and writes no report. The ordinary `python -m MILP` CLI remains
configuration-only and does not silently adopt the synthetic profile.
`--verify-oracle` is accepted only for deliberately tiny cases and requires
exact objective and canonical-placement agreement with the Phase 1 oracle.

The local free backend remains SciPy 1.18.0 with embedded HiGHS 1.12.0.
No second backend is installed, so backend parity is explicitly
`not-applicable-single-available-backend`; the results are not Gurobi 10.0 or
paper-runtime evidence. The isolated-process one-second scale ladder produced:

| Case | Status | Incumbent | Best bound | Relative gap | Build | Solve | Total | Variables | Constraints | Peak RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1x2x1 | proven optimal | 119.199 | 119.199 | 0 | 0.000534 s | 0.007584 s | 1.026003 s | 9 | 15 | 126.480 MiB |
| 2x3x2 | proven optimal | 299.256 | 299.256 | 0 | 0.003051 s | 0.041854 s | 0.924918 s | 60 | 112 | 128.250 MiB |
| 5x3x4 | proven optimal | 755.652 | 755.652 | 0 | 0.029940 s | 0.752963 s | 1.672026 s | 387 | 841 | 130.070 MiB |
| 10x3x6 | timed feasible incumbent | 1421.08 | 1448.69 | 0.0194227 | 0.056745 s | 1.022321 s | 2.084141 s | 1,488 | 3,524 | 138.586 MiB |
| 15x3x10 | timed feasible incumbent | 1628.29 | 2281.98 | 0.401463 | 0.140502 s | 1.210599 s | 2.458909 s | 5,475 | 14,115 | 182.141 MiB |

The 15x3x10 case therefore completed with an executable incumbent but did not
prove optimality. A second isolated one-second run reproduced its status,
incumbent, bound, and gap; build/solve/total time and peak RSS were naturally
different. These bounded local results expose the baseline's scale limit and
must not be generalized into a real-time guarantee.

### MILP benchmark verbose output

The Phase 4 benchmark now accepts opt-in `--verbose`. It prints an immediate
start banner and passes `disp=True` to the existing SciPy/HiGHS adapter, which
exposes native presolve, branch-and-bound, incumbent, bound, gap, node, LP-
iteration, and timing progress. Default execution remains silent until its
single compact completion line. When an optimum is proven, verbose mode also
shows the existing objective-preserving canonicalization solves; these are
secondary tie-resolution solves within the same cutoff contract, not repeated
independent benchmark runs. Verbosity changes output only and does not alter
the formulation, cutoff, seed, status, objective, or evidence contract.

## MILP Phase 5 Kernel architecture

MILP Phase 5 is implemented as a separate `milp-coupled-phase5-kernel-v1`
execution boundary. It does not modify the frozen Exact or Hybrid trees and
does not reinterpret Exact's contiguous, stage-1-first route contract.
`MILP/kernel_contracts.py` defines the versioned
`milp-two-selected-stage-route-v1` wire shape: every route contains exactly
two replicas from distinct stages in increasing stage order. The two stages
may be noncontiguous, such as 1 to 3, and the first selected stage may be
greater than one, such as 2 to 3. Different flows in one centralized slot may
select different stage pairs. The other `K-2` stages are absent from the
route and therefore receive no request, load, observation, pair endpoint,
utility, or SLA contribution.

The controller-side order is strict. `MILP/kernel_adapter.py` first discovers
the complete expected set of Running and Ready StatefulSet ordinals and maps
each ordinal to an immutable `(stage, replica, Pod, node, endpoint)` record.
Only after that snapshot exists does `MILP/kernel_profiles.py` combine the
mounted deterministic replica profiles, their declared assigned-flow
capacities, and a complete versioned directed planning-link document into the
clairvoyant `MILPProblemInput`. `MILP/kernel_runner.py` invokes the public
`solve_coupled_milp` boundary exactly once. A proven optimum or validated
time-limited incumbent proceeds; every status without an incumbent fails
before traffic and has no fallback. All placements are complete before the
adapter publishes any route.

`MILP/kernel_flow_generator.py` is a separate service rather than a change to
the Exact generator. It validates the controller-supplied final assigned load
against the complete route set, starts all flows concurrently, and submits
each route to its first selected public forwarder. The unchanged forwarder
then processes the first selected hop and forwards to the second selected
hop sequentially. The existing private processor remains the only source of
state/load-conditioned physical processing, independent observation-only
jitter, noisy signal, and exact convolved likelihood. The response boundary
requires exact flow/slot/stage/replica/load/Pod/endpoint correlation, exactly
two selected observations, and exactly one selected-pair record per flow.

Kernel observations deliberately have no simulated seed fields and expose no
true-state value. They retain physical processing, observation-only jitter,
noisy signal, likelihood, modeled delay, admitted concurrency, request and
transport timing, and Pod identity. The one measured pair retains the
forwarder-to-forwarder residual and endpoint identities. The frozen Phase 3
status/placement validator and metric computation are reused structurally,
so expected planner welfare, configured planning-link deduction, physical-
only realized utility, the physical-only 110-ms SLA, measured-pair reference
utility, raw physical-plus-pair latency, Jain fairness, and solver provenance
have the same definitions. Traffic time replaces in-process simulation time
only in the Phase 5 timing projection; configured planning links and measured
Kernel pairs remain separate.

The container and Kubernetes resources live under
`deploy/milp-kubernetes/` and use the isolated `milp-testbed` namespace and
`milp-testbed:kernel-phase5` image. The MILP image adds the MILP package and
pins the accepted SciPy 1.18.0 backend while reusing the unchanged Exact
processor and forwarder code. Dynamic replica Services, StatefulSets, and
profile ConfigMap are generated through the unchanged
`testbed.kubernetes_resources.build_runtime_resources` helper. Therefore the
single processor worker on 8081, two public-forwarder workers on 8080,
resource requests/limits, separate local/downstream clients, and 30-second
downstream keep-alive remain unchanged. Namespace-scoped RBAC still permits
only Pod get/list. `scripts/run_milp_kernel.py` accepts runtime dimensions,
mandatory cutoff, an explicit user-supplied uniform planning-link coefficient,
and optional verbose output; it generates one isolated controller Job after
all long-running rollouts are Ready. It creates no CSV or pickle output.

The read-only parity audit against the completed Hybrid Phase 5 pure runner
found no missing algorithm-neutral outcome policy in MILP Phase 3. Both use
final-load physical latency, the same separate half-normal physical and
observation laws, the same exact convolved likelihood, physical-only utility
and 110-ms SLA, planning/measured-pair separation, raw reference utility, and
the same expected-per-flow Jain basis. Phase 5 applies those accepted policies
to Kernel telemetry without importing Hybrid policy, belief, pruning,
lookahead, or Monte Carlo code.

## MILP Phase 6 replay and diagnostic architecture

MILP Phase 6 adds `milp-coupled-phase6-trace-v1` as an immutable in-memory,
JSON-safe record over either a completed pure slot or a completed Kernel slot.
It retains runtime dimensions, Phase 0--6 versions, cutoff/backend/status/
bound/gap provenance, placement and bypasses, final loads, configured selected
planning links, objective components, observations, measured pairs, metrics,
timing, and optional diagnostics. Clairvoyant replica state and admission data
exist only under the explicitly named `private_planner_input` replay section;
observations still expose no true state. Kernel traces additionally retain
Ready endpoint/Pod/node identity without inventing simulation seeds.

`MILP/replay.py` has two separate boundaries. Mathematical/outcome replay does
not construct a model or call a solver: it revalidates exact-`L=2` feasibility,
readiness, capacity, links, bypasses, and final loads; reconstructs known-state
final-load social welfare from configured planning coefficients; validates two
selected observations and one selected pair per flow; and reconstructs
physical-only utility, the 110-ms SLA, raw physical-plus-pair latency,
reference utility, and expected-per-flow Jain fairness. It raises categorized
drift for contracts, placement, loads, coefficients, objective, solver status,
observation/pair coverage, utility, SLA, and fairness. Optional solver replay
is separate: a recorded proven optimum must reproduce its objective and
canonical placement, while a timed incumbent remains unproven and has no
placement-identity requirement.

`MILP/diagnostics.py` records an explicit compatibility catalog and an opt-in
collector. Controller timing and solver resources are adapted to model-build,
solve, execution, total time, model counts, and optional process RSS. Kernel
HTTP timing, forwarding-path telemetry, and selected-forwarder cgroup counters
are algorithm-neutral compatible concepts. Payload diagnostics retain logical
record counts unless explicit wire capture exists. Exact memo-cache entries,
learning footprint, beliefs/equilibrium, and Hybrid candidate/rollout/sample
counts are inapplicable. Diagnostics never enter placement, objective,
physical latency, utility, SLA, or RNG ownership. The guarded
`scripts/milp_diagnostic_compatibility.py` prints this catalog and writes no
report.

## MILP Kernel live-repair architecture correction

Updated: 2026-08-01.

The first live 2x3x2 MILP attempt failed during controller readiness because
the restarted kind cluster had stale `kindnet` and `kube-proxy` Pods whose
host-network addresses no longer matched their nodes. New MILP Pods therefore
received addresses from the wrong node PodCIDRs; both trailing and
non-trailing Service names, kube-dns, and cross-node replica traffic failed.
The existing absolute Service URL was not defective. Restarting only the
`kindnet` and `kube-proxy` DaemonSets and recycling only the isolated MILP
workloads restored correct PodCIDRs, Service DNS, and cross-node reachability.

The repaired retry reached the flow generator and completed the primary MILP
solve, then exposed a separate Phase 5 integration defect. The MILP-specific
flow generator accepts the versioned two-selected-stage route, but each
replica Pod still starts the unchanged Exact public forwarder. That forwarder
requires the next stage to equal `current_stage + 1`, so it rejects a valid
MILP route such as stage 1 to stage 3 with `next forwarded stage must be 2,
got 3`.

The required correction is an isolated MILP public-forwarder application in
the MILP image/deployment path. It must retain the same private processor,
ports, worker counts, HTTP clients, keep-alive, resources, physical/observation
laws, and telemetry schema while validating exactly one later selected hop
rather than Exact's contiguous full-chain rule. `IBG/`, `IBG_Hybrid/`, and the
independently reproducible Exact deployment remain unchanged. This correction
is identified but not yet implemented; no completed live MILP slot or live
utility/SLA result is claimed.

### MILP Kernel forwarder correction implemented

Updated: 2026-08-01.

The live-route gap is now closed by `MILP/kernel_route_forwarder.py`. The
shared Exact forwarder exposes a protected next-hop validation hook and an
optional runtime-injection seam; its default implementation and application
still require `current_stage + 1`. The MILP subclass overrides only that hook:
an entry forwarder may receive exactly one remaining hop whose stage is
strictly greater than the current selected stage. All local processing,
downstream HTTP, keep-alive, pair measurement, identity checks, separated-
jitter telemetry, diagnostics, cgroup behavior, and lifecycle code continue
through the shared implementation.

`MILP/kernel_resources.py` projects the shared resource document into the
isolated namespace and replaces only the forwarder application target with
`MILP.kernel_route_forwarder:app`. The live StatefulSets retain the private
processor on 8081, the public forwarder on 8080, two forwarder workers, the
same requests/limits, separate clients, and 30-second keep-alive. Exact
resources still target `testbed.route_forwarder:app` and retain contiguous
route behavior.

The controller now performs solver-independent Phase 6 trace replay against
the complete in-memory live result before printing success. Replay treats the
optional HTTP root slash introduced by Pydantic `AnyHttpUrl` as a representation
normalization only; host, port, path, Pod, replica, stage, load, action, and
pair identities remain strict. The compact result line exposes route,
observation, and pair counts plus expected-stage, configured-planning,
physical, measured-pair, raw-reference, solver, and timing metrics.

### MILP Kernel launcher progress boundary

Updated: 2026-08-01.

`scripts/run_milp_kernel.py` now emits an automatic compact preflight before
any build, deployment, or solver work. It reports the requested flow/stage/
replica scale, exact `L=2`, replica-Pod/container/serving-worker footprint,
cutoff, planning-link coefficient, cluster node snapshot, build mode, and a
capacity notice when the request exceeds the live-validated 2x3x2 topology.
It then announces and streams each StatefulSet rollout, reports the Ready
snapshot, and names the controller Job before waiting for it. This makes the
deployment/rollout phase visibly distinct from MILP solving. Native HiGHS
branch-and-bound output remains opt-in through `--verbose`; the automatic
launcher progress does not change model inputs, runtime dimensions, placement,
traffic, results, or file-output behavior.

## MILP canonical experiment-input parity repair

Updated: 2026-08-01.

`MILP/experiment_profile.py` defines immutable, JSON-safe
`milp-experiment-profile-v1`, shared by ordinary pure and Kernel experiments.
It retains dimensions and cutoff, exact `L=2`, every replica's true state and
Ready flag, explicit capacity in `assigned-flows-per-slot`, all directed
planning links, the separate pure measured-pair profile, source/mode
provenance, and a canonical BLAKE2b fingerprint. Equal dimensions alone can
therefore no longer be mistaken for equal inputs.

The shared Exact runtime profile remains unchanged and supplies only the
true-state map for the default `milp-experiment` profile. Its historical
`ReplicaProfile.capacity` is not read by MILP admission. The default MILP
limit is the configured flow count per replica, measured in assigned flows per
slot; `--assigned-flow-capacity FLOWS` provides an explicit override. This
dimension-aware complete-slot default is not paper-calibrated or empirically
validated capacity.

Planning coefficients come from either `--planning-link-ms` or a complete
versioned table through `--planning-links`. Uniform mode is faithfully
labelled `uniform-objective-constant`: exact `L=2` deducts the same value once
per flow, so it cannot distinguish pair choices. Measured Kernel pair latency
remains outcome telemetry and never becomes a planning coefficient.

`python -m MILP.experiment` is the import-safe pure entry point. The Kernel
launcher constructs the same profile before Kubernetes work, mounts it into
the controller, and builds the model only after Ready discovery. Kernel adds
endpoint identity and real traffic only after input and placement are fixed.
Compact and structured results retain source, fingerprint, and link mode.

Phase 4 `python -m MILP.benchmark` remains separate and unchanged. Its
`milp-scale-synthetic-profile-v1` continues to use hashed heterogeneous
states/links for scale evidence. The historical pure and Kernel 14x3x7 runs
had equal model dimensions but were not runs of the same input.

A same-input 2x3x2 live gate used fingerprint
`011001de78293ceefae74d4c52a330a5`. Pure and Kernel both proved social welfare
`333.62750071` optimal with equal bound and zero gap under a 10-second cutoff.
Kernel completed two routes, four observations, two measured pairs, and
replay. Expected pure/HTTP outcome differences do not change planner parity.

### MILP planning-latency correction pending

Updated: 2026-08-01.

The uniform `--planning-link-ms 2` option is now explicitly limited to a
solver/route smoke-control input. Under exact `L=2`, it deducts the same
configured value once per flow and therefore carries no pair-selection
information. It is not an acceptable default for a latency-aware coupled
MILP experiment.

The immediate next MILP repair is to provide one deterministic, complete,
heterogeneous directed planning-latency profile to both the pure and Kernel
paths. The centralized MILP will use those declared coefficients before
placement. Post-placement measured Kernel pair latency remains separate
outcome telemetry: it must evaluate the plan and never silently replace its
planning coefficient. This is a profile/input correction, not a change to the
MILP formulation, state/load physical latency law, jitter, utility, or SLA.

### MILP Kernel replica-rollout scalability investigation

Updated: 2026-08-03.

The user has paused planning-latency profile work and opened a separate
infrastructure investigation: determine how the isolated MILP Kernel topology
can safely roll out more replicas. This concerns Pod/container footprint,
requests and limits, scheduling, readiness, startup behavior, and cluster
capacity; it must not change MILP mathematics or outcome policy.

Each replica Pod has a single-worker private processor and two-worker public
forwarder. Its combined request is 75m CPU and 256Mi memory; combined limit is
2 CPUs and 1Gi memory. The next work must measure actual rollout/runtime
resource use before accepting any specification change. More requests can
improve stability but reduce schedulable replicas; lower requests can pack more
Pods but risk starvation, failed health checks, or restarts.

### MILP-owned deployment configuration

Updated: 2026-08-03.

MILP no longer projects IBG's Kubernetes resource builder or runtime profile
file. `MILP/kernel_resources.py`, `MILP/runtime_profiles.py`,
`MILP/kubernetes_api.py`, and `deploy/milp-kubernetes/profiles.json` now own
the MILP resource manifest, profile data, labels, ConfigMap/path, and
Ready-only discovery selector. The initial independent MILP values deliberately
remain equal to the established two-container/three-worker footprint; this is
an ownership separation, not a resource tuning change. Future MILP rollout or
resource changes therefore cannot alter IBG deployment behavior. The shared
processor service and frozen Exact latency/outcome helpers remain deliberate
algorithm-neutral runtime dependencies.

### MILP controller/service image split

Updated: 2026-08-03.

The isolated MILP deployment now uses two images. Replica Pods and the flow
generator use `milp-testbed:kernel-service-phase5`, which contains only the
HTTP service dependencies (NumPy, FastAPI, HTTPX, and Uvicorn) and a minimal
service-package initializer. The controller Job uses
`milp-testbed:kernel-controller-phase5`, which retains pandas and the
SciPy/HiGHS solver backend. The route contract, processor, two forwarder
workers, one processor worker, and Pod resource specifications are unchanged.
This removes solver-only packages from every long-running service Pod; image
size and actual resident-memory effects are measured separately.

In a fresh MILP-only 12-flow/3-stage/6-replica rollout, all 18 replica Pods
became Ready with zero restarts. Matched post-start cgroup samples show the
two-worker forwarder at a mean 119.7MiB, versus 175.5MiB for the former broad
image (a 55.8MiB, 31.8% reduction per forwarder). The single-worker processor
remained about 40.6MiB. This is a service-image footprint result only; it does
not alter worker count, resource declarations, route behavior, or the MILP
algorithm.

### MILP bounded replica-rollout and processor memory boundary

Updated: 2026-08-03.

The MILP-owned replica manifest now declares the private processor at a fixed
50m CPU/64Mi memory request and 1 CPU/256Mi memory limit. These are per-Pod
declarations; they do not vary with the requested replica count. Its one
worker, image, command, port 8081, probes, environment, and processor service
remain unchanged. The two-worker public forwarder remains fixed at its prior
25m CPU/128Mi memory request and 1 CPU/256Mi memory limit.

`scripts/run_milp_kernel.py` accepts a positive
`--rollout-batch-size REPLICAS` option (default `2`). It first applies each
MILP StatefulSet at the first bounded target, then scales every requested
stage to the next deterministic target and waits for every stage to be Ready
before advancing. A target of six with the default produces `2 -> 4 -> 6`; a
target of three produces `2 -> 3`. The final StatefulSet desired count remains
the requested `--replica` value. This affects only deployment timing and
resource declarations: profile construction, centralized MILP placement,
controller invocation, cutoff, route execution, and outcome semantics are
unchanged.

The fresh MILP-only 6-flow/3-stage/3-replica live validation completed the
`2 -> 3` sequence. All nine two-container replica Pods became Ready with zero
restarts, used the lean service image, and ended at three desired/Ready
replicas per stage before the controller started. Direct post-run cgroup
samples measured processor use at 40.5--40.6MiB under the 256MiB cap and
forwarder use at 119.2--120.3MiB under its unchanged 256MiB cap. The earlier
12x3x6 lean-image sample remains the only broad-image before/after comparison;
the new 6x3x3 measurement is a smaller-scale resource-limit validation, not a
node-level or same-scale RSS reduction claim.

### MILP existing-replica rollout correction

Updated: 2026-08-03.

The initial batching implementation incorrectly reapplied the first batch
target on every launch. That would have scaled an existing three-replica stage
down to two before a requested scale-up to six. The launcher now reads the
consistent existing desired count from all MILP StatefulSets before applying
the replica manifest. A scale-up preserves that desired count and batches only
the missing replicas: with batch size two, `3 -> 6` becomes `3 -> 5 -> 6`. A
fresh deployment still begins at `2 -> 4 -> 6`; an explicit lower requested
target still intentionally scales down. Inconsistent or partial existing
StatefulSet sets fail explicitly rather than guessing their state.

This corrects replica-count behavior only. The current profile ConfigMap hash
is part of the StatefulSet Pod template, so changing dimensions/profile data
also triggers a rolling refresh of already-existing Pods. Live 3-to-5 evidence
therefore confirms no scale-down to two and only two newly required ordinal
replicas, but it does not claim that the original three Pod processes remain
running unchanged. Avoiding that profile-driven refresh is a separate runtime
profile/rollout design task.

### MILP append-only runtime-profile rollout repair

Updated: 2026-08-03.

That profile-refresh task is now complete for append-only replica scale-up.
The global `milp.profile-hash` was removed from the StatefulSet Pod template:
adding entries for new replica ordinals no longer changes the template and
therefore does not roll existing Pods. Before applying a changed runtime
ConfigMap, the launcher compares the profiles of every existing
`(stage, replica)` identity with the planned values. It permits unchanged
existing identities plus new identities, but fails explicitly if a running
identity's state/runtime profile would change. That avoids silently using a
stale processor profile without reintroducing an all-Pod rollout.

Removing the legacy annotation required one migration rollout of the existing
five-replica topology. The subsequent live 10-flow 5-to-6-per-stage scale-up
kept every recorded ordinal 0--4 Pod UID unchanged, created only ordinal 5 in
each stage, reached 6/6 Ready for all three StatefulSets, and completed a
valid controller slot. A future deliberate profile change for an existing
replica remains an explicit refresh/redeployment operation, not an implicit
side effect of scale-up.

### MILP heterogeneous planning-link profile repair

Updated: 2026-08-03.

The pre-placement planning-link boundary now retains the
`milp-planning-links-v1` contract version, a semantic source identity, the
`explicit-directed` or `uniform-objective-constant` mode, and the canonical
whole-experiment fingerprint in both pure and Kernel experiment results. The
same fields are emitted in their compact provenance output. The canonical
planner input remains the complete ordered tuple of lower-stage-to-higher-
stage replica pairs; pure and Kernel builders use the same parser and produce
equal `MILPProblemInput` values for the same profile and dimensions.

Explicit JSON validation requires exact runtime-dimension coverage, strict
positive-integer stage/replica IDs, increasing distinct stages, finite
nonnegative costs, canonical completeness, and no duplicate pair. A requested
file is never replaced with generated values. Uniform `--planning-link-ms`
behavior is unchanged and remains explicitly marked objective-constant under
exact `L=2`.

`MILP/planning_links.py` is an import-safe, stdout-only generator for a
complete deterministic heterogeneous example at user-supplied stage/replica
dimensions. Its source is deliberately labelled `not-calibrated`; it is a
reproducible test/demo profile, not measured network evidence. Actual Kernel
pair latency is still generated after placement and remains outcome telemetry
only. It cannot update or replace same-slot planning coefficients.

### Future cross-baseline seeded state-profile boundary

Requested: 2026-08-03. Not implemented.

Every algorithm path—IBG-Exact, IBG-Hybrid, MILP, and future baselines—will
eventually accept a common --seed state-profile control with default 2050.
It will deterministically create the complete replica hidden-state map once at
experiment initialization, retain that map and seed as run provenance, and
hold it fixed across every slot/iteration of that experiment. The same
state-profile seed/map must be usable by all compared algorithms. It is
separate from seeds used for physical, observation, flow-order, or other
post-placement stochastic streams.

### MILP temporary synthetic-scale planner-profile parity mode

Updated: 2026-08-03.

The opt-in `--planner-profile synthetic-scale --profile-seed SEED` mode adapts
the existing Phase 4 benchmark generator into the canonical
`MILPExperimentProfile` boundary. It supplies the same true-state,
Ready/admission-capacity, directed planning-link, and pure measured-pair tables
as `MILP.benchmark` for equal dimensions, cutoff, and profile seed. The Kernel
launcher also rewrites only MILP-owned runtime Pod state values to match that
planner table before rollout. It is a controlled same-input solver comparison,
not a measured-latency calibration or a changed default.

Ordinary `runtime` mode remains unchanged and requires one planning-link input.
`synthetic-scale` supplies its own complete table and rejects both planning-link
flags. Existing Pods with different state profiles are rejected by the existing
append-only guard and must be deliberately refreshed for this comparison.

### MILP solver-difficulty profile finding

Updated: 2026-08-03.

The observed fast normal-Kernel solve and cutoff-bounded Phase 4 benchmark do
not represent the same MILP instance merely because dimensions match. The old
normal 3x10 runtime state profile repeats its five-replica pattern at replicas
6--10 and contains ten state-4 replicas across three stages; its explicit demo
link generator follows a smooth stage-span/replica-distance formula. In
contrast, the Phase 4 synthetic profile at seed 20260801 has only four
state-4 replicas, no state-4 replica at stage 2, and 292 distinct values among
its 300 directed planning links (0.566--5.482 ms). Both retain the same
dimension-aware assigned-flow capacity. These materially different known-state
and planning-coefficient tables can cause HiGHS to explore very different
search trees.

The opt-in synthetic-scale mode is the accepted temporary test/fix: it makes
pure and Kernel planners use the benchmark's complete table and matching Pod
states. It does not establish that any one state or link is solely responsible,
does not make generated values real network latency, and does not replace the
separate future latency-calibration work.

## IBG-Hybrid Kernel rollout/resource feasibility evaluation

Updated: 2026-08-06. Evaluation only; no implementation or live validation.

The completed MILP rollout work is architecturally useful for a future
IBG-Hybrid Kernel path, but it must be adopted through a Hybrid-owned
deployment boundary. Hybrid must have its own namespace, labels, ConfigMaps,
runtime profiles, discovery selector, flow generator, controller, images, and
rollout state. It must not share deployment ownership with either
`ibg-testbed` or `milp-testbed`.

| MILP optimization | Hybrid applicability | Required Hybrid boundary |
| --- | --- | --- |
| Dedicated deployment ownership | Reusable with adaptation | Use Hybrid-specific names and contracts. The controller must retain beliefs across slots and must never receive MILP's clairvoyant planner input. |
| Lean service/controller image split | Reusable with adaptation | Replica Pods and the flow generator need only HTTP/runtime dependencies. The controller image needs Hybrid policy/learning dependencies, but not SciPy/HiGHS merely because MILP uses them. |
| Private processor/public forwarder split | Reusable concept | Preserve one processor worker on 8081, two forwarder workers on 8080, separate local/downstream clients, and the active keep-alive behavior. Add a Hybrid-owned versioned two-hop route validator; neither Exact's contiguous route validator nor MILP's controller contract can be reused as-is. |
| Processor 50m/1 CPU and 64Mi/256Mi memory | Evidence required | The CPU values are a reasonable unchanged starting point. The lower memory declaration was measured only for MILP's lean service image and must pass Hybrid image cgroup, probe, restart, and traffic tests before acceptance. |
| Forwarder two workers and 25m/1 CPU, 128Mi/256Mi | Reusable baseline with evidence | Preserve the current workers, clients, and resources initially. Hybrid's 20 concurrent two-hop routes need controlled queueing, throttling, memory, and restart evidence; lowering these values or changing workers is not authorized. |
| Bounded per-stage rollout batches | Reusable with adaptation | A Hybrid launcher may use deterministic all-stage targets and wait for every stage at each target before proceeding. Batching must not start the controller early or change the requested final replica count. |
| Preserve existing replicas and add only missing ordinals | Reusable | Scale-up must begin from a complete, consistent existing StatefulSet count, never shrink first, and fail on partial/inconsistent stage ownership. Explicit scale-down remains a separate deliberate action. |
| Append-only runtime-profile handling | Reusable with adaptation | Keep existing profile entries byte-for-byte equal, add only new ordinal entries, and reject drift for running identities. Hybrid beliefs remain controller state and must not be placed in the Pod runtime-profile ConfigMap. |
| Incremental readiness/scalability | Evidence required per phase | Do not use 20x3x10 as one combined infrastructure gate. Validate each ownership, route, image, rollout, profile, and resource phase separately; choose a larger live scale only after the preceding phase is accepted. |

Hybrid's policy/runtime differences remain outside the replica service. Each
flow is selected sequentially through belief-driven pruning and deterministic
lookahead, while traffic begins only after all focal actions are committed.
The controller must retain learned beliefs across slots. Future Monte Carlo
cost belongs to the controller CPU/memory/deadline boundary and does not
justify changing replica resources. The skipped stage, noncontiguous routes,
and routes beginning after stage 1 require explicit Hybrid route tests.

The processor/forwarder process split is already present in the shared Exact
runtime and is not a new Hybrid implementation phase. Future Hybrid work only
needs to preserve that boundary while adding its own L=2 routing and deployment
ownership around it.

## IBG-Hybrid Monte Carlo professor-baseline correction

Updated: 2026-08-06. This supersedes the earlier planned `Q=10` production MC
root shortlist; that earlier text remains historical.

The professor's MC baseline starts from the existing feasible complete pruned
`L=2` action pool, which has at most 75 complete routes under the current
per-stage `C=5` pruning. It first ranks that full pool by immediate joint score
with canonical ties, then retains exactly the top five complete routes (or all
when fewer than five are feasible). The five-route MC shortlist is distinct
from the existing per-stage pruning meaning of `C=5`; implementation must use
an unambiguous root-shortlist name rather than silently changing per-stage
pruning.

Each retained route receives `S=50` independent rollouts. `D=2` remains the
accepted project rollout horizon. Within a rollout, each future flow rebuilds
its current-state Phase 2 feasible/pruned pool and normally takes the canonical
greedy action, while occasionally taking a seeded uniform action from that
same pool. This epsilon-greedy action choice is the MC noise described by the
professor; no hidden true state, physical sample, observation noise, or
measured-pair outcome enters planning.

For each root route, MC averages only the current/focal flow's projected final
utility, with its configured planning-link cost deducted once. It then selects
the canonical greatest mean. The historical all-feasible-route MC remains a
reference/test path only. Automatic MC remains disabled pending the dedicated
redesign and a later explicit uncertainty-event activation contract.

## IBG-Hybrid rollout/resource work postponed

Updated: 2026-08-06.

The evaluated Hybrid rollout/resource optimizations are postponed. Do not
implement image splitting, resource changes, batching, existing-replica
scale-up, append-only profiles, or any deployment work while completing the
pure MC correction. Reopen and apply those infrastructure phases only during
the later Hybrid Kubernetes/node implementation, one separately authorized
phase at a time.

### IBG-Hybrid separate deterministic and MC depths

Updated: 2026-08-06. This supersedes the preceding MC statement that shared
`D=2` as its full rollout horizon.

Hybrid now has two semantically separate depth controls. `D_LOOKAHEAD=2`
remains the deterministic normal-Hybrid lookahead depth. `D_MC=10` is the
number of noisy MC rollout arrivals after a tentative focal route. In that
MC window, each simulated arrival rebuilds its updated-state Phase 2 pool and
uses seeded greedy-with-epsilon-noise choice. The remaining hypothetical flows
after the clamped `D_MC` window complete the branch through pure canonical
Phase 2 greedy choice only: no noise, no deterministic lookahead, and no
recursive MC. Their loads still contribute to the focal flow's final projected
utility.

Both values must be separately named, versioned, recorded, and tested. Equal
values are not an excuse to share one parameter. The actual next MC redesign
uses `D_MC=10`; it does not alter `D_LOOKAHEAD=2`.

## IBG-Hybrid professor-baseline Monte Carlo implementation

Updated: 2026-08-06. Pure-Python implementation complete.

`ibg-hybrid-policy-contract-v5` makes the production MC boundary explicit.
Phase 2 still prunes at most five replicas per stage and enumerates at most 75
feasible complete `L=2` roots for the default three-stage topology. Production
MC ranks that full root pool by immediate joint score with canonical ties and
samples only `HYBRID_MC_ROOT_SHORTLIST_SIZE=5` complete routes. The other
roots remain recorded with their scores but receive no rollout.

Each sampled root receives 50 independently seeded branches. A branch commits
the focal route locally, applies `D_MC=10` updated-state epsilon-greedy Phase 2
continuations, and then completes every remaining hypothetical arrival with
updated-state pure Phase 2 greedy. The tail consumes no exploration choice and
never invokes lookahead or MC. Only the focal route's expected two-stage
utility at the completed branch loads is scored, with its planning link
deducted once; only the selected focal route is returned as a real commit.

The decision record retains the ranked pool, sampled and excluded roots,
immediate scores, root mode, contract version, `S`, epsilon, requested and
effective MC depth, tail length and actions, per-step Phase 2 accounting,
seed keys/derived seeds, failures, and canonical selection. Normal lookahead
still uses the independent `D_LOOKAHEAD=2`. The former all-feasible-root,
truncated-depth MC is retained only as
`select_monte_carlo_all_roots_reference`.

The ordinary slot runner remains unchanged: every automatic placement still
uses deterministic lookahead, so production MC is reachable only through an
explicit policy call. No Hybrid Kubernetes, node, rollout, image, traffic,
learning, latency, utility, or SLA boundary changed.

## IBG-Hybrid explicit MC execution and bounded parallel rollouts

Updated: 2026-08-06.

`scripts/run_hybrid_iterations.py` now accepts `--policy lookahead|mc`.
`lookahead` remains the default and retains the established automatic
deterministic path. `mc` is explicit-only: every real focal flow invokes the
v5 production top-five MC selector, commits only its selected focal route, and
then the unchanged runner performs the complete simulation, selected-only
learning, metrics, and equilibrium step after all flows have been placed.

Explicit MC also accepts `--mc-workers N`, defaulting to three local process
workers on this four-CPU development host. Only the independent shortlisted
root rollout groups inside one focal MC decision run concurrently. Real flows,
root ranking, the fifty seeded samples per root, canonical result collection,
focal selection, and all state commits remain deterministic and sequential at
their required boundaries. Worker count is execution scheduling only; it does
not change the v5 algorithm, seeds, utility, learning, latency, or outcomes.

MC remains a manual-only execution mode. No automatic entropy, contention,
priority, or uncertainty-event trigger is part of the active runner.

The runner creates the bounded local MC process pool once for the placement
phase of an explicit MC slot, reuses it for every real focal decision, and
closes it before in-process simulation and learning. It is not a Kubernetes
worker pool and has no lifecycle beyond that one pure-Python slot.

## Hybrid Kernel sequencing clarification

Updated: 2026-08-06. Planning only; no Hybrid Kubernetes code has changed.

The detailed Phase 0--8 sequence in `ROADMAP.md` remains authoritative. It
already joins each rollout/resource optimization to its proper Kernel
implementation phase: image split, first live gate, bounded rollout,
append-only profiles, resource evidence, and incremental scale validation.
This paragraph is only a compact summary of that existing plan, not a separate
or replacement phase track.

## IBG-Hybrid Kernel Infrastructure Phase 0 boundary

Completed: 2026-08-06. Contract-only implementation; no Kubernetes resources
were created.

`IBG_Hybrid/kernel_infrastructure_contract.py` is the import-safe,
pure-Python ownership boundary for the future Hybrid Kernel runtime. Its
active infrastructure contract is
`ibg-hybrid-kernel-infrastructure-phase0-v1`. Hybrid owns the namespace
`ibg-hybrid-testbed`, the `ibg-hybrid-*` controller, ServiceAccount, discovery
Role, flow-generator, and ConfigMap names, the `ibg-hybrid-replica` selector,
the `ibg-hybrid.stage` stage label, and distinct service/controller image
names. These values cannot alias the frozen Exact `ibg-testbed` or MILP
`milp-testbed` ownership boundaries.

The versioned runtime-profile contract contains only canonical replica
identity, processor hidden state, and deterministic observation seed for every
configured replica. Learned beliefs are deliberately absent and remain
controller-private across slots. Assigned-flow admission capacity and directed
planning links remain separate controller inputs rather than processor-profile
fields.

The versioned Ready-discovery snapshot requires exact stage/replica coverage,
Running and Ready status, Hybrid namespace and labels, and StatefulSet ordinal
identity. It is a pure validator in Phase 0; no Kubernetes API adapter exists
yet. The controller lifecycle is frozen as: complete Ready discovery, all
sequential focal placements, selected-route execution, complete telemetry
validation, selected-only learning, then one slot result. Traffic therefore
cannot begin before complete placement, hidden state cannot enter Hybrid
policy, beliefs persist between slots, and automatic MC activation remains
disabled.

The reusable runtime boundary records the existing one-worker private
processor on port 8081, two-worker public forwarder on port 8080, separate
local/downstream clients, and 30-second public-forwarder keep-alive. Phase 0
does not implement Hybrid two-hop routing or accept resource sizes: routing
remains Infrastructure Phase 1 and resource evidence remains Infrastructure
Phase 7. Image ownership is separated now only as a contract: service owns the
processor, forwarder, and flow generator; controller owns Hybrid policy,
learning, and orchestration; MILP solver dependencies are forbidden.

## IBG-Hybrid Kernel Infrastructure Phase 1 route boundary

Completed: 2026-08-06. Pure route-contract/execution implementation; no
Kubernetes resources or service application were created.

`IBG_Hybrid/kernel_route_contracts.py` defines the immutable
`ibg-hybrid-two-selected-stage-route-v1` wire boundary. Every flow has exactly
two processor/forwarder hop targets in strictly increasing stage order and one
explicit skipped stage. Routes may be noncontiguous, such as stage 1 to stage
3, and may begin after stage 1, such as stage 2 to stage 3. Different flows in
one slot may select different stage pairs. The complete-slot request uses
canonical flow ordering and requires each selected hop's assigned load to
equal the load reconstructed from all committed routes.

The pure route builder consumes only a complete map of real Hybrid focal
actions and the Phase 0 complete Ready snapshot. It refuses partial placement,
derives final selected-replica loads, and includes only selected endpoints.
The skipped stage cannot appear in a processor request or pair endpoint.

`IBG_Hybrid/kernel_route_forwarder.py` subclasses the frozen Exact public
forwarder only to replace Exact's contiguous-next-stage rule with one strictly
later selected stage. Exact's processor calls, HTTP clients, pair telemetry,
timing, and forwarding implementation are inherited unchanged; the Exact
forwarder itself is not modified. `IBG_Hybrid/kernel_route_execution.py`
concurrently dispatches complete routes through their first selected public
forwarder and validates exactly two correlated processor observations and one
measured selected-pair result per flow.

The executor directly reuses Exact's `RouteProcessResponse`,
`PairwiseLinkTelemetry`, Kernel datapath validation, exact convolved
learning-signal likelihood, and state-estimation helpers. It verifies physical
processing plus independent observation jitter equals the learning signal.
The response exposes metric/learning inputs only through the two selected hop
records: selected physical latency is their sum and selected learning input is
their two signals. No skipped-stage request, observation, learning input,
physical metric input, or measured-pair endpoint can be represented.

The Phase 1 executor is not yet a FastAPI flow-generator service and performs
no discovery or Kubernetes API operation. Phase 2 owns the Hybrid namespace,
RBAC, ConfigMaps, Services, StatefulSets, flow-generator service, Ready
discovery adapter, and controller adapter.

## IBG-Hybrid Kernel Infrastructure Phase 2 boundary

Completed: 2026-08-08. Mocked/controller-level implementation only; no image,
cluster, deployment, or live-traffic operation was performed.

`deploy/hybrid-kubernetes/` is the isolated Hybrid-owned Kubernetes boundary.
Its namespace, namespace-scoped Pod get/list RBAC, labels, selectors, headless
stage Services, three StatefulSets, flow-generator Service/Deployment,
ConfigMaps, and explicit controller Job template use only the Phase 0 Hybrid
ownership. The long-running Kustomize base excludes the controller Job so a
future launcher must finish all rollouts before starting controller traffic.
The static Phase 2 profile is deliberately a small four-flow, three-stage,
two-replica template; it is not a live or large-scale acceptance claim.

The processor runtime ConfigMap follows
`ibg-hybrid-kernel-runtime-profile-v1` and contains complete canonical replica
identity, hidden state, and observation seed only. A separately mounted
`ibg-hybrid-kernel-controller-inputs-v1` document supplies complete assigned-
flow admission capacities and directed planning-link metadata. The controller
does not mount processor profiles, and neither ConfigMap contains beliefs.
Beliefs remain private mutable controller state across slots.

`IBG_Hybrid/kernel_kubernetes_discovery.py` lists only Hybrid-labelled Pods
through the namespace-scoped Core API path. It converts no response into a
usable snapshot until every configured StatefulSet ordinal is present exactly
once with the required namespace, labels, name/ordinal identity, Running
phase, and Ready condition. Missing, duplicate, unexpected, foreign, unready,
mislabelled, or identity-mismatched responses fail before policy construction
or traffic.

The Hybrid service image boundary now has three import-safe ASGI entry points.
`kernel_processor_service.py` loads the minimal Hybrid runtime profile and
constructs the unchanged Exact processor runtime. `kernel_route_forwarder_service.py`
wraps the Phase 1 Hybrid continuation subclass around the unchanged Exact
forwarding application. `kernel_flow_generator.py` accepts only the versioned
Hybrid two-selected-stage request and delegates to the Phase 1 concurrent
executor; Exact's contiguous request is not a substitute.

`IBG_Hybrid/kernel_controller.py` supplies the controller-side HTTP port, the
Kernel traffic adapter, explicit seedless
`ibg-hybrid-kernel-observation-provenance-v1`, and a stateful controller
adapter. The existing Hybrid runner still owns flow order and all focal
placements. It calls the Kernel traffic adapter only after every focal action
is committed. The adapter builds one complete request, validates exactly two
selected observations and one measured pair per flow against the Ready
snapshot and final assigned loads, and rejects partial or mismatched telemetry.
Only after that complete result exists does the unchanged Hybrid runner call
the frozen Exact selected-only learner and metric helpers. Kernel physical
latency, observation-only jitter, exact convolved likelihood, and measured
pair values enter through selected telemetry; no skipped-stage record or
fabricated pure-simulation seed can enter learning or metrics. Configured
planning links remain policy/expected-utility inputs while measured pair cost
remains a separately named outcome input.

The manifests retain the Exact processor baseline of one worker on port 8081
with 50m/1 CPU and 128/768 MiB, and the forwarder baseline of two workers on
port 8080 with 25m/1 CPU and 128/256 MiB. The inherited local/downstream HTTP
client split and 30-second public keep-alive remain unchanged. The candidate
64/256 MiB processor reduction remains Infrastructure Phase 7 work.

## IBG-Hybrid Kernel Infrastructure Phase 3 image boundary

Implemented: 2026-08-08. No cluster, kind, deployment, image load, or live
HTTP operation was performed.

`deploy/hybrid-kubernetes/Dockerfile.service` now defines
`ibg-hybrid-testbed:kernel-service-v1` from an explicit source allowlist. It
contains the frozen Exact `datapath.py`, `latency_model.py`, private processor,
public forwarder, and profile parser together with only the Hybrid runtime-
profile, two-hop route, executor, forwarder, processor, and flow-generator
modules needed by the three Phase 2 ASGI paths. Its narrow image-local Hybrid
initializer prevents the repository convenience facade from eagerly loading
policy or runner code. The image-local budget module preserves exactly L=2
without copying the legacy pandas/SciPy-bearing `budgeted.py`. The service
dependency set is NumPy, FastAPI, HTTPX, and Uvicorn; controller, policy,
lookahead/MC orchestration, belief retention, reporting, MILP, SciPy/HiGHS,
OR-Tools, and pandas sources/dependencies are absent.

`deploy/hybrid-kubernetes/Dockerfile.controller` separately defines
`ibg-hybrid-testbed:kernel-controller-v1`. It contains the Hybrid policy,
deterministic lookahead, manual MC path, slot runner, selected-only learning
and metrics boundary, Ready discovery, controller configuration/adapter, and
Job entry point. Its dependency set is NumPy, FastAPI, and HTTPX; it has no
Uvicorn, pandas, SciPy/HiGHS, OR-Tools, or MILP dependency/source. The existing
Exact route wire models remain the shared schema dependency, but no Hybrid
processor, forwarder, or flow-generator ASGI entry point is copied and the
controller command runs only `IBG_Hybrid.kernel_controller_service`.

Two controller-image compatibility files contain only behavior-identical
copies of the frozen Exact `Replica` learning/utility methods, equilibrium and
Jain helpers, and `SLA_v`. This avoids importing the unrelated legacy CSV,
plotting, and truncated-normal surfaces while preserving the runner's existing
selected-only update, 0.8 belief retention, physical-only SLA, and metric
semantics. Functional comparison tests bind these lean copies to the frozen
Exact implementations. They are deployment-context files and do not modify
anything under `IBG/`.

Both image roots were materialized in temporary directories for silent,
RNG-neutral, file-clean import smokes and content inspection. The service
imports all three ASGI modules without loading policy, runner, controller,
pandas, SciPy, OR-Tools, or MILP modules. The controller imports policy,
manual-MC, learning, metrics, discovery, and adapter code without importing a
Hybrid service entry point, Uvicorn, pandas, SciPy, OR-Tools, or MILP. The
Phase 2 manifests remain unchanged, so one processor worker on 8081, two
forwarder workers on 8080, the split clients, 30-second public keep-alive,
probes, and 50m/1 CPU 128/768 MiB processor plus 25m/1 CPU 128/256 MiB
forwarder resources remain authoritative.

A local Docker build was attempted with the existing base image,
`--pull=false`, and `--network=none`. Docker accepted the service definition
and context, then stopped at dependency installation because no NumPy wheel
was cached. New network access was not requested, the controller build was not
attempted, and no completed Hybrid image was claimed. Image construction and
in-image inspection therefore remain an explicit prerequisite before the
separately approved Infrastructure Phase 4 live gate.

### Infrastructure Phase 3 image validation completed

Completed: 2026-08-08. The two Phase 0 image identities now resolve to built,
locally inspected images. The service image is
`sha256:01b9795bea127235c7537677379fe42c67e076e07a69c52fece1c19e19651737`
(78,954,015 bytes); the controller image is
`sha256:8726906596820d56ae4ec17fd03efe583e1b84cf030f79de5fb87f905a7448c3`
(78,492,804 bytes). Both retain numeric user `10001:10001`. The service image
exposes only 8080/8081 and retains the Hybrid flow-generator Uvicorn command;
the controller exposes no port and retains only the controller Job command.

After an online controller-wheel download timed out, the user downloaded the
resolved wheels individually into `/tmp/ibg-hybrid-controller-wheels`. The
controller was then built with `--network=none` using a temporary BuildKit
read-only bind mount. The wheel directory was neither copied into the source
tree nor retained as an image layer. The committed controller Dockerfile now
uses a 300-second pip read timeout for future ordinary builds; this affects
only dependency acquisition.

Read-only, network-disabled, non-service container smokes imported every
service entry module and the controller/policy/manual-MC/learning stack. Both
were silent, RNG-neutral, and file-clean. In-image package/source inspection
proved Uvicorn is service-only; pandas, SciPy/HiGHS, OR-Tools, and MILP are in
neither image; controller/policy/runner code is absent from the service; and
Hybrid processor, forwarder, flow-generator, and runtime-profile modules are
absent from the controller. No HTTP server, Kubernetes API, cluster, kind
load, deployment, or live traffic was started. Infrastructure Phase 3 is now
fully complete; Infrastructure Phase 4 remains separately authorized work.

## IBG-Hybrid Kernel Infrastructure Phase 4 small live boundary

Completed: 2026-08-08.

The first live gate is a sibling Kustomize overlay at
`deploy/hybrid-kubernetes-phase4-small/`. It retains the Phase 2 Hybrid-owned
namespace and long-running base, but narrows it to two flows, three stages,
and exactly one ordinal per stage. The base still excludes the controller
Job. The Phase 4 Job remains a separately applied object, so the controller
cannot start discovery, placement, or traffic until all three replica Pods and
the flow generator have become Ready.

`IBG_Hybrid.kernel_phase4_validation` is the controller-image live-gate entry
point. It runs two stateful controller slots through the completed Phase 2
adapter, emits one compact JSON evidence object per slot, and validates exact
two-selected-stage telemetry, skipped-stage absence, seedless Kernel
provenance, separated physical/observation jitter, and belief retention. It
then replays the returned Kernel observations and measured pairs through the
existing pure Hybrid slot boundary without issuing another HTTP request. The
replay must preserve placement, final assigned loads, beliefs, and metrics
(excluding wall-clock elapsed time).

The live topology exercised both required route shapes in the first slot:
flow 1 selected stages 1 and 3, while flow 2 began at stage 2 and continued to
stage 3. Each slot produced four selected observations and two measured pairs,
equivalent to exactly two observations and one pair for each flow. Planning
links remained controller input at 0 ms for the selected pairs; measured pair
latencies remained separate observations. Physical processing totals remained
the only realized-utility and 110-ms SLA input, with zero physical-only SLA
violations in both slots.

The existing kind cluster was restarted, not recreated. The inspected Phase 3
service image and the controller image containing the validation entry point
were loaded on all three existing nodes. The deployed boundary has four
long-running Pods plus one completed controller Job. Exact Ready ordinal
coverage was established before the Job was applied. After both slots, every
long-running Pod retained its original UID, remained Ready, and had zero
restarts; no OOM kill or eviction occurred. No rollout batching, profile
scaling, resource change, netem, diagnostic tracing, calibration, replay
traffic, or larger topology was introduced.

## Hybrid kind-cluster isolation correction

Corrected: 2026-08-08.

The Phase 4 live topology must no longer reuse the historical `ibg` kind
cluster. That cluster retains unrelated Exact/MILP Kubernetes state, so
restarting its node containers also restarts those workloads. The supported
Hybrid live-gate boundary is now the temporary, single-control-plane
`ibg-hybrid` cluster defined by
`deploy/hybrid-kubernetes-phase4-small/kind-config.yaml` and operated through
`scripts/run_hybrid_kernel_phase4.py`. Its only accepted kubectl context is
`kind-ibg-hybrid`.

This single-control-plane configuration is the completed small-gate boundary,
not the intended workload topology. The next Hybrid infrastructure correction
is one control-plane node plus one worker node. Hybrid replica StatefulSets,
the flow generator, and the finite controller Job must run on that worker;
the control-plane remains reserved for Kubernetes management services. The
two kind nodes remain containers on one physical host, so this separates
management and workloads but provides no same-worker versus cross-worker
workload-path comparison.

The runner is fail-closed at four boundaries. It requires the pinned kind node
image and both Hybrid images to exist locally before cluster creation; it
accepts only the exact `ibg-hybrid-control-plane` node identity; it rejects the
`ibg-testbed` and `milp-testbed` namespaces plus every workload Pod outside
the Hybrid/system namespaces; and it verifies the exact three Ready stage Pods
plus one Ready flow generator before applying the controller Job. It never
starts, targets, scales, or deletes the historical `ibg` cluster or its frozen
baseline resources.

`run-small` creates only the dedicated cluster, loads only the two Hybrid
images, executes the bounded Phase 4 gate, prints the completed Job evidence,
and deletes the dedicated cluster in a `finally` path by default. An explicit
`--keep-cluster` is required to retain its memory-consuming state. A failed
post-creation step follows the same default cleanup path. `preflight` and
`cleanup` are likewise bound to the dedicated cluster name and context.

## Hybrid persistent-cluster lifecycle correction

Corrected: 2026-08-08. This latest section supersedes the preceding temporary-
cluster deletion policy while retaining its dedicated-cluster isolation rule.

The supported Hybrid runner now follows the Exact launcher lifecycle without
sharing Exact's cluster. `run-small` checks for `ibg-hybrid`; when absent it
creates the pinned one-node cluster, and when present it validates the exact
node, namespace, and workload inventory before reuse. A normal Phase 4 run
requires both local Hybrid images, loads them into the dedicated node, applies
the small long-running boundary, explicitly restarts those service workloads,
waits for complete Ready coverage, and deletes/recreates only the finite
controller Job. Successful completion or failure leaves the dedicated cluster,
node image cache, and Hybrid workloads intact.

Cluster deletion is available only through the explicit `cleanup` action and
can target only `ibg-hybrid`. The runner has no automatic deletion path and no
`--keep-cluster` inversion of the normal lifecycle.

Exact-style `--skip-build` is intentionally assigned to Infrastructure Phase
5 rather than pulled into the completed Phase 4 gate. It must skip both Hybrid
Docker builds, both kind image loads, and the otherwise explicit service
rollout restart while still reconciling manifests/counts, waiting for Ready
coverage, and creating a fresh controller Job. Infrastructure Phase 6 then
extends that reuse boundary to append-only profiles and proves that existing
Pod UIDs/processes are unchanged while only missing ordinals are created.

## Persistent Phase 4 lifecycle live verification

Verified: 2026-08-08.

The dedicated one-control-plane `ibg-hybrid` architecture has now completed
two consecutive normal Phase 4 executions. Both used Docker container
`d6b8e934dfd9` and Kubernetes node UID
`11d63e26-dd1a-448d-9a14-a99c1667727a`; the second invocation discovered and
reused that node instead of creating another cluster. Its normal pre-Phase-5
path reloaded the two local Hybrid images, reapplied unchanged resources,
explicitly restarted only the three Hybrid StatefulSets and flow generator,
then deleted/recreated only the completed controller Job.

The historical three-node `ibg` cluster remained stopped throughout. The
dedicated cluster contains only Kubernetes system namespaces plus
`ibg-hybrid-testbed`; no Exact or MILP namespace/workload appeared. After the
second run, the three two-container stage Pods and flow-generator Pod were
Ready with zero restarts, and the replacement controller Job had succeeded.
The dedicated node remains running by design. This validates persistent node
reuse only; Phase 5 `--skip-build` and its no-service-restart/Pod-UID guarantee
were not exercised.

The second normal invocation also exposed the correct future image-presence
boundary. `kind load docker-image` reported both unqualified host tags as not
present and re-imported them, while node `crictl images` showed the normalized
runtime tags `docker.io/library/ibg-hybrid-testbed:kernel-service-v1` and
`...:kernel-controller-v1` with platform image IDs `bb6c47d791a1f` and
`eda04655da857`. Phase 5 `--skip-build` must inspect normalized node-runtime
tags/platform IDs directly; kind's host-manifest comparison is not an absence
test for these multi-platform images.

## Planned Infrastructure Phase 7.5 manual MC Kernel boundary

Planned: 2026-08-08. This phase is explicitly ordered after Hybrid-specific
resource evidence in Phase 7 and before incremental scale validation in Phase
8. It is not implemented or authorized by this planning record.

The existing controller image already owns deterministic lookahead, the frozen
top-five-root MC selector, `S=50`, `D_MC=10`, the pure greedy tail, selected-
only learning, metrics, and bounded rollout-worker support. Phase 7.5 adds only
the Kubernetes controller selection/lifecycle boundary: an absent policy flag
continues to mean deterministic lookahead, while explicit `--policy mc` plus
`--mc-workers N` selects MC for that finite controller Job. No automatic
entropy/contention/priority trigger is introduced.

For each Kernel MC slot, the controller creates one bounded local process pool,
uses it for independent shortlisted-root rollout groups across all sequential
real focal decisions, and closes it before any flow-generator HTTP request.
All focal actions and final assigned loads must be committed before exactly one
complete request. The unchanged service image then executes the selected
two-hop routes, and the existing complete-telemetry boundary applies learning
only after every selected observation and measured pair is present. Hidden
processor state never enters MC planning.

The live gate reuses the topology and service resources accepted by Phase 7;
it is not a scale phase. Under Phase 5 `--skip-build`, all existing service Pod
UIDs must remain unchanged. Controller evidence separately records CPU, RSS,
worker count, deadline, completion/failure, and pure-versus-Kernel decision
parity. Service workers, ports, keep-alive, resources, physical/observation
jitter, planning/measured latency, utility/SLA, and route semantics remain
frozen.

## IBG-Hybrid Kernel Infrastructure Phase 5 boundary

Completed: 2026-08-09.

`IBG_Hybrid/kernel_rollout.py` is the import-safe rollout/count boundary. It
accepts only the exact three Hybrid-owned StatefulSets, validates namespace,
name, required labels, Service identity, selector, Pod-template labels, and one
consistent positive desired count, and rejects missing, partial, duplicate,
foreign, mislabelled, or inconsistent inventories. Its deterministic plan
never shrinks: an equal requested count has no batches, while a larger valid
target adds only the zero-based ordinals missing from each bounded target and
ends exactly at the requested count. At every target, all three StatefulSets
receive the same desired count before exact Running/Ready ordinal coverage is
accepted. The module imports no Hybrid placement, policy, learning, traffic,
or metric implementation.

The persistent Hybrid runner now supports `run-small --skip-build --replica N
--rollout-batch-size B`. The normal path uses only the locally present Python
base and invokes both Hybrid Dockerfiles with `--pull=false --network=none`,
loads both images into `ibg-hybrid`, reconciles resources without first
shrinking an existing count, explicitly restarts only the Hybrid service
workloads, waits for every bounded target, and replaces only the controller
Job. An unavailable offline dependency/cache fails the build; the runner has
no download or host-package fallback.

The `--skip-build` path requires the already-existing dedicated cluster and
skips both Docker builds, the kind image load, and the explicit service
restart. It still validates isolation and exact StatefulSet ownership,
reconciles the count-safe Kustomize projection, waits for exact Ready coverage,
and replaces the finite controller Job. Before reconciliation it exports each
local image to a temporary offline OCI archive, resolves the unique
`linux/amd64` config digest beneath the local multi-platform index, and matches
that full digest to the normalized `docker.io/library/ibg-hybrid-testbed` tag
reported by `crictl` on every accepted Hybrid node. Temporary archives are
removed automatically. Thus the check compares the local selected platform
identity with the node platform identity and never relies on `kind load`
output or hard-coded historical IDs.

The runner snapshots every existing serving Pod UID and per-container restart
count before a skip-build reconciliation and fails if any existing process
identity changes afterward. Complete StatefulSet/Ready validation always
precedes controller Job deletion and creation. The static Phase 4 profile must
already cover the exact requested replica count; requesting a new ordinal with
the current one-replica profile fails before reconciliation because append-only
profile creation remains Phase 6.

The Phase 5 live gate reused Docker node `d6b8e934dfd9` and Kubernetes node UID
`11d63e26-dd1a-448d-9a14-a99c1667727a` at the unchanged one-replica topology.
The three stage Pod UIDs (`df6d584d...`, `760f9475...`, `b0dd1dc9...`) and flow
generator UID (`f9b97cb9...`) remained identical with zero restarts. Only the
controller Job was replaced. Both slots retained the `(1,3)` noncontiguous and
`(2,3)` stage-2-first routes, exactly two observations and one measured pair
per flow, skipped-stage absence, separated jitter, belief retention, and
pure/Kernel parity. The shared `ibg` nodes remained stopped and the dedicated
cluster remains running. No Phase 6 profile mutation, Phase 7 resource change,
Phase 7.5 Kubernetes MC wiring, or Phase 8 scale work was introduced.

## IBG-Hybrid Kernel Infrastructure Phase 6 boundary

Completed: 2026-08-09.

`deploy/hybrid-kubernetes-phase6-3x3x2/` is the append-only profile and
deployment projection for the first approved three-flow, three-stage,
two-replica Hybrid topology. It keeps the Phase 4/5 one-replica overlay as a
reproducible historical boundary. The Phase 6 runtime document preserves each
ordinal-0 processor identity, hidden state, and observation seed and adds only
replica 2 for stages 1--3. Its controller document preserves the three old
admission capacities and three old directed links, adds the other three
admission entries and nine required directed links, and remains free of hidden
state, observation seeds, and beliefs.

`IBG_Hybrid/kernel_profile_expansion.py` is a policy-free fail-before-write
contract. It requires exact document/nested fields and complete canonical
runtime, admission, and planning-link coverage; compares every deployed entry
with the proposed document; rejects identity/state/seed, capacity, or link
drift plus missing, duplicate, unexpected, partial, or malformed additions;
and permits only complete target additions. Admission capacity remains a
controller input, configured planning links remain pre-placement inputs, and
measured pairs remain post-traffic outcomes.

The persistent runner selects the Phase 6 overlay only for `--replica 2` and
requires `--skip-build`. Before either ConfigMap changes, it reads both live
documents and validates the append-only transition. It then performs a
server-side dry-run of the count-preserving projection and requires canonical
equality between every live and proposed StatefulSet Pod template. Only after
those checks does it reconcile the two fixed-name ConfigMaps, verify their
exact target contents, wait at the existing count, and use the Phase 5 bounded
rollout to add ordinal 1 at all stages. Exact two-ordinal Ready coverage
precedes the fresh controller Job.

The runtime profile is mounted as a projected ConfigMap directory without a
name-suffix hash, checksum annotation, or `subPath`. Kubelet may refresh the
projected file after reconciliation, but each private processor loads and
validates its own immutable identity/profile once when its application process
starts. Existing processes therefore retain their already-loaded state and
seed; only newly started ordinal-1 processors read the new entries. A change to
an existing profile remains an explicit future refresh operation and is not
implemented by this boundary.

The live gate reused Docker node `d6b8e934dfd9` and Kubernetes node UID
`11d63e26-dd1a-448d-9a14-a99c1667727a`. Existing UIDs remained
`df6d584d-35cd-4de9-b53e-3f8b071586c2`,
`760f9475-b6f3-412f-9279-fdcd3f53ece4`,
`b0dd1dc9-59d8-4580-bbe5-a3fd7c55814c`, and
`f9b97cb9-031a-4c72-b298-2c1a85cb8562`, all with unchanged zero restart
counts. Only `hybrid-stage-1-1` (`ade01b78-9f31-4795-a5c6-a39cf00291c1`),
`hybrid-stage-2-1` (`db51c381-0491-4a88-ac61-a4b396f0e8e1`), and
`hybrid-stage-3-1` (`c40c5d06-78fd-4635-bd61-32d44223386e`) were added, also
with zero restarts.

The two-slot 3x3x2 Job completed after all six replicas were Ready. Each slot
returned six selected observations and three measured pairs, with one complete
request after all placements, skipped-stage absence, final-load correlation,
selected-only learning, belief retention, seedless Kernel provenance,
physical/observation separation, planning/measured separation, and pure/Kernel
replay parity. Slot 1 exercised `(1,3)`, `(2,3)`, and `(1,2)` and produced one
assigned flow on each replica. No image build/load/download, service restart,
node creation, Phase 7 resource change, Phase 7.5 MC wiring, or Phase 8 scale
work occurred.

### Infrastructure Phase 6 explicit topology CLI correction

Corrected: 2026-08-09.

The persistent Hybrid runner now exposes the same dimension vocabulary as the
Exact and MILP launchers: `--flow`/`--flows`, `--stage`/`--stages`, and
`--replica`/`--replicas`. The three values select a complete versioned profile
boundary; they do not generate profiles or authorize arbitrary dimensions.
The only accepted tuples are the historical `2x3x1` boundary and the accepted
Phase 6 `3x3x2` boundary. Omitting flow and stage remains backward-compatible
by inferring them from the uniquely approved replica profile.

Topology resolution and complete local profile validation occur before the
first kind, Docker, or Kubernetes command. A mismatched tuple, a stage count
other than the frozen three, or a larger unapproved scale therefore fails
without contacting or changing the cluster. For an accepted tuple, the runner
prints the resolved flow/stage/replica topology before continuing through the
unchanged image, profile, rollout, readiness, process-preservation, and Job
lifecycle. No new topology, profile mutation, or live gate was introduced by
this interface correction.

## IBG-Hybrid Kernel Infrastructure Phase 7 resource boundary

Completed: 2026-08-09.

`deploy/hybrid-kubernetes-phase7-3x3x2/` preserves the accepted Phase 6
3-flow, 3-stage, 2-replica topology and its controller inputs while providing
a five-slot finite Phase 7 controller Job. The sibling
`deploy/hybrid-kubernetes-phase7-3x3x2-candidate/` changes only each private
processor's memory request/limit from 128Mi/768Mi to 64Mi/256Mi. Processor CPU
remains 50m/1 CPU; public forwarders remain two workers at 25m/1 CPU and
128Mi/256Mi; flow-generator/controller declarations, ports, probes, images,
client split, and 30-second public keep-alive remain unchanged.

`IBG_Hybrid/kernel_resource_evidence.py` is a policy-free resource boundary.
It validates exact three-StatefulSet ownership, recognizes only the baseline
and candidate processor profiles, compares the complete StatefulSet spec, and
allows no difference except the two private-processor memory values. Replica
count, forwarder resources, commands, probes, labels, selectors, profiles,
and every other Pod-template field must remain identical. A deliberate
processor resource change is therefore a controlled StatefulSet rollout and
starts a new stage-Pod UID lineage; unchanged resource reruns still preserve
all serving UIDs and restart counts.

`scripts/run_hybrid_kernel_phase7.py` wraps the persistent runner at the exact
3x3x2 `--skip-build` boundary. It takes per-container CRI working-set/RSS
samples, cgroup-v2 CPU/memory/event snapshots before and after traffic,
controller cgroup plus `/proc` RSS samples while the finite Job runs, Pod and
event health, exact Ready coverage, node capacity/pressure, and node/Pod
lineage. Metricless retained containerd entries are ignored only before the
collector requires the exact live set of six processors, six forwarders, and
one flow generator. Startup probe events are separated from post-Ready probe
events. Candidate acceptance requires a processor peak no greater than half
the 256Mi limit, no memory event, bounded CPU throttling, no serving restart,
no fatal Kubernetes event or post-Ready probe failure, no node pressure,
complete Ready coverage, and at least half of the controller deadline
remaining.

The baseline five-slot gate measured a 48,599,040-byte processor cgroup peak
and 44,486,656-byte maximum working set; processor throttling and memory events
were zero. The candidate five-slot gate measured a 46,583,808-byte peak and
42,487,808-byte maximum working set, leaving 221,851,648 bytes below the
256Mi limit; processor throttling, memory events, restarts, and post-Ready
probe failures were zero. The candidate is accepted and remains deployed.
All candidate Pods became Ready within five to seven seconds of creation; the
six-Pod creation-to-final-Ready window was 16 seconds. Expected startup-only
connection-refused/503 readiness events cleared before traffic.

The candidate gate retained Docker node `d6b8e934dfd9`, Kubernetes node UID
`11d63e26-dd1a-448d-9a14-a99c1667727a`, and flow-generator UID
`f9b97cb9-031a-4c72-b298-2c1a85cb8562`. It deliberately replaced all six
stage Pods and then preserved their new zero-restart UIDs through repeated
candidate runs. Five slots each produced six observations and three measured
pairs after complete placement, retained beliefs, exercised noncontiguous and
stage-2-first routes, excluded skipped stages, preserved jitter/link
separation, and passed pure/Kernel parity. No image build/load/download,
topology scale, MC wiring, or shared-cluster operation occurred.

## IBG-Hybrid Kernel Infrastructure Phase 7.5 controller boundary

Completed: 2026-08-09.

`IBG_Hybrid/kernel_controller_cli.py` is the finite controller policy entry
point. With no policy argument it resolves to deterministic lookahead;
`--policy mc` is accepted only with an explicit positive `--mc-workers` count
bounded at two, and `--mc-workers` is rejected for lookahead. The Kubernetes
controller adapter now passes that count to the existing pure slot runner. It
does not copy or alter MC mathematics.

The frozen runner already owns the required placement lifecycle. In MC mode it
creates one `ProcessPoolExecutor` for a slot, reuses the same executor across
all three sequential focal placements, and exits the executor context before
the traffic adapter can submit the one complete flow-generator request.
Executor mapping preserves canonical root order; worker exceptions or missing
root outcomes fail the slot. Traffic, complete telemetry validation, selected-
only learning, belief retention, and metrics remain outside the worker pool.

`deploy/hybrid-kubernetes-phase7.5-3x3x2/` reuses the accepted Phase 7
candidate service overlay and keeps its long-running Kustomize boundary free
of Jobs. Its separate finite Job mounts a Hybrid-owned controller-source
ConfigMap containing only the updated controller adapter, parity validator,
and CLI. This no-build bridge is required because Phase 7.5 explicitly reuses
the already-loaded Phase 3 controller image; it changes no service image,
profile, StatefulSet template, processor, forwarder, flow generator, or
controller resource declaration. Future controller image builds include the
CLI directly through the updated controller Dockerfile.

`IBG_Hybrid/kernel_mc_evidence.py` and
`scripts/run_hybrid_kernel_phase75.py` validate exact 3x3x2 MC slot evidence,
one-versus-multiple-worker decision equality, direct controller child-process
counts, post-slot pool cleanup, controller cgroup/process resources, deadline,
events, pressure, and serving/node lineage. The live one-worker and two-worker
Jobs each completed two slots. Every slot placed all flows before one request,
returned six selected observations and three measured pairs, excluded skipped
stages, retained beliefs, preserved the separated jitter/link contracts, and
passed same-policy pure/Kernel replay parity. Both worker counts produced the
same placements and final loads.

The live gate preserved Docker node `d6b8e934dfd9`, Kubernetes node UID
`11d63e26-dd1a-448d-9a14-a99c1667727a`, all six Phase 7 stage-Pod UIDs, and
flow-generator UID `f9b97cb9-031a-4c72-b298-2c1a85cb8562`, with every serving
restart count still zero. Only the finite controller Job was replaced between
worker-count runs. No image build/load/download, service rollout, topology
change, shared-cluster operation, or Phase 8 scale work occurred.

## IBG-Hybrid Kernel Infrastructure Phase 8 Gate 1 boundary

Completed: 2026-08-09.

The first incremental scale boundary is exactly 4 flows x 3 stages x 2
replicas and remains deterministic-lookahead only. The persistent runner now
recognizes exactly `2x3x1`, `3x3x2`, and `4x3x2`; the new tuple requires
explicit `--skip-build --flow 4 --stage 3 --replica 2`, while every other
tuple still fails before cluster contact. Omitted flow/stage values at two
replicas retain the historical `3x3x2` inference.

`deploy/hybrid-kubernetes-phase8-gate1-4x3x2/` layers only versioned runtime
and controller ConfigMaps over the accepted Phase 7 candidate service
resources. All six runtime identity/hidden-state/seed entries, all six
admission capacities, and all twelve directed planning links are identical to
Phase 6; only `num_flows` and the source identity advance. The long-running
Kustomize boundary still contains no Job. Its separate two-slot finite Job
reuses the Phase 7.5 controller-only source ConfigMap, defaults to lookahead,
mounts no runtime profile, and retains controller requests 100m CPU / 256Mi
and limits 2 CPU / 1Gi.

`validate_flow_only_profile_expansion` parses complete deployed and proposed
documents before mutation and requires the exact approved source/target
configurations and identities. It rejects any runtime identity/state/seed,
admission, planning-link, completeness, stage, replica, or budget drift. A
server-side dry run must then reproduce every existing StatefulSet Pod
template byte-for-byte. The equal two-replica rollout plan contains no batch,
so ConfigMap reconciliation creates no ordinal, scale command, or service
rollout; the existing process snapshot enforces unchanged serving Pod UIDs
and restart counts around the finite Job.

`IBG_Hybrid/kernel_phase8_evidence.py` validates exact four-flow lookahead
semantics, admission-safe final loads, final assigned-load propagation, route
coverage, eight selected observations/four measured pairs, belief retention,
seedless provenance, jitter/link separation, and pure/Kernel replay parity.
`scripts/run_hybrid_kernel_phase8.py` adds bounded per-container CRI/cgroup,
controller RSS/deadline, event, pressure, Ready, and lineage evidence without
entering placement mathematics.

The live two-slot gate preserved Docker node `d6b8e934dfd9`, Kubernetes node
UID `11d63e26-dd1a-448d-9a14-a99c1667727a`, all six stage-Pod UIDs, and flow-
generator UID `f9b97cb9-031a-4c72-b298-2c1a85cb8562`, with all serving
restart counts zero. Each slot completed all four placements before one
request and produced eight observations and four pairs. The first slot
included `(1,3)` and `(2,3)` routes; both slots passed skipped-stage absence,
selected-only learning, belief retention, final-load propagation, seedless
provenance, separated latency/jitter boundaries, zero physical-only SLA
violations, and pure/Kernel lookahead parity.

Processor/forwarder/flow-generator maximum cgroup peaks were
46,899,200/129,708,032/53,149,696 bytes and CPU deltas were
734,676/1,344,907/125,690 usec, with zero serving throttling or memory events.
The controller used 1,811,503 CPU usec, 79,981 throttled usec, a 51,302,400-
byte cgroup peak, and 69,079,040-byte maximum process RSS; it completed in 22
seconds with 578 seconds of deadline margin. There were no serving restarts,
fatal events, post-Ready probe failures, or node pressure. No image operation,
service resource change, MC-at-scale run, later Phase 8 topology, or shared-
cluster operation occurred.

## IBG-Hybrid dynamic-topology launcher boundary

Completed: 2026-08-09.

The Phase 8 Gate 1 tuple table was an incremental validation mechanism, not
the final experiment interface. `scripts/run_hybrid_kernel_phase4.py` now
accepts any positive flow count and replica count, keeps the frozen stage
count exactly three, and resolves those dimensions before any cluster
command. The singular and plural flags are retained. `--skip-build` controls
only image build/load/restart behavior; it no longer selects an approved
topology. Replica shrink remains fail-closed.

`IBG_Hybrid/kernel_profile_expansion.py` owns deterministic dimension-driven
generation. It preserves every canonical existing runtime identity, hidden
state, and observation seed. Later replicas cycle the accepted hidden-state
templates within their stage and receive an identity-derived Cantor-pair seed
in a reserved one-billion-plus range. Repeating a dimension request is byte
stable, and extending a replica count is append-only. Runtime ConfigMaps still
contain only stage, replica, hidden state, and observation seed; beliefs stay
controller-private and hidden state never enters controller inputs.

Every generated replica receives `ceil(num_flows / num_replicas)` admission
capacity, giving each stage aggregate capacity for all flows. Planning inputs
contain the complete directed increasing-stage cross-product: three stage
pairs times `R^2` replica pairs. Existing link values are copied exactly; new
links use the canonical versioned value for their stage pair. At `10x3x5`
this produces exactly 15 runtime profiles, 15 admission entries of capacity
two, and 75 planning links. Measured pairs remain post-traffic outcomes.

Before a ConfigMap write, the runner reads the deployed documents and requires
them to equal the versioned rule for their deployed dimensions. It then
requires the proposed documents to equal the generated target and preserves
all old runtime and link entries; admission changes are allowed only when the
dimension formula requires them. A server-side dry run must preserve every
StatefulSet Pod template. Fixed ConfigMap names have no profile hash, so
existing processors retain their startup-loaded identity while new ordinal
Pods consume the expanded document.

The existing Phase 5 rollout planner applies one count to all three
StatefulSets and waits for exact Ready ordinal coverage at each batch before
the finite dynamic controller Job. The accepted `2 -> 5` rollout with batch
size two used targets four and five, creating only ordinals 2, 3, and 4. The
generic Job remains outside every long-running Kustomize boundary and runs
two deterministic-lookahead slots after final readiness. Completed dynamic
Job Pods are recognized as Hybrid-owned during the next isolation preflight,
then the Job alone is deleted and recreated.

The live `10x3x5` gate preserved the dedicated node, all ordinal-0/1 Pods, and
the flow generator; every serving restart count remained zero. Each of two
slots completed ten placements before one request and returned twenty selected
observations and ten measured pairs, with noncontiguous and stage-2-first
routes, skipped-stage absence, selected-only learning, belief retention,
seedless provenance, separated jitter/link boundaries, and pure/Kernel
lookahead parity. A second unchanged `--skip-build` run preserved all fifteen
stage Pods and the flow generator and replaced only the finite Job.

The one-node resource preflight admitted 2,225m CPU of 4,000m and
3,726,639,104 of 16,720,244,736 allocatable bytes. Final processor,
forwarder, and flow-generator maximum working sets were 42,639,360,
126,119,936, and 49,430,528 bytes; cgroup peaks were 46,899,200,
130,232,320, and 53,907,456 bytes, with no memory events. The controller
completed in 16 seconds with 584 seconds of deadline margin. There were no
serving restarts, OOM/eviction/fatal events, post-Ready probe failures, or
node pressure. No image build/load/pull/download, worker-node addition,
resource change, MC-at-scale execution, or shared-cluster operation occurred.

## IBG-Hybrid completed-slot console presentation

Completed: 2026-08-09.

`IBG_Hybrid/console_output.py` is the presentation-only boundary for both
lookahead and explicitly selected MC slots. After a complete `HybridSlotResult`
exists, it renders the iteration/slot identity, active outcome mode, per-flow
physical/pair/raw/outcome latency, predicted/realized/physical/raw utility,
SLA count, Jain fairness, elapsed time, and equilibrium. Latency is shown in
milliseconds, utility and fairness use six decimals, and time uses three
decimals. The formatter omits flow order, placements, observations, learning
signals, beliefs/deltas, and storage messages.

Hybrid metrics already sum the two selected stage-utility components into
`aggregate_expected_utility_per_flow` inside `_compute_metrics`; presentation
reads that completed scalar rather than recomputing policy mathematics. The
active Hybrid outcome contract remains `physical-only-v1`, so outcome latency
equals selected physical processing latency and realized utility equals the
physical utility view. Pair latency and its raw end-to-end reference remain
separately visible. No latency, utility, SLA, fairness, learning, equilibrium,
or persistence calculation changed.

The Kernel validation loop now invokes an optional completion callback only
after one slot and all of its semantic checks succeed, and before the next slot
starts. Controller entry points use that callback to flush the human block
immediately. Complete machine evidence remains a prefixed controller-log line.
The host runner follows the finite Job log while it is running, displays only
human lines, privately collects and normalizes the evidence lines for existing
validators, then still waits for Job completion and applies the unchanged
process-preservation checks. It no longer dumps detailed evidence JSON after
the Job finishes.

The controller image includes the formatter. The existing controller-only
no-build source ConfigMap also carries and mounts that single module for the
Phase 7.5, Phase 8, and dynamic Jobs; service Pods do not mount or import it.

## IBG-Hybrid production experiment lifecycle

Completed: 2026-08-09.

The dynamic launcher now exposes `run` as the normal experiment command and
retains `run-small` only as the historical bounded infrastructure gate. `run`
requires explicit positive flow, stage, replica, and maximum-iteration values;
stages remain exactly three. Dimension-driven profiles, drift checks, bounded
rollout, Ready coverage, `--skip-build`, and serving-process preservation are
shared with the completed dynamic-topology path and are not duplicated in the
experiment controller.

`run_kernel_experiment` is separate from `run_small_live_gate`. It invokes the
stateful controller adapter once per sequential slot, verifies belief continuity,
emits the completed human block and prefixed machine evidence before the next
slot, then checks the existing `HybridSlotMetrics.equilibrium` result. It returns
immediately on equilibrium or after exactly the configured maximum, with a final
reached/not-reached status. The adapter still owns complete Ready discovery,
all placement before traffic, one complete flow-generator request, telemetry
validation before learning, and controller-private belief retention.

The host renders the dynamic controller Job with
`HYBRID_CONTROLLER_LIFECYCLE=experiment` and the requested `MAX_ITERATIONS`.
The dynamic Job template no longer embeds a two-slot limit. Historical gate
templates retain their bounded counts. The production rendering removes the
historical 600-second gate deadline because the positive iteration bound itself
makes the Job finite and a gate deadline could truncate a valid long experiment.
Host log following and hidden prefixed-evidence collection remain unchanged.

The completed-slot formatter now omits the entire human `Latency:` section.
Physical processing, measured-pair, raw end-to-end, and outcome latency remain
unchanged in `HybridSlotResult` and prefixed evidence; only their console
projection was removed. The human block retains outcome mode, the four utility
views, SLA count, fairness, elapsed time, and equilibrium.

Kubernetes MC remains manual-only and is still limited to the accepted `3x3x2`
candidate-resource boundary with one or two workers. The general dynamic `run`
interface does not authorize large-topology MC or automatic activation.

## IBG-Hybrid intentional replica scale-down boundary

Completed locally: 2026-08-11. Live acceptance remains separately gated.

The Hybrid rollout contract is now direction-aware. Equal replica counts remain
a no-op, scale-up retains bounded missing-ordinal batches, and an explicit lower
target produces one deliberate all-stage batch. The plan records added and
removed zero-based ordinals separately; an `8 -> 5` transition removes only
ordinals `5`, `6`, and `7` from each StatefulSet. Exact three-stage ownership,
one consistent deployed count, and exact Ready ordinal coverage remain
prerequisites.

Dynamic profile validation independently regenerates both the deployed and
target runtime/controller documents from the versioned Hybrid rule before any
write. It returns explicit retained, added, changed, and removed runtime,
admission, and planning-link sets. Retained runtime identity, hidden state, and
observation seed and retained planning links must be identical. Only profiles
and admission entries above the target may disappear; every removed planning
link must have a removed endpoint. A retained admission value may change only
to the target `ceil(flows / replicas)` value. Beliefs remain controller-private.

Scale-down deliberately reverses the scale-up ConfigMap order. The runner first
server-dry-runs the exact lower projection and proves StatefulSet Pod templates
unchanged while leaving the complete deployed ConfigMaps intact. It then scales
all three StatefulSets to the one lower target, waits for exact retained Ready
coverage and absence of higher ordinals, and only then reconciles the reduced
runtime/controller ConfigMaps. It revalidates the exact documents, unchanged
Pod templates, and Ready coverage before replacing the finite controller Job.
This prevents a terminating high-ordinal processor from restarting after its
profile has already been removed.

`--skip-build` process evidence compares the retained subset: every retained
stage Pod and the flow generator must keep the same UID and restart counts, and
only the declared higher ordinals may disappear. Scale-down resource preflight
uses zero added Pods and conservatively validates the existing serving envelope
plus the finite controller; it never fabricates negative resource demand.

The read-only MILP reference supplied the useful direct-lower-target rollout
concept. Its current existing-profile validator was not copied because it loops
over all pre-scale identities and can misclassify intentional high-ordinal
removal as drift. Hybrid validates complete deterministic source and target
documents and uses the safe scale-before-profile-removal ordering instead.

Local validation passes 37 focused scale-down/dynamic/production tests, 105
Infrastructure Phase 5--8 plus lifecycle tests, all 252 Hybrid tests (split
into memory-bounded processes), 119 relevant frozen Exact tests, and 50 frozen
MILP Phase 5 rollout/profile tests. Compilation, seven Kustomize renders, and
seven controller Job parses also pass without contacting a live cluster.

## IBG-Hybrid initial/final belief presentation

Completed locally: 2026-08-11.

The production `run` lifecycle now prints exactly two human belief snapshots:
`Initial replica state` immediately before the first controller slot and
`Final replica state` after the equilibrium reached/not-reached status. Both
lookahead and explicit MC use this same lifecycle. The table follows Exact's
sorted, aligned `Stage  Replica  Belief` presentation and formats each four-state
vector in brackets to three decimals. Exact's additional hidden state and
legacy capacity/delay/gamma columns are deliberately excluded because the
Hybrid controller must not expose processor true state.

Completed per-slot metric blocks remain belief-free, and prefixed machine
evidence, belief retention, learning, equilibrium, traffic, metrics, and
latency behavior are unchanged. Historical `run-small` validation output is
unchanged.

Validation passes 70 focused lifecycle/console/service-isolation tests, all 253
Hybrid tests in memory-bounded groups, and 119 relevant frozen Exact tests.
Compilation and all seven retained Kustomize renders pass.

## IBG-Hybrid reproducible offline image-build boundary

Implemented locally: 2026-08-11. No Kubernetes resource, kind image, or
serving process was changed.

Normal Hybrid image construction now has two explicit project-local inputs:
`.offline-wheels/ibg-hybrid/service/` and
`.offline-wheels/ibg-hybrid/controller/`. Their ignored wheel binaries are
described by committed versioned manifests and complete transitive lock files
under `deploy/hybrid-kubernetes/wheel-manifests/`. The manifests pin filenames,
versions, Python `cp312` ABI, and linux/amd64 wheel platforms; neither image
allows solver/MILP dependencies. `scripts/hybrid_offline_wheelhouse.py` is an
import-safe operator helper that lists requirements, validates a supplied
wheelhouse, or explicitly copies a complete validated supplied set into the
project-local cache. It never downloads.

Before a normal runner invocation can inspect or create a cluster, it prints
`Hybrid image mode: build offline from validated local wheelhouses` and validates
both image wheelhouses. A missing, extra, ABI/platform, lock, or recorded-digest
mismatch aborts before either Docker build. Each Dockerfile then copies only its
image-specific cache and uses pip `--no-index --find-links` with
`--network=none`; the wheels are removed from the completed image layer.

Conversely, `--skip-build` prints `Hybrid image mode: --skip-build; reuse
validated node-local images`, does not inspect local wheelhouses, and retains
its previous node-image identity, topology/configuration, Ready, and finite-Job
lifecycle. It does no Docker build, kind load, or serving-workload restart.
The Phase 7.5 controller-source ConfigMap bridge remains available to that path,
while the normal controller Dockerfile still copies the current controller code
permanently.

### Offline image-build evidence

On 2026-08-11, after an explicitly authorized operator wheel download, both
project-local wheelhouses passed validation and clean `--no-cache --pull=false
--network=none` local Docker builds completed. The resulting local manifest-list
IDs are service `sha256:fb1245a5bcfd8c46a5e0d500aaac62d3c36b051744cad3b5604323a9bb2683f8`
and controller `sha256:0ea07d41c9e45b74f075bdba89c532761a4d670d80452a71a24ebe5144b10daf`.
No image was loaded into kind, no container was started, and Kubernetes was not
contacted.

## IBG-Hybrid seeded hidden-state profile allocation

Implemented locally: 2026-08-11. No live cluster or image operation occurred.

The production launcher now requires a nonnegative `--profile-seed`. Its only
effect is processor hidden-state allocation. The versioned
`ibg-hybrid-profile-state-allocation-v1` allocator uses the public state order
Very Good/Good/Bad/Very Bad with integer weights `3/3/2/2`. Each stage is an
append-only sequence of ten-replica strata. Every stratum has exactly those
counts; within a stratum, domain-separated BLAKE2b ranks over allocation
version, seed, stage, stratum, ordinal, and state select among choices whose
prefix discrepancy remains at most one replica. A bounded deterministic
backtrack enforces that invariant without Python or NumPy global RNG state.
Consequently every ten-replica stage has exact 30/30/20/20 coverage, arbitrary
prefixes remain within one replica of their ideal quotas, and changing the seed
permutes identities without changing counts.

The runtime ConfigMap alone records seeded allocation provenance in its
processor-side source identity. Its individual entries remain exactly stage,
replica, hidden state, and observation seed. Canonical observation seeds and all
retained identity seeds remain unchanged; new ordinal seeds keep the separate
identity-derived rule. The controller document remains generated solely from
topology, admission, and planning links and contains no hidden state, profile
seed, observation seed, mix, or equivalent allocation data. The controller Job
still does not mount runtime profiles, and discovered policy replicas still use
`hidden_state=None` with uniform initial beliefs.

Historical profile documents continue to use the legacy fixed allocator and
remain byte-identical fixtures. Seed-aware transition validation regenerates
the exact deployed provenance and exact target before mutation. Same-seed
scale-up preserves every existing runtime entry and appends only missing
ordinals; same-seed scale-down retains lower ordinals and removes only higher
ones. A legacy-to-seeded or seed-to-seed change fails unless
`--refresh-runtime-profiles` is explicit.

The refresh path is deliberately restricted to `--skip-build`, an unchanged
replica count, and no simultaneous resource-template rollout. After complete
source/target and Pod-template validation, it reconciles the exact ConfigMaps,
records the identities whose hidden state differs, then deletes only those
StatefulSet Pods one stage at a time. Exact Ready coverage follows every stage
before the finite controller Job. Unaffected stage Pods and the flow generator
must preserve UID/restart state; deliberately changed Pods must receive new UIDs
with zero restarts. No profile hash or accidental rollout is used.


## Hybrid management/workload node-separation boundary

Implemented locally: 2026-08-15. No kind, Docker, image, live-traffic, or
Kubernetes API mutation was performed.

The dedicated Hybrid kind definition now contains exactly
`ibg-hybrid-control-plane` and `ibg-hybrid-worker`. Only the worker receives
the immutable scheduling label `ibg-hybrid.workload-node=true`. All three
replica StatefulSet Pod templates, the flow-generator Deployment Pod template,
and every retained finite controller Job template select that label. The
control-plane has no matching workload label and remains the Kubernetes
management node.

The persistent launcher now accepts only those two Ready node identities and
roles. It rejects a missing worker, an extra node, a misplaced workload label,
a worker carrying the control-plane role, or any Hybrid replica, flow-generator,
or recognized controller Pod whose bound `spec.nodeName` is not
`ibg-hybrid-worker`. Every serving-Ready gate repeats the worker-placement
check, so rollout completion cannot be inferred from readiness alone on the
wrong node. Node-image validation continues to require both Hybrid image
identities on every kind node.

Dynamic resource admission now compares the requested workload envelope only
with `ibg-hybrid-worker` allocatable CPU and memory. Existing nonterminal Pods
bound to that worker are counted; control-plane management Pods and completed
Jobs are excluded; new replica Pods, a fresh-cluster flow generator, and the
finite controller request retain their existing formulas and resource
declarations. Phase 7 CRI statistics now come from the worker container because
that node owns the serving containers.
No request/limit, worker count, port, probe, client, keep-alive, algorithm,
profile, jitter, learning, utility/SLA, telemetry, or rollout-policy value
changed.

The two kind nodes are still Docker containers on one physical host. This
boundary provides management/workload separation only. It does not provide a
same-worker versus cross-worker workload path, multi-host networking, NIC,
SR-IOV, DPDK/VPP, hugepage, line-rate, or datapath-performance comparison. The
user-reported historical one-control-plane live state is intentionally
incompatible with the new exact topology preflight. No successful live-cluster
read or mutation was part of this local implementation; replacement with a
clean two-node cluster remains a separately approved live gate.


## Hybrid two-node bootstrap readiness gate

Corrected locally: 2026-08-15. A user-authorized first production launch
created the intended control-plane and worker, but kind's create-time wait
returned when the control-plane was Ready while the worker was still joining.
The immediate strict topology preflight therefore failed closed before image
build, workload deployment, or controller traffic.

After creating a fresh cluster, the launcher now explicitly waits for both
named nodes to report Ready before reading the exact node-role, workload-label,
namespace, and Pod inventory. Existing-cluster runs retain the immediate
fail-closed preflight. This changes only bootstrap ordering; all scheduling,
resource, rollout, algorithm, learning, outcome, and telemetry contracts remain
unchanged.

The resumable-bootstrap boundary also recognizes an already existing,
successfully validated dedicated cluster with no `ibg-hybrid-testbed`
namespace as pristine. It follows the same namespace-first bootstrap path and
uses an existing replica count of zero. If the Hybrid namespace exists, the
unchanged strict StatefulSet/profile reconciliation path remains mandatory.


## Hybrid two-node functional confirmation

User-confirmed: 2026-08-15. The corrected production Hybrid launcher completed
a subsequent live test successfully on the one-control-plane/one-worker kind
topology. Detailed run output and metrics were intentionally not retained in
the handoff. This confirms functional availability only and does not add
same-worker/cross-worker, multi-host, NIC, line-rate, or datapath-performance
evidence.


## Deferred Hybrid robustness and reporting extensions

Recorded for later implementation: 2026-08-15. Three independent, opt-in
Hybrid extensions are planned. None is implemented by this entry.

First, a Hybrid transport-robustness wrapper will apply controlled `tc/netem`
impairment around the existing Kernel path. The Exact `netem_v1` boundary is
the compatibility reference: ordinary runs remain unimpaired, configured
delay/jitter is transport noise rather than physical or observation jitter,
and impairment must not enter learning, placement, utility/SLA, or pair-cost
semantics. Exact Pod/interface scope, configuration provenance, cleanup, and
matched impaired/unimpaired validation must be reviewed against the Hybrid
deployment before code is reused. Packet loss, retries, imputation, and
missing-observation behavior are not implied.

Second, the retained legacy Hybrid CSV helpers in `IBG_Hybrid/header.py` and
`IBG_Hybrid/report.py` will be characterized and tested. The review must cover
header creation, append behavior, column alignment, empty/malformed inputs,
deterministic output, and metric meaning. Any production integration should be
an explicit host-side export from completed structured Hybrid results, remain
off by default, and avoid controller-side persistence or import-time writes.

Third, Hybrid will gain an enable-only control-plane data-footprint record per
completed timeslot. The Exact `control_plane_v1` application-payload boundary
is the reference: count controller-boundary payload bytes and messages by
category, exclude forwarder-to-forwarder selected-route traffic, and state
clearly whether values are canonical logical bytes or observed application-body
bytes rather than wire bytes. The versioned record must be absent when disabled
and must not affect policy, traffic, learning, telemetry, utility/SLA, or
equilibrium.


## Hybrid persistent experiment trace

Implemented locally: 2026-08-15. Every successful production `run` now writes
a host-side timestamped JSONL file named
`ibg-hybrid-experiment-<UTC timestamp>.jsonl` under `runs/` by default. The
destination can be relocated with `--trace-dir`; persistence is not performed
inside the controller Pod and requires no Kubernetes volume.

The `ibg-hybrid-experiment-jsonl-v1` stream follows an Exact-style lifecycle:
one `run_started` record, one `iteration_completed` record for every completed
timeslot, and one `run_completed` record. Each iteration retains the complete
existing Hybrid machine evidence, including configuration, flow order, Ready
Pod identities, selected paths/replicas, final loads, planning-link values,
each flow's measured pair latency, selected physical/observation/learning
values, beliefs, metrics, and Pure/Kernel parity.

Before creating a file, the host validates configuration identity, the maximum
iteration bound, contiguous slot IDs, exactly one placement and measured pair
value per configured flow, exactly two selected observations per flow, and a
valid equilibrium field. Cgroup and solver-resource evidence are not required
or added. Processor-private hidden-state allocation provenance remains absent.
This persistence layer changes no controller, policy, traffic, learning,
utility/SLA, telemetry, scheduling, or Kernel behavior.


## Hybrid 80-ms physical-only SLA threshold

Changed locally with explicit user authorization: 2026-08-15. Hybrid now owns
`HYBRID_SLA_LATENCY_THRESHOLD_MS = 80.0`; it no longer inherits Exact's
110-ms default. The active SLA input remains the sum of the two selected
physical processing latencies under `physical-only-v1`. Measured pair latency,
raw end-to-end latency, and observation-only jitter remain recorded but do not
enter Hybrid SLA classification.

Every new Hybrid slot records `sla_latency_threshold_ms: 80.0`, so persisted
JSONL traces remain self-describing. Existing traces, including
`ibg-hybrid-experiment-20260815T122632.955716Z.jsonl`, retain their historical
110-ms classifications and must not be backfilled. Exact's threshold and all
Exact source remain unchanged.


## Hybrid automatic random experiment series

Implemented locally: 2026-08-15. Production `run --runs N` executes `N`
finite, independent controller Jobs without accepting a seed argument. The
launcher obtains nonzero, distinct 63-bit experiment seeds from the operating
system CSPRNG. Each run's experiment seed is both the controller policy root
seed and its first slot ID, so policy/flow-order random streams and Kernel
processor request sampling vary together while remaining reproducible from
that run's persisted provenance.

The runtime environment is fixed across a series. An existing seeded Hybrid
deployment reuses its deployed profile seed; a fresh cluster or validated
cluster without the Hybrid namespace receives one automatically random profile
seed for the whole series. The same topology and hidden-state allocation are
then reconciled for every run. Runtime-profile refresh is forbidden in series
mode, and an existing legacy deployment without seeded profile provenance
fails closed. The first run performs the requested image/build path and later
runs reuse it; every run still creates a new finite controller Job and
therefore begins with fresh uniform beliefs.

Each series member is persisted as its own validated JSONL lifecycle trace.
The files share a series identity, use `-run001`, `-run002`, and subsequent
suffixes, and record the experiment seed plus series index/count. Single-run
behavior remains available and continues to require explicit `--profile-seed`.
This orchestration changes no Hybrid solver, pruning/lookahead/MC behavior,
jitter, learning, outcome, telemetry, worker-placement, or frozen Exact code.


## Hybrid interrupted scale-down recovery

Implemented locally: 2026-08-15. Dynamic seeded-topology reconciliation now
recognizes one narrowly recoverable deployment state: all three owned
StatefulSets have the same positive replica count, that count is lower than the
replica count in the deployed runtime/controller documents, and those documents
still match their exact versioned deterministic generation rule. Kubernetes
StatefulSet ordinals make the live Pods the retained low-ordinal prefix.

The launcher validates the complete old documents before mutation, reports the
recovery, projects the requested target documents, and resumes normal bounded
rollout from the actual StatefulSet count. A profile count below the live Pod
count, inconsistent stage counts, malformed/foreign ownership, or any profile,
admission, planning-link, source-identity, observation-seed, or retained-state
drift still fails closed. This recovery changes no running workload by itself
and does not weaken the fixed-environment contract within a multi-run series.


## Hybrid opt-in legacy-layout CSV export

Implemented locally: 2026-08-15. Production `run --csv 1` converts each
completed, validated host-side Hybrid JSONL trace into exactly five CSV files
under the ignored repository-local `figures/` directory:
`time.csv`, `sla_violations.csv`, `aggregate_utility.csv`, `jain_index.csv`,
and `replica_results.csv`. CSV output remains disabled by default, uses no
controller filesystem or Kubernetes volume, and never creates or calls
`results.csv`/`log_results`.

The four metric files retain the legacy wide layout: one deterministic
six-character run-hash column per experiment and one value per completed
timeslot row. Time exports `elapsed_seconds`; SLA exports the active
`physical_only_sla_violations`; Jain exports `jain_fairness`. By explicit user
choice, the legacy-named `aggregate_utility.csv` exports the current raw
end-to-end utility, `raw_end_to_end_reference_utility`, rather than predicted
or physical-only utility. Multi-run series therefore add one distinct column
per automatically seeded Job.

`replica_results.csv` retains one `(stage, replica)` column per identity and a
JSON belief vector in each cell. Every experiment appends its initial belief
snapshot followed by one post-update snapshot per completed timeslot; run
boundaries remain implicit to preserve the legacy layout. Column alignment is
now identity-based and deterministic, including reordered inputs and added
replicas. Shared atomic table primitives treat an empty file as new, preserve
unequal run lengths with blank cells, reject malformed rows/duplicate headers,
validate metric and belief values, and reject metric run-hash collisions before
export. The export layer changes no Hybrid metric, algorithm, learning,
telemetry, scheduling, JSONL, or frozen Exact behavior.


## Hybrid CSV output directory

Adjusted locally: 2026-08-15. All opt-in Hybrid CSV reports now live under the
dedicated `figures/IBG_hybrid/` directory rather than directly under
`figures/`. The host exporter checks the path and creates the directory and
missing parents before its first write. Filenames, columns, rows, metric
semantics, JSONL provenance, and default-off behavior are unchanged.


## Hybrid opt-in control-plane data footprint

Implemented locally: 2026-08-15. Production `--csv 1` now propagates
`HYBRID_CONTROL_PLANE_FOOTPRINT=1` into the finite controller Job. Each
successfully completed Kernel slot carries an
`ibg-hybrid-control-plane-data-v1` block at the controller-result/evidence
boundary; `--csv 0` and omission propagate the disabled state and emit no
block. The record deliberately stays outside `HybridSlotMetrics` and Pure/
Kernel semantic parity.

The category names and application-body boundary match Exact
`control_plane_v1`: one accepted aggregate Kubernetes Pod-list request and
response, one serialized route-command request, one raw selected-telemetry
response, and controller-local belief TX/RX fields. Hybrid counts the actual
HTTPX request and response body lengths. GET request bodies are normally zero;
belief bytes and messages are exactly zero because no belief vector crosses
the controller boundary. The six-category payload and message totals are
validated exactly. Forwarder traffic, headers, wire bytes, NIC throughput,
memory, cgroups, timing, and CPU are not measured.

Exact's full schema also contains timing and CPU fields, which were explicitly
excluded from this Hybrid scope. Hybrid therefore uses a separately named
data-only schema rather than emitting an incomplete record under the Exact
schema name. A completed Hybrid snapshot requires exactly one message in each
discovery/route/telemetry category and zero belief messages; transient
incomplete discovery polls and failed slots cannot become completed evidence.

When footprint evidence is present, the existing host exporter additionally
creates `figures/IBG_hybrid/footprint/` and writes 16 wide-layout CSVs: the six
primary payload categories, derived belief payload total, grand payload total,
and the parallel eight message reports. Derived belief totals are TX plus RX
and are never added to the six-category grand total a second time. The original
five files under `figures/IBG_hybrid/` retain their names, layout, and meaning.

`scripts/hybrid_control_plane_summary.py` is the matching host-side validation
and summary boundary. It accepts completed Hybrid JSONL traces, revalidates
every data-only snapshot, and reports per-run median/p95 values for each
payload category, each message category, the two derived belief totals, and
the two exact grand totals. It contains no timing or CPU reporting and does not
change Exact's separate `scripts/control_plane_summary.py`.


## Planned Hybrid per-timeslot execution optimizations

Planned: 2026-08-16. Four architecture-only optimizations are ordered for the
Hybrid Kernel controller. They must not change flow order, pruning, candidate
sets, lookahead depth, branch recurrence, canonical tie-breaking, placement,
loads, random streams, physical or observation jitter, learning, beliefs,
utility/SLA, fairness, equilibrium, route semantics, telemetry, footprint
arithmetic, worker placement, or frozen Exact behavior.

Phase 1, **persistent HTTP clients**, has medium implementation difficulty.
Controller-owned clients will reuse connections across slots for aggregate
Kubernetes discovery and the controller-to-flow-generator request. The
flow-generator application will reuse its client pool for first-forwarder
dispatch. Request counts, bodies, validation, timeouts, and completed-slot
footprint categories remain unchanged. Existing inherited forwarder-local and
downstream clients, their 30-second keep-alive contract, and measured selected-
pair semantics are outside this change. Every client requires an explicit
startup/shutdown owner and deterministic cleanup on success and failure.

Phase 2, **bounded parallel lookahead candidate evaluation**, has high
implementation difficulty because semantic equality is the primary gate. Only
independent focal-candidate branches for one current real flow may execute in
parallel. Real flows remain sequential, and projected future flows inside each
branch remain sequential. Each task receives immutable current state, beliefs,
admission data, planning links, parameters, and its canonical candidate index.
Results must be restored to canonical order before the unchanged strict-
improvement and first-on-tie selection rule is applied. Phase 2 first exposes
and validates this pure worker boundary while production remains serial.

Phase 3, **controller-lifetime bounded process-pool reuse**, has medium-high
implementation difficulty. One two-process pool will be created by the finite
controller, reused across all focal decisions and completed slots, and closed
when the controller exits. Workers must receive current slot state explicitly
and must never retain controller beliefs, real loads, or mutable policy state.
Normal completion, task failure, and controller termination must leave no
child process. This phase activates the Phase 2 boundary only after exact
serial/parallel parity is established.

Phase 4, **soft controller CPU priority**, is deliberately last and has medium
overall difficulty: the manifest edit is small, but resource admission and
live non-regression evidence are not. If preceding measurements justify it,
the controller CPU request may increase from `100m` toward an evidence-selected
value, initially considering `1`, while retaining the `2`-CPU limit. This is
shared weighted capacity, not an exclusive or pinned core. It adds no node and
changes no one-control-plane/one-worker placement rule. All controller Job
templates and worker-only resource-preflight arithmetic must agree before a
separately approved live comparison. Unused CPU must remain available to
replicas and the flow generator.


## Hybrid persistent HTTP-client lifecycle

Implemented locally: 2026-08-16. Phase 1 gives the finite controller explicit
ownership of one persistent synchronous Kubernetes client and one persistent
controller-to-flow-generator client. Both are constructed once, reused by all
slots, closed once by the controller CLI on success or failure, and rejected
after closure. Environment construction uses a pending-resource stack so a
partially constructed controller cannot leak an already-created client.

The Hybrid flow-generator FastAPI lifespan now starts one asynchronous client
pool in `HybridKernelRouteExecutor`, reuses it for first-forwarder dispatches,
and closes it at application shutdown. Import remains client-free. Pure direct
executor callers that do not run an ASGI lifespan retain the former safe
one-call client lifecycle, keeping import/unit-test usage compatible without
creating an event-loop-bound client globally.

This changes connection ownership only. Kubernetes selector/query behavior,
one accepted discovery exchange, one route/telemetry exchange, request and
response bodies, timeouts, validation, footprint bytes/messages, selected-pair
semantics, inherited public-forwarder clients and keep-alive, algorithm,
learning, metrics, and Pure/Kernel parity remain unchanged. No performance
improvement is claimed without a separately approved live comparison.


## Hybrid process-safe focal lookahead branch boundary

Implemented locally: 2026-08-16. Phase 2 exposes the module-level
`evaluate_hybrid_lookahead_branch` boundary for exactly one deterministic
focal candidate. Its frozen task carries the Hybrid configuration and policy
parameters, immutable current global loads, the complete scored focal action,
admission metadata, beliefs, planning pair links, requested/effective depth,
and original canonical index. Mapping inputs are serialized as immutable
tuples; the worker reconstructs private dictionaries and a private
`IBGHybridPolicy` cache.

Each branch applies only its focal action to private state, then evaluates its
projected future flows sequentially through the unchanged greedy policy. The
indexed outcome contains either the complete existing
`HybridLookaheadEvaluation` or the complete existing branch-failure record.
Unexpected worker exceptions retain the canonical index and focal action.
Decision assembly sorts outcomes by canonical index, verifies complete
one-to-one candidate coverage, and then applies the unchanged strict-
improvement rule, so exact ties retain the first canonical completed branch.

Production `select_lookahead` invokes this worker boundary serially. A private
import-safe validation method can map the same tasks through a test-owned
executor, but no process pool is owned or activated by the policy, controller,
runner, CLI, Job, or launcher. Real flows, real commits, branch-internal future
flows, traffic, telemetry, learning, beliefs, metrics, and existing MC pool
semantics remain sequential and unchanged. Phase 3 alone may later integrate
a controller-lifetime bounded pool after separate authorization. This phase
proves process safety and semantic equality only; it makes no speed claim.


## Hybrid controller-lifetime lookahead process pool

Implemented locally: 2026-08-16. Phase 3 activates the Phase 2 focal-branch
boundary only for the finite Kernel controller's deterministic-lookahead mode.
The controller constructs one `ProcessPoolExecutor` with exactly two workers
and a `spawn` multiprocessing context. Spawn prevents workers from inheriting
the controller's Kubernetes and flow-generator HTTP clients; every submitted
task still carries its complete current immutable planning inputs and creates
its own private policy/cache.

The same executor is passed through every sequential real focal decision in a
slot and every completed slot in the finite controller lifetime. Each focal
decision maps only its independent candidate branches; projected future flows
inside each task remain sequential. The map completes before the selected real
focal action is committed, and all real flows remain ordered and sequential.
The workers remain idle during traffic, telemetry validation, learning, and
metrics, then receive fresh explicit loads and beliefs with the next task.

The controller shuts the pool down with waiting and pending-future
cancellation before closing its persistent HTTP clients. Normal completion,
slot failure, context exit, CLI `finally` cleanup, and the alternate finite
controller-service exit all use that owner. Slot evidence records the fixed
worker count and `ibg-hybrid-controller-lookahead-pool-v1` lifecycle. Active
lookahead slots require exactly two children between slots; controller shutdown
requires none. Historical lookahead evidence without this provenance continues
to represent the former zero-worker lifecycle. Manual MC retains its separate
per-slot rollout pool and requires zero lookahead workers.

Pure `run_hybrid_slot` and direct `select_lookahead` calls remain serial by
default. They accept an executor only as an internal integration boundary; no
CLI worker flag or user-facing lookahead mode was added. No resource, manifest,
topology, scheduling, HTTP, footprint, algorithm, random, latency, learning,
utility/SLA, telemetry, or frozen Exact behavior changed. Local tests establish
reuse, cleanup, and semantic equality, not a timeslot speed improvement.


## Hybrid controller-lifetime lookahead live validation

Validated live: 2026-08-16. The user authorized a bounded transition from the
existing 30-flow, 15-replica environment to 15 flows and eight replicas per
stage with the retained profile seed 50. The launcher removed only StatefulSet
ordinals 8--14; all retained ordinals 0--7 and the flow-generator Pod kept
their UIDs and zero restart counts. All 24 retained replica Pods, the flow
generator, and the finite controller ran on `ibg-hybrid-worker`; Kubernetes
management services remained on the control-plane node.

Only the controller image was rebuilt and loaded. A three-slot, explicitly
deterministic-lookahead controller Job used root seed 2050 and the unchanged
100m/2-CPU request/limit. Every completed slot reported two lookahead workers,
`ibg-hybrid-controller-lookahead-pool-v1`, two active children after the slot,
Pure/Kernel replay parity, retained belief continuity, complete placement
before one route request, 30 selected observations, and 15 measured pairs.
Observed worker PIDs 22 and 25 remained identical across all three slots. The
controller container then exited successfully and no controller container or
lookahead worker remained; the 48 continuing `spawn_main` processes are the
unchanged two Uvicorn workers in each of 24 public-forwarder containers.

Slot elapsed times were 10.150, 7.545, and 8.546 seconds (26.240 seconds total
inside slot metrics); the Kubernetes controller Pod ran for approximately 58
seconds and the Job completed in 61 seconds. This is lifecycle and correctness
evidence only because no matched live serial baseline was run. It is not a
speedup, multi-host, cross-worker, NIC, line-rate, or exclusive-CPU result.


## Hybrid finite-controller soft CPU priority

Implemented locally: 2026-08-21. Every retained finite Hybrid controller Job
template now requests one CPU and retains its existing two-CPU limit and
256-MiB/1-GiB memory request/limit. The request is ordinary Kubernetes shared
scheduler accounting and Linux CPU weighting. It neither reserves an exclusive
physical core nor enables pinning, cpusets, static CPU-manager allocation,
affinity, another worker, or another node. CPU not used by the controller
remains available to the replica and flow-generator processes.

The worker resource preflight uses the same 1000-millicpu controller request
when summing the current nonterminal worker Pods, any new replica Pods, a fresh
flow generator when applicable, and the future finite controller. It continues
to compare that exact Pod-request sum against the Kubernetes worker's reported
allocatable CPU and memory and fails before mutation when either resource is
insufficient. No host CPU ceiling or synthetic four-CPU cap is introduced.

This phase changes only controller request accounting. The two-process
lookahead pool, manual-MC pool, HTTP-client lifecycles, service resources,
topology and worker selector, and every algorithm, random, latency, learning,
utility/SLA, telemetry, footprint, route, and scheduling semantic remain
unchanged. Local tests establish template/preflight consistency and regression
parity; a separately approved matched 100m-versus-1-CPU live A/B is still
required before making any runtime-improvement claim.


## Planned Hybrid end-to-end SLA metrics

Planned: 2026-08-21. SLA reporting is ordered into two explicit steps. The
authorized first step replaces the active Hybrid violation count's physical-
only input with each flow's already-recorded raw end-to-end latency: selected
physical processing latency plus measured consecutive-pair latency. A flow is
an end-to-end SLA violation only when that value is strictly greater than the
unchanged 80-ms threshold. The active metric is named
`end_to_end_sla_violations`; physical processing, measured pair, and raw end-
to-end latency remain separately recorded.

The active wide-layout count export is named
`end_to_end_sla_violations.csv`. The historical generic
`sla_violations.csv` is not reused for new columns, preventing physical-only
and end-to-end counts from being mixed in one unversioned table.

This SLA-count change does not make pair latency a planning, learning, or
utility input. Placement, beliefs, observation-only jitter, physical jitter,
realized utility, raw end-to-end reference utility, and all traffic/telemetry
boundaries remain unchanged.

The second step is planned but not authorized for implementation. It will add
`end_to_end_sla_excess_ms`, calculated per completed timeslot as
`sum(max(0, raw_end_to_end_latency_ms - 80))` across flows, and a separate CSV
with one timeslot value per row. It must remain distinct from the violation
count and must not be implemented until the user explicitly requests it.

Implemented locally: 2026-08-21. The first step is complete. Hybrid slot
metrics now derive `end_to_end_sla_violations` directly from the recorded raw
end-to-end per-flow map. Kernel evidence serializes the renamed field, Pure/
Kernel replay compares it as part of the complete metrics value, and host trace
persistence uses `ibg-hybrid-experiment-jsonl-v2`. Persistence validates the
80-ms threshold, complete finite nonnegative per-flow raw values, strict
greater-than counting, and absence of the retired physical-only field.

Console output labels the count as end-to-end. Active CSV export reads only the
new field and writes `end_to_end_sla_violations.csv`; it rejects legacy
physical-only trace fields and never creates or modifies historical
`sla_violations.csv`. No accumulated SLA excess value or quality CSV exists.


## Hybrid end-to-end SLA excess quality metric

Implemented locally: 2026-08-21. Every completed Hybrid slot now carries
`end_to_end_sla_excess_ms`, the per-timeslot sum of
`max(0, raw_end_to_end_latency_ms - 80)` across all configured flows. The
calculation consumes the existing canonical raw end-to-end per-flow map after
physical processing and measured consecutive-pair latency have already been
combined. It preserves full floating-point precision and does not construct a
second latency path or retain a separate per-flow excess field.

The count and quality values therefore share one evidence source: exactly
80 ms contributes neither a violation nor excess, and values above 80 ms
contribute one violation plus only their positive difference. The metric is a
slot result value, so the existing complete-metrics Pure/Kernel replay
comparison includes it automatically. Kernel evidence serialization includes
it in every completed metrics block, and human output labels the sum explicitly
as end-to-end milliseconds.

Active host traces are now `ibg-hybrid-experiment-jsonl-v3`. Persistence
requires complete finite nonnegative raw per-flow coverage, the unchanged
80-ms threshold, a matching strict violation count, and a finite nonnegative
excess value exactly recomputed from that same raw map. Active `--csv 1`
export adds `figures/IBG_hybrid/end_to_end_sla_excess_ms.csv` with the existing
six-character run-column, timeslot-row, blank-padding, duplicate-rejection,
malformed-file rejection, and atomic-write behavior. CSV-disabled runs create
no quality report. The five preceding Hybrid reports retain their layout and
meaning, and historical traces and `sla_violations.csv` remain untouched.

This reporting addition changes no threshold, violation count semantics,
physical-only realized utility, raw end-to-end reference utility, placement,
learning, beliefs, telemetry, latency generation/measurement, routing,
scheduling, resources, or frozen Exact behavior.


## Hybrid opt-in replica-egress transport impairment

Implemented and locally verified: 2026-08-22. Hybrid now has one versioned,
host-selected `ibg-hybrid-netem-v1` transport configuration. The production
launcher defaults it off. When enabled, deterministic dynamic Kustomize
patches add one short-lived init container to each of the three replica
StatefulSet Pod templates. That container applies `tc qdisc replace` only to
the replica Pod network namespace's `eth0` egress, has `NET_ADMIN` as its only
added capability, drops all other capabilities, and is not privileged. The
ordinary private-processor and public-forwarder containers remain non-root and
unchanged. Controller, flow-generator, kind-node, host, and Kubernetes
management interfaces are outside this boundary.

The bounded init image is Hybrid-owned as `ibg-hybrid-testbed:netem-v1` and is
rebased offline from the already-local frozen Exact runtime image solely to
reuse its validated `/usr/sbin/tc`. It is built and image-identity checked only
for enabled runs. Disabled rendering contains no netem init container,
capability, annotation, or qdisc command. A configuration transition is a
deliberate replica StatefulSet template rollout; the launcher rejects mixed,
malformed, or silently reused impaired/unimpaired templates and preserves the
flow-generator Pod across that transition.

Every persisted lifecycle event receives the complete top-level
`network_impairment` record, including explicit disabled provenance. The host
boundary requires one identical configuration across the trace and rejects
missing, malformed, mixed, drifted, or controller-supplied provenance. The
active trace remains `ibg-hybrid-experiment-jsonl-v3` because this is additive
run provenance outside `HybridSlotMetrics`; Pure/Kernel metrics and parity are
unchanged.

Netem remains external transport impairment, separate from physical processing
jitter and observation-only learning noise. It does not directly alter policy,
placement, beliefs, learning, physical-only realized utility, or pair
measurement semantics. Because the existing raw end-to-end boundary includes
measured consecutive-pair latency, injected delay may legitimately affect raw
end-to-end latency, end-to-end violation count and excess, and raw end-to-end
reference utility. That observed effect is neither suppressed nor counted a
second time. Packet loss, retries, imputation, and partial-slot acceptance are
not part of this feature.


## Hybrid equilibrium stopping tolerance

Updated: 2026-08-22. The active Hybrid equilibrium check now stops only when
every belief-vector entry changes by strictly less than `0.04` from the prior
completed timeslot. Equality at `0.04` does not pass. The existing Exact
equilibrium helper remains the implementation boundary; Hybrid supplies the
new threshold explicitly. This changes stopping time only and does not alter
belief updates, placement, learning, utility/SLA, telemetry, seeds, traffic,
or any per-slot algorithm result.


## Hybrid control-plane phase wall time

Implemented and locally verified: 2026-08-22. When `--csv 1` enables the
existing Hybrid controller-footprint boundary, every successfully completed
slot now includes monotonic `timing_ms` alongside its retained application-body
payload and message counters. Discovery spans the complete Ready-Pod discovery
call. Admission spans slot start through discovery, policy/pruning/lookahead,
placement, and serialized route-request preparation, ending immediately before
the flow-generator POST. `data_plane_wait` spans that POST through response
receipt. Feedback spans response receipt through telemetry conversion,
learning, metrics, equilibrium handling, and valid slot completion. Active
control time is exactly admission plus feedback; selected-route waiting remains
separate.

The versioned footprint schema is now
`ibg-hybrid-control-plane-wall-time-v2`. The enclosing experiment trace remains
`ibg-hybrid-experiment-jsonl-v3` because `HybridSlotMetrics` and its semantic
contract are unchanged. Five wide-layout reports are added under
`figures/IBG_hybrid/footprint/`: `discovery_time_ms.csv`,
`admission_time_ms.csv`, `feedback_time_ms.csv`,
`active_control_time_ms.csv`, and `data_plane_wait_ms.csv`. Existing payload
and message reports retain their categories and arithmetic.

This measurement intentionally contains no CPU, child-process CPU, cgroup,
memory, NIC, or wire-byte field. It can identify whether controller admission
or selected-route waiting dominates wall time, but it cannot by itself prove
that the two lookahead processes saturate their CPU limit. Failed or partial
slots cannot finish or persist a timing snapshot. The measurement does not
enter Pure/Kernel metric parity and changes no policy, random stream, placement,
learning, utility/SLA, telemetry, resource, topology, or scheduling behavior.


## Hybrid four-process lookahead candidate envelope

Implemented locally: 2026-08-22. The finite deterministic-lookahead controller
now owns one spawn-isolated pool of four worker processes instead of two. The
same pool remains persistent across every sequential real flow and completed
timeslot. Only independent focal candidate branches run concurrently;
projected future flows inside each branch, real flow commits, traffic,
telemetry, and learning remain sequential. Results are still restored to
canonical order before selection, preserving strict improvement and first-
canonical tie behavior. Manual MC retains its separate two-worker boundary.

Every retained production controller Job now requests two CPUs and has a
four-CPU limit, with its 256-MiB request and 1-GiB memory limit unchanged. The
worker preflight adds 2000 millicpus for the future finite controller and still
uses actual Kubernetes allocatable/request arithmetic. These are shared soft
scheduler resources, not exclusive cores, pinning, cpusets, new nodes, or
guaranteed physical capacity. Idle CPU remains available to serving workloads.

The candidate targets the measured admission bottleneck from the preceding
five-slot 20x3x10 baseline, where mean admission was about 15.32 seconds while
mean selected-route wait was about 177 ms. That baseline motivates the test but
does not predict or prove improvement. A matched user-run candidate trace is
required before any speedup or serving-non-regression conclusion.


## Hybrid optional Pure/Kernel parity replay

Implemented locally: 2026-08-22. Normal production experiments now perform
each Kernel timeslot once. The previously unconditional post-slot
`_replay_kernel_semantics` calculation is controlled by the production option
`--parity-replay 0|1` and defaults to disabled. Disabling it does not remove
traffic, telemetry validation, belief updates, metrics, JSONL, CSV, placement,
or controller-lifetime lookahead processing; it removes only the second serial
policy calculation over the completed slot's already-returned telemetry.

The host launcher propagates the selection as `HYBRID_PARITY_REPLAY` into the
finite controller Job. A disabled completed slot records
`pure_kernel_replay_performed=false` and contains no parity result. An enabled
slot records `pure_kernel_replay_performed=true`, recomputes the unchanged
serial Pure decision, requires `pure_kernel_replay_parity=true`, and fails
closed if the comparison disagrees. The historical `run-small` validation gate
continues to perform and require replay because parity is part of that gate.

Trace lifecycle events record `parity_replay_enabled`; persistence rejects
missing, mixed, disabled-result, or failed enabled provenance. This additive
evidence remains outside `HybridSlotMetrics`, so the active SLA metrics trace
contract stays `ibg-hybrid-experiment-jsonl-v3` and historical traces are not
rewritten. Dedicated tests retain continuous serial/parallel semantic parity
coverage even when ordinary experiments use the default-off setting.


## Hybrid netem image self-containment correction

Corrected and image-validated: 2026-08-22. The Hybrid netem init image no
longer depends on the optional historical `ibg-testbed:kernel-phase3` host
tag. Its multi-stage Dockerfile uses the same digest-pinned kind node image as
the Hybrid cluster, verifies the local `tc` utility and `normal.dist`, and
copies only `tc`, its runtime libraries, and the normal-distribution table into
a Hybrid-owned scratch image. The result remains offline-buildable and keeps
the init-container command, `NET_ADMIN` boundary, replica-`eth0` scope, and
`ibg-hybrid-netem-v1` provenance unchanged. IBG-Exact is not modified.

The resulting `ibg-hybrid-testbed:netem-v1` image is 3.28 MB, reports
iproute2 6.15.0, and successfully executed the configured 7-ms delay/3-ms
normal-jitter qdisc command in an isolated disposable container. It was loaded
into both existing kind nodes without applying manifests or starting traffic.

## MILP large-profile Kubernetes persistence

The MILP Kernel launcher persists its generated experiment profile ConfigMap
with Kubernetes server-side apply under the dedicated
`milp-kernel-launcher` field manager. This is required for large explicit
synthetic planning-link profiles: client-side apply stores a second serialized
copy in `kubectl.kubernetes.io/last-applied-configuration`, whose annotation
has a 256-KiB Kubernetes limit. Server-side apply retains the same ConfigMap
data and controller mount contract without that duplicate client annotation.

For large coupled MILP solves, the finite controller Job requests 8 GiB of
memory and is limited to 16 GiB. This is an isolated controller cgroup
allocation; it does not reserve exclusive host memory or alter replica,
forwarder, flow-generator, route, profile, or solver semantics.

When an existing MILP topology changes replica count, profile-drift validation
compares only the stable ordinal Pods that remain after the requested change:
the common prefix of existing and requested replica counts. This protects
retained Pod identities against silent state/profile replacement while allowing
the higher ordinals of an intentional scale-down to be removed normally.

The current synthetic-scale MILP planner profile is
`milp-scale-synthetic-profile-v2`. Its deterministic directed planning-link
coefficients range from 65.000 through 74.999 ms in 0.001-ms increments;
they remain planner inputs only and do not inject traffic delay. The frozen v1
generator (0.500--5.499 ms) remains selectable internally for historical
reproduction, while new `synthetic-scale` runs default to v2.

## Planned Greedy baseline architecture

Recorded: 2026-08-24. The architecture below remains the implementation plan.
Greedy Phase 0 now supplies executable contract and legacy-characterization
fixtures, but no Greedy policy runtime, controller, container image,
Kubernetes resource, cluster, trace, or CSV writer is implemented.

`Greedy/` will become the project-owned package for the final pure-Greedy
baseline. The files currently in that directory are historical simulation
material, not an executable specification. In particular, the current
`main.py` performs work at import time, hard-codes 50 flows, three stages, and
80 replicas per stage (240 total), selects the budgeted path by default, and
contains a retired historical `range(1,30)` loop that launches 29 executions.
That loop is characterization evidence only and is not part of the new run
contract. The active budgeted helper selects two stages,
while the dormant per-stage helper can return replica zero and its embedding
path then increments the last load entry. Its utility, jitter, learning, SLA,
equilibrium, and CSV behavior also predate the active testbed contracts.
Implementation must therefore characterize useful formulas and fixtures before
replacing the execution boundary; it must not copy the old driver as the new
controller.

### Greedy policy contract

For a requested topology of `N` flows, `K>=2` positive contiguous configured
stages, and `M` replicas per stage, every admitted flow receives one budgeted
action with fixed `L=2`: exactly one Ready replica from each of two distinct
stages. Selected identities are ordered by increasing stage, and the other
`K-2` stages are explicit bypasses. A seeded flow order is fixed for a
completed timeslot.

For each flow, the policy evaluates every feasible canonical two-stage action
against the real current global loads. Each selected replica is evaluated at
projected load `n[k,j] + 1`; the immediate action score is the sum of its two
belief-driven expected stage utilities. The greatest score is committed, then
both selected loads are incremented before the next real flow is evaluated.
Exact score ties retain the lexicographically lowest canonical action by
`(stage, replica)` identities.

This is `pure-greedy-budgeted-l2-v1`: no recursion, future-flow simulation,
candidate pruning, local search, deterministic lookahead, Monte Carlo, bandit,
MILP call, or planning-link coefficient may affect selection. The controller
still has a no-rejection route contract. If every feasible action score is
non-positive, it chooses the greatest value rather than returning the legacy
zero sentinel. Readiness and declared admission capacity define feasibility.
Each generated replica receives `ceil(N/M)` admissions, matching the current
Hybrid topology rule. An empty feasible action set fails the slot rather than
producing a partial route.

The user-selected target now shares Hybrid's budgeted `L=2` action shape while
remaining pure Greedy. The historical `Greedy/budgeted.py` is useful only for
characterizing that shape because its stochastic grids and old semantics are
not trusted. Link cost is measured only after the two-hop action is chosen. It
remains raw outcome/SLA/reference-utility telemetry and cannot feed back into
the same-slot greedy score unless the user separately changes that contract.

### Semantic and package boundaries

Greedy will own its policy, configuration, runner, controller, console,
persistence, CSV, deployment, launcher, and tests. Policy-neutral behavior
should reuse the current tested runtime contracts where direct reuse does not
couple Greedy to a Hybrid policy module: four-state expected utility, physical
`half-normal-additive-v1` jitter, independent
`half-normal-observation-v1` learning noise and exact convolved likelihood,
selected-only posterior aggregation, physical-only realized utility, measured
consecutive-pair telemetry, raw end-to-end reference utility, Jain fairness,
and controller-private beliefs. If a component cannot be reused without a
Hybrid algorithm dependency, Greedy must own a thin adapter and prove behavior
with compatibility tests rather than silently fork mathematics.

For comparison with the active Hybrid baseline, Greedy will use the same
strict raw-end-to-end SLA definition and 80-ms threshold: selected physical
processing plus measured consecutive-pair latency is a violation only when it
is greater than 80 ms, and excess is the unrounded sum of positive differences.
Realized utility remains physical-only. Equilibrium uses the active Hybrid
strict per-belief-entry change `<0.04` and changes stopping time only. These
values must be frozen in Phase 0 fixtures before implementation; the old
Greedy 15-ms latency excess and 0.06 equilibrium threshold are historical only.

The pure runner will support dependency-injected discovery, traffic, and
observation ports so policy/learning/metric tests need no cluster. One
completed slot must contain `N` placements, `2*N` selected observations, and
`N` measured selected-pair records, plus `K-2` bypassed stages per placement.
Hidden runtime state and profile seed never enter the policy input. A
Pure/Kernel replay gate will require the
same flow order, profiles, observations, placements, belief changes, and
metrics for a captured slot while allowing wall-clock runtime to differ.
Correctness and small live gates always enable that replay. Ordinary production
runs default to `--parity-replay 0` so they do not repeat the complete Greedy
calculation; `--parity-replay 1` explicitly restores the fail-closed oracle.
Each slot records whether replay was requested and actually performed, and a
disabled replay never records a fabricated parity result.

### Greedy Kubernetes ownership and runtime

Greedy will use a dedicated persistent kind cluster `greedy`, context
`kind-greedy`, and namespace `greedy-testbed`. The kind topology will contain
exactly one control-plane node and one worker node. Only the worker carries
`greedy.workload-node=true`; every Greedy replica, flow-generator, and finite
controller Job selects it. The control-plane remains management-only. Cluster
inventory must reject the Exact, Hybrid, or MILP namespaces and any foreign or
misplaced workload before mutation.

Each configured stage owns one headless Service and one StatefulSet named
`greedy-stage-<stage>`. Stable ordinal `r-1` maps to Greedy identity
`(stage, r)`. Each Pod preserves the accepted two-container Kernel boundary:
a single-worker private processor on port 8081 creates physical processing and
the selected learning signal, while a two-worker public forwarder on port 8080
executes only the selected route and records pair telemetry. The current
processor, forwarder, and flow-generator requests/limits, probes, and matched
forwarder keep-alive behavior are the initial compatibility profile and may
not be retuned during baseline construction. One flow-generator Deployment
executes selected two-hop routes; one finite Greedy controller Job starts only after
exact Ready ordinal coverage.

Greedy-owned images, labels, ServiceAccount/RBAC, ConfigMaps, Jobs, and
manifests must not reuse Hybrid resource ownership names. The controller may
only get/list namespace-scoped Pods. Runtime profiles contain stage, replica,
hidden state, and observation seed; controller inputs contain only public
topology/admission data. `--profile-seed` deterministically allocates one fixed
hidden-state map for the experiment, records its version and seed in host-side
provenance, and does not seed flow order or physical/observation sampling.
Formal cross-baseline same-map comparison remains a separate gate unless the
exact recorded map, rather than seed spelling alone, is proven identical.

### Dynamic topology and launcher contract

The entry point is `scripts/run_greedy_kernel.py run`. It requires
explicit positive `--flow`, `--stage`, and `--replica` values on every
invocation, with `--stage` constrained to at least two. There are no runtime
topology defaults. A positive
`--max-iterations` and nonnegative `--profile-seed` remain required.
`--rollout-batch-size` is positive and bounds the
number of missing replica ordinals added to every retained stage before each
Ready gate, with a conservative default of one. `--csv {0,1}` and
`--parity-replay {0,1}` both default to zero. `--skip-build` means only: reuse
validated Greedy images already loaded into the existing dedicated cluster,
skip Docker builds and kind loads, and avoid an otherwise forced serving
restart. It still reconciles the requested topology/profiles, validates Ready
coverage, and creates a fresh finite controller Job; it fails on a fresh
cluster or image mismatch. Every launcher invocation creates exactly one
experiment/controller run. Greedy has no `--runs` option and performs no
automatic repetition inside an invocation.

Flow-count changes update controller/admission inputs without changing serving
Pod identity. Replica scale-up is append-only and batched; scale-down removes
only higher ordinals, waits for their absence, then projects lower profiles.
Stage identities are always contiguous and may never contract below two.
Stage scale-up creates only new
highest-stage Services/StatefulSets and reaches their requested ordinals before
traffic. Stage scale-down first prevents a new controller run, removes only
highest stages, waits for absence, then removes their profiles. Retained
lower-stage Pods and the flow generator must keep UID and restart state under
`--skip-build`. Partial ownership, inconsistent per-stage counts, profile
drift, a noncontiguous stage set, or a resource-preflight failure aborts before
controller traffic.

### Console and host-side evidence

Launcher progress follows the Hybrid presentation grammar with a Greedy
label: selected topology, profile allocation, image mode, worker-resource
preflight, each rollout target/Ready gate, controller start/completion, trace
path, and CSV directory. Controller output prints the same aligned initial
and final belief tables and the same completed-iteration block for outcome
mode, predicted/realized/physical/raw utility, end-to-end SLA count and excess,
fairness, elapsed time, and equilibrium. It does not print hidden state.

Complete machine evidence uses the prefix `GREEDY_SLOT_EVIDENCE=` and retains
full flow order, placements, loads, selected observations, pair telemetry,
beliefs, metrics, and policy provenance. Every successful production run is
persisted on the host as `runs/greedy-experiment-<UTC timestamp>.jsonl` with
one `run_started`, one `iteration_completed` per completed slot, and one
`run_completed` record. Controller Pods do not own result volumes.

When `--csv 1` is enabled, the validated JSONL trace is exported host-side to
`figures/Greedy/` using the Hybrid-compatible wide layout:
`time.csv`, `end_to_end_sla_violations.csv`,
`end_to_end_sla_excess_ms.csv`, `aggregate_utility.csv`, `jain_index.csv`, and
`replica_results.csv`. `aggregate_utility.csv` retains the raw end-to-end
reference-utility meaning for comparison; JSONL retains complete provenance.
CSV generation is downstream of trace validation and must not change policy,
traffic, learning, metrics, or Kubernetes state.

Phase 6 implements this boundary in Greedy-owned modules. The finite controller
emits evidence only after a slot has passed route correlation, selected-only
learning, metric assembly, timing validation, and belief commit. Default
`--parity-replay 0` records requested/performed as false and has no parity
result. `--parity-replay 1` repeats only the pure policy, captured selected
learning, and metric calculation from the already captured public inputs and
telemetry; it performs no HTTP request or stochastic redraw and fails the Job
on divergence.

The host projector keeps the prefixed machine line out of the human console,
validates every record, and writes a one-run lifecycle by atomic replacement.
The start record includes the complete versioned matched-comparison rows,
dimension and seed schemes, runtime-profile fingerprint, warm/build state,
exact service/controller source fingerprints and image IDs, worker
allocatable resources, and the four actual Pod resource envelopes. Each slot
includes final-load-conditioned selected observations, measured pair records,
strict raw-latency SLA arithmetic, phase wall times, application-body/message
footprint when CSV is enabled, and controller CPU/RSS/cgroup-throttling deltas.
Hidden state and physical/observation seeds are rejected from evidence.

CSV export validates the complete JSONL first, rejects duplicate run columns
or malformed retained tables before replacement, and blank-pads unequal run
lengths in metric and footprint tables. Beliefs remain identity-aligned rows.
Controller Pods mount only their public input ConfigMap; result ownership stays
on the host. Source changes invalidate `--skip-build`, preventing retained old
images from being assigned new source provenance.

### Greedy execution-efficiency boundary

Greedy will carry forward only Hybrid optimizations that preserve a sequential
myopic decision stream. The policy object precomputes immutable canonical
replica identities grouped by stage and deterministic `L=2` action ordering
once per configuration. It must not copy Hybrid pruning, activation, lookahead,
or Monte Carlo candidate structures. Deterministic expected stage utility may be
memoized for an exact immutable `(belief vector, projected load)` key within
one finite controller lifetime. Cache use must be transparent to results,
discarded with the controller, covered by cached/uncached equality tests, and
kept bounded or explicitly cleared if the measured key population can grow
beyond the configured experiment envelope. The legacy Greedy Pandas grids,
per-decision distribution construction, and random Monte Carlo expectation are
not part of this path.

The finite controller owns one persistent synchronous Kubernetes discovery
client and one persistent synchronous controller-to-flow-generator client for
all slots. The flow-generator ASGI lifespan owns one persistent asynchronous
first-forwarder client pool. Every public forwarder keeps the accepted separate
local-processor and downstream-forwarder clients, including the matched
30-second downstream/server keep-alive window; all clients close exactly once
on normal exit, partial construction, or failure. Import-safe direct route-
executor tests may use a one-call ephemeral fallback. A slot dispatches its
`N` already-selected routes concurrently, while hops within each route remain
ordered. Placement, load mutation, belief update, and slot commit remain
sequential and canonical.

Reconciliation is change-scoped. Equal topology/profile input is a no-op for
serving Pods; expansion applies only missing highest stages or ordinals;
contraction removes only the declared highest stages or ordinals; and each
bounded batch reaches exact Ready coverage before the next. `--skip-build`
also skips wheelhouse validation, image build/load, and forced serving restart
after validating existing node-local image identities. A normal bootstrap
builds both Greedy images. Later controller-only or service-only maintenance
may build/load only the affected Greedy image when the launcher can prove the
other image and serving template are unchanged.

Greedy records monotonic wall time for Ready discovery, admission/placement,
route dispatch and data-plane wait, feedback/validation, and total slot time.
With `--csv 1`, it exports those phase timings and the compatible controller
payload/message footprint beside the outcome CSVs. These measurements locate
controller or data-plane dominance but do not themselves prove CPU saturation
or a speedup.

Hybrid's process-safe focal-candidate workers and persistent four-process
lookahead pool are deliberately not inherited. Pure Greedy has no independent
candidate tree, and parallel real-flow decisions would observe stale loads and
change the policy. For comparison, however, the Greedy controller receives the
same Kubernetes resource envelope as the active Hybrid controller: request
`2` CPU and `256Mi`, limit `4` CPU and `1Gi`. Greedy remains one sequential
policy process and may consume less of that common ceiling. The matched
envelope participates in worker allocatable-versus-request preflight and may
not be retuned for only one baseline. Any resource experiment must be a
separately versioned, matched Greedy/Hybrid A/B.

### Greedy/Hybrid matched-comparison envelope

`greedy-hybrid-matched-comparison-v1` defines fair comparison as the same
inputs, infrastructure opportunity, runtime conditions, and measurement
boundaries with only policy logic intentionally different. Before implementing
each Greedy phase, inspect the active phase-relevant Hybrid source, manifests,
launcher, and smallest focused tests. Record the exact values and source
versions used; never rely solely on this prose if the active Hybrid boundary
has changed. A detected drift stops that phase until the comparison matrix is
reviewed and versioned.

The matched matrix includes:

| Boundary | Matched Greedy/Hybrid contract |
| --- | --- |
| Experiment shape | 10 flows, 3 configured stages, 5 replicas per stage, fixed `L=2`, one Job/run, and the same positive `max_iterations` |
| Admission | `ceil(N/M)` assigned-flow capacity per replica and identical Ready/capacity interpretation |
| Environment | Exact identity-aligned hidden-state and observation-seed map; equality is proven from the materialized map and fingerprint, not seed spelling |
| Random inputs | Same root-seed and flow-order derivation; physical and observation draws use a shared deterministic key schedule by experiment, slot, flow, stage, replica, load, and component so common inputs agree without entering policy selection |
| Serving Pods | Private processor request/limit `50m/128Mi` and `1 CPU/768Mi`; public forwarder request/limit `25m/128Mi` and `1 CPU/256Mi`; one private worker, two public workers, ports 8081/8080, and 30-second downstream/server keep-alive |
| Flow generator | Request/limit `50m/128Mi` and `1 CPU/768Mi`, the same route concurrency and request-count contract, and the same worker placement |
| Controller | Request `2 CPU/256Mi`, limit `4 CPU/1Gi`, same worker node and cgroup opportunity; Greedy remains sequential and does not copy Hybrid policy workers |
| HTTP/discovery | Same active client ownership, pool limits, request timeouts, discovery timeout/polling, keep-alive, and close-on-failure behavior, frozen from current source during Phases 3--4 |
| Lifecycle | Same rollout-batch value for a paired run, Ready gates, no-op reconciliation, image/build mode, warm/cold state, and retained-Pod conditions |
| Semantics | Same latency laws, learning likelihood, selected-only update, outcome/SLA/fairness/equilibrium rules, and reporting arithmetic |
| Measurement | Same JSONL lifecycle, timing boundaries, controller footprint instrumentation, CSV mode, and parity setting; timed runs use replay off only after forced-replay correctness passes |

Paired evidence records a comparison-profile version, the complete matched
matrix, source/image fingerprints, node allocatable resources, Pod resource
specs, actual controller CPU/RSS/throttling evidence, and every matched or
unmatched field. A comparison fails closed if a required matched value differs.
Exact sample equality is required for shared deterministic inputs; if divergent
routes make an observation inapplicable to one policy, evidence records that
fact rather than pretending both policies observed the same selected hop.

Intentional differences are limited to the policy: Greedy has no Hybrid
pruning, activation, planning-link selection term, lookahead, Monte Carlo,
candidate counts/depths, `--policy`, `--mc-workers`, or process pool. Those
arguments are absent rather than assigned artificial neutral values. Different
actual CPU time, memory use, and wall time under the common resource envelope
are comparison outputs, not configuration drift.

### Greedy implementation intelligence guidance

The roadmap's recommended intelligence level is user-facing guidance for
choosing a Codex reasoning-effort tier when starting that phase. It is not an
agent prerequisite or check, and the agent does not inspect, verify, enforce,
or change the user's model selection. It is also not a Greedy runtime setting,
Kubernetes resource, algorithm parameter, acceptance result, or authorization
to continue into the next phase. Model IDs are deliberately not frozen because
availability and product defaults can change.

The recommendation uses `high` for bounded work whose contract is already
explicit but still benefits from careful reasoning. It uses `xhigh` when an
error could silently change policy mathematics, retained state, concurrency or
lifecycle ordering, dynamic-topology safety, cross-baseline conclusions, or
final evidence interpretation. The user may choose a different level at any
time; no explanation or handoff update is required.

The planned allocation is `high` for Phases 0, 4, 6, and 8, and `xhigh` for
Phases 1, 2, 3, 5, 7, and 9. These labels are informational only. Live
authorization, destructive-action safeguards, focused tests, and human review
remain governed by their existing contracts rather than the selected level.

### Greedy Phase 0 executable contract boundary

Implemented locally and corrected after user clarification: 2026-08-24.
`Greedy/phase0_contract.py` is the non-production executable source for
`pure-greedy-budgeted-l2-v1` ambiguities. It validates positive arbitrary `N`
and uniform `M`, contiguous `K>=2` configured stages, `ceil(N/M)` capacity,
two distinct selected stages, `K-2` bypasses, projected load `current + 1`,
canonical joint-action ties, best-feasible non-positive selection, explicit
empty-feasible failure, and exactly two load increments per sequential flow
decision. Its canonical slot fixture fixes deterministic flow order, `N`
two-hop actions, `2*N` selected observations, and `N` selected-pair records.
This is a small Phase 1 oracle, not the production policy or runner.

The executable canonical matched-comparison fixture is explicitly
`N=10`, `K=3`, and `M=5`, which implies capacity two per replica, ten complete
two-hop routes, twenty selected observations, ten selected-pair records, and
one bypassed stage per flow. It is a comparison input, never a runtime default.
A separate `3x3x2` hand-checked slot fixture remains intentionally tiny and is
also not a default. The invocation contract is exactly one run and explicitly
excludes a `--runs` repetition option.

The policy-visible fixture schema contains only flow/stage/replica identity,
readiness, admission capacity, belief, and current load. Hidden state, profile
seed, physical and observation seeds, planning-link cost, and measured pair
latency are explicitly forbidden selection inputs. The contract excludes
recursion, future-flow simulation, pruning, local search, lookahead, Monte
Carlo, bandits, MILP, link-aware selection, and future-flow objectives. The
fixed two-stage budget is part of the action schema rather than an excluded
algorithm.

`Greedy/legacy_characterization.py` parses the seven historical Python sources
without importing them. It records import-time executable statements in
`main.py`, `test.py`, and `header.py`; the first is the unsafe experiment, the
second reads and rewrites SLA CSV data, and the third changes the process
recursion limit. The bounded characterization records the retired
`range(1,30)` outer loop, 50 flows, three stages, 80 replicas per stage (240
total), active
`is_budgeted=1`, mixed global Python/NumPy randomness plus unseeded UUIDs, no
explicit seed call, and direct
CSV/file behavior. Tiny tests separately demonstrate that the active budgeted
selector returns exactly two stages and that the dormant per-stage selector's
zero sentinel makes `embedding` mutate the final replica load through Python's
negative index.

All 38 top-level legacy functions and `Replica` methods have an explicit
disposition: five reuse only the active shared behavior with compatibility
tests, fourteen remain historical reference, and nineteen retire. "Reuse" never
means importing the unsafe driver or copying its stale formula. In particular,
the historical inverse-latency utility, random 30-sample grids, single
truncated-normal likelihood, state-based SLA, 15-ms link-latency excess,
strict `<0.06` equilibrium, direct wide CSV mutation, and trend-filled SLA data
do not define the new baseline.

The frozen Greedy/Hybrid compatibility matrix is:

| Component | Phase 0 disposition | Greedy boundary |
| --- | --- | --- |
| Physical jitter, observation jitter, and exact convolved likelihood | Reuse | Pure functions from `IBG.latency_model` |
| Belief-driven expected stage utility | Adapt | Greedy-owned thin adapter over `IBG.latency_model`; do not depend on a Hybrid policy namespace |
| Selected-only posterior aggregation | Reuse | `IBG.learning` and frozen IBG replica update behavior |
| Physical-only outcome selection | Reuse | `IBG.outcome_latency` |
| Raw-chain SLA count and unrounded excess above 80 ms | Adapt | Greedy-owned selected-two-hop metric assembly; reuse `IBG.report.SLA_v` for count |
| Jain fairness | Reuse | Active `IBG.header.jain_index` with compatibility tests |
| Strict `<0.04` equilibrium | Adapt | Explicit-threshold Greedy call to the active IBG predicate |
| Route, observation, and pair schemas | Adapt | Greedy-owned budgeted `L=2` schema compatible with Hybrid's action shape but not its policy fields |
| Flow-order isolation | Adapt | Greedy-owned explicit order, independent of policy/profile RNG streams |
| Hybrid pruning/lookahead/MC/pair-aware policy | Exclude | No Greedy dependency |
| Legacy budgeted and stochastic-grid solvers | Exclude | `L=2` shape is reference-only; implementation is not reused |

Active compatibility constants are fixed at physical scales
`6/5.25/4/3.25` ms, observation scales `7.2/6.3/4.8/3.9` ms,
`physical-only-v1` realized utility, selected-hop-only learning, measured raw
consecutive pairs, strict raw end-to-end latency greater than `80.0` ms,
unrounded SLA excess, Jain fairness, and strict maximum belief change below
`0.04`. Every completed flow contributes two selected observations and one raw
selected-pair record. Pair telemetry remains post-selection, and profile seed
cannot enter the policy calculation.

### Greedy Phase 1 pure policy boundary

Implemented locally: 2026-08-24. `Greedy/contracts.py` owns immutable explicit
dimension, identity, public replica, canonical load, admission, two-stage
action, decision, and complete policy-result contracts. `GreedyConfiguration`
has no topology defaults: callers must provide positive `N`, `K`, and `M`, with
`K>=2`; `L=2` is a class-level invariant. The explicit 10x3x5 configuration is
available only through the canonical matched-comparison fixture.

`Greedy/policy.py` constructs stage-major replica identities, immutable
per-stage groups, and globally lexicographically sorted complete two-stage
actions once per policy object. One real flow evaluates every feasible action
using public Ready state, current load, declared `ceil(N/M)` capacity, and
public belief. Each stage score uses projected load `current+1`; strict
improvement over the pre-sorted actions implements the exact lowest-action tie
rule. Both chosen loads are committed before the next supplied flow ID.
Results contain all `N` actions, their `K-2` bypasses, the complete sequential
load chain, and final loads without mutating caller inputs. Empty feasibility
raises `NoFeasibleActionError`; non-positive scores remain eligible.

`Greedy/expected_utility.py` is the Greedy-owned thin adapter over the pure
`IBG.latency_model.expected_state_utility` function. It reconstructs no
distributions and draws no samples. Its controller-lifetime LRU has an exact
`(belief tuple, projected load)` key, a 4096-entry default bound, explicit
clear operation, and result-transparent cached/uncached behavior. The policy
imports no Hybrid namespace, RNG, pruning, activation, planning-link,
lookahead, Monte Carlo, or process-pool code.

`Greedy/comparison.py` owns the typed
`greedy-hybrid-matched-comparison-v1` fixture. It records the explicitly
supplied 10x3x5/L2 comparison, `ceil(10/5)=2` capacity, required profile/seed,
runtime/lifecycle/measurement equality, current serving and controller
resources, and separately enumerated policy-only differences. Construction
fails on a missing, reordered, or unequal required row and on a claimed
intentional difference whose values are equal. Runtime manifests and
stochastic scheduling remain later phases; this fixture does not implement
them.

Phase 1 revalidated its relevant Hybrid sources at repository HEAD
`19229c274038db440f3cfdd62ed2102ea4c2c545`. No recorded Phase 1 comparison
value drifted. Exact audited source versions were:

| Boundary | Active source location | Git blob |
| --- | --- | --- |
| Deterministic belief utility | `IBG_Hybrid/expected_utility.py:12-42` | `ae323e521a73fe9d4c430ce947acb670c2c784de` |
| Identity, action, and load ordering | `IBG_Hybrid/contracts.py:17-171` | `4f50cb74b56f3739a9dba1be59b80091f8f20732` |
| Public Ready/capacity feasibility | `IBG_Hybrid/phase0_contract.py:232-289` | `45eb84512efa7457648ae8667b30e7f83f25f304` |
| Precomputation, utility cache, and strict ties | `IBG_Hybrid/policy.py:1240-1555` | `610ab606cdd14548abfcf2fd5b8c4bef97f72b78` |
| `ceil(N/M)` topology capacity | `IBG_Hybrid/kernel_profile_expansion.py:587-600` | `8f10eb51ac4fce23a693ccda783f5828f60422d2` |
| Processor/forwarder ports, workers, keep-alive | `IBG_Hybrid/kernel_infrastructure_contract.py:490-527` | `b4b2d651c7903abc7f735983a0cd106e4b75f98b` |
| Serving Pod resources | `deploy/hybrid-kubernetes/replicas.yaml:46-110` | `830abdb9bbe908c74a43ba2437d0d0aef88c4809` |
| Flow-generator resources | `deploy/hybrid-kubernetes/flow-generator.yaml:35-57` | `32ec288eeceef9c47ec5f80bcaa294716ac5f4be` |
| Controller resources | `deploy/hybrid-kubernetes/dynamic-controller-job.yaml:19-66` | `1e4dbde99f3d76ee529192aae624a6ec87a05f61` |
| Required production dimensions and controls | `scripts/run_hybrid_kernel_phase4.py:3400-3534` | `c571940408423410df91480470a79f0007a0f68e` |

The active Hybrid typed configuration still has its historical 20x3x10
defaults and fixed three-stage boundary, while its production launcher requires
explicit dimensions. Neither becomes a Greedy default. For the canonical
comparison both launchers receive 10x3x5 explicitly; Hybrid's optional
`--runs`, policy/depth/MC controls, link-aware pruning, lookahead action tree,
and process workers remain intentional exclusions.

### Greedy Phase 2 stateful pure experiment boundary

Implemented locally: 2026-08-25. `Greedy/slot_contracts.py` now owns immutable
simulation-only replica profiles, raw pair inputs, slot inputs, selected
observations, measured pairs, belief snapshots, placements, metrics, phase
timings, slot results, and one-experiment results. A slot input keeps public
`PublicReplicaState` values separate from the hidden-state/observation-seed
profile map. Only the public tuple is passed to `GreedyPolicy`; hidden state,
profile seed, component seeds, and pair telemetry remain outside selection.
The canonical materialized profile fingerprint covers sorted
`(stage, replica, hidden_state, observation_seed)` entries, so equal
`--profile-seed` spelling alone does not establish environment equality.

`Greedy/simulation.py` owns the pure selected-route execution port. Explicit
flow order is preserved byte-for-byte. Otherwise
`blake2b-hybrid-flow-order-v1` uses the active Hybrid root/slot payload and a
local `random.Random`, never global RNG state. Physical and observation draws
use separate local NumPy generators. Their immutable key contains experiment,
slot, flow, stage, replica, final assigned load, and component. Because every
launcher invocation is one experiment, canonical `experiment_id=1` preserves
the active Hybrid physical/observation seed bytes exactly; noncanonical pure
fixture IDs add an explicit experiment namespace to prevent cross-experiment
aliasing. `profile_seed` and the recorded profile observation seed are not draw
seeds. Only committed replicas are sampled, and the exact convolved learning
likelihood comes directly from `IBG.latency_model`.

`Greedy/runner.py` resolves one flow order, calls the unchanged Phase 1 policy
once, preserves its decision/load sequence as placement records, executes only
the selected actions, and validates exactly `2*N` final-load observations and
`N` selected-pair records before learning. `Greedy/learning.py` reuses
policy-neutral `IBG.learning.apply_observations` through a minimal Greedy-owned
replica target that preserves the frozen three-decimal posterior and `0.8`
retention/aggregation behavior without importing unsafe legacy Greedy code or
the side-effectful Exact header during ordinary package import. Beliefs for
idle replicas remain unchanged and learned snapshots feed the next slot.

`Greedy/metrics.py` evaluates every selected expected stage value against the
slot's final assigned load and does not deduct a planning-link coefficient.
Physical realized utility uses only selected physical processing latency.
Exactly one measured selected-pair latency per flow is added only to raw
end-to-end latency and deducted only from the raw reference utility. The SLA
is strict raw latency `>80.0` ms with unrounded positive excess. Jain fairness
matches the active Exact rounding/formula without mutating caller maps, and
equilibrium is true only when every belief entry changes by strictly less than
`0.04`. Injected monotonic clocks divide the slot into placement and
feedback/validation durations whose sum is total pure-slot time.

`run_greedy_experiment` owns one persistent policy object and one simulation
adapter for exactly one experiment call. It retains beliefs across consecutive
slot IDs, returns immediately on equilibrium, or returns after exactly the
explicit positive maximum iteration count. It prints and writes nothing and
has no repetition, HTTP, container, Kubernetes, JSONL, or CSV boundary.
`Greedy/oracle.py` is an explicit validation-only path: it independently
enumerates the immediate canonical policy, then replays already-captured
observations/pairs with cache disabled. It never redraws stochastic inputs and
compares placements, load changes, beliefs, and metrics while excluding only
wall-clock/provenance differences caused by supplying the captured order.
Ordinary slot execution does not import or invoke this oracle and therefore
does not duplicate the solve.

Phase 2 revalidated its comparison rows at repository HEAD
`19229c274038db440f3cfdd62ed2102ea4c2c545`. The audited active sources were:

| Boundary | Active source location | Git blob |
| --- | --- | --- |
| Flow-order scheme and derivation | `IBG_Hybrid/phase0_contract.py:31,493-506` | `45eb84512efa7457648ae8667b30e7f83f25f304` |
| Selected physical/observation seed payload and simulation | `IBG_Hybrid/simulation.py:21-163` | `1b9f59f208885874b57e06e1d92fcabeeccc2db4` |
| Slot/profile/observation/pair/result schemas | `IBG_Hybrid/slot_contracts.py:59-420` | `845c761490e772f376811deaa4449a03912138c1` |
| Exact selected-result validation, learning, and metrics | `IBG_Hybrid/runner.py:192-400,504-638` | `b60ddcc0c7d55d7c6d3cc55e2308c194d24389c3` |
| Policy-neutral selected-only dispatch | `IBG/learning.py:4-15` | `ca15eba6e423643658d752046c010e18f13b2dd4` |
| Separated jitter and exact convolved likelihood | `IBG/latency_model.py:95-283` | `f082cf3600b6d17f9a879ae807235a11f450a72f` |
| Physical utility, posterior, aggregation, equilibrium, and Jain behavior | `IBG/header.py:48-129,211-220,329-336` | `17d10aa18213e102b71bc0f951a418fd46a09b90` |
| Strict SLA count helper | `IBG/report.py:6-13` | `1a592e0af8c2fb28ae82f0c8c4e74a9fcbf62c52` |
| Hybrid tiny continuation oracle (excluded) | `IBG_Hybrid/oracle.py:26-137` | `e6a34f18cc66aa3513717de302406fc0455da839` |

Reuse is limited to `IBG.latency_model`, `IBG.learning.apply_observations`,
`IBG.report.SLA_v`, and the Phase 1 policy-neutral expected-utility adapter.
Greedy-owned adaptations cover schemas, public/environment separation,
profile fingerprinting, flow/stochastic key orchestration, the import-safe
learning target, final-load metric assembly, timing, stopping, and captured
replay. Hybrid activation, planning-link selection, candidate accounting,
lookahead/Monte Carlo execution, process pools, and its recursive continuation
oracle are excluded. No Phase 2 mathematical constant drift was found. The
only source-shape distinction is Hybrid's lack of an explicit experiment field
in its one-experiment component payload; Greedy preserves exact Hybrid bytes
for canonical experiment 1 and versions the extension for noncanonical pure
fixtures.

### Greedy Phase 3 Kernel/HTTP and finite-controller boundary

Greedy Phase 3 is complete locally. The new import-safe boundary consists of
`Greedy/kernel_contracts.py`, `kernel_kubernetes_discovery.py`,
`kernel_route_contracts.py`, `kernel_route_execution.py`,
`kernel_flow_generator.py`, `kernel_processor_service.py`,
`kernel_route_forwarder.py`, `kernel_route_forwarder_service.py`,
`kernel_controller_config.py`, `kernel_controller.py`,
`kernel_controller_service.py`, and `kernel_oracle.py`. It creates no image,
manifest, namespace, cluster, launcher, JSONL, or CSV boundary.

Discovery owns one synchronous namespace-scoped HTTP client for the complete
finite-controller lifetime. An accepted snapshot contains exactly every
configured contiguous `(stage, replica)` identity in canonical order, public
Running/Ready state, declared `ceil(N/M)` assigned-flow capacity, Pod/UID/node
identity, ownership labels, and the public-forwarder endpoint. Missing,
duplicate, unexpected, non-Ready, foreign, or malformed entries fail the
snapshot. Hidden state and runtime seeds have no discovery or public policy
field. The controller combines the accepted snapshot with its retained belief
map to construct exact `PublicReplicaState` values.

Each slot resolves the explicit or versioned flow order and calls the existing
Phase 1 policy exactly once. All `N` immediate Greedy decisions and both load
increments per flow finish before traffic begins. The route command is one
controller-to-flow-generator `/run-slot` request containing explicit `N/K/M`
and `N` canonical complete routes. Every route contains exactly two
increasing-stage selected hops, final assigned loads, explicit route positions
and next-hop correlation, and the complete `K-2` bypass tuple. The
flow-generator then starts exactly `N` first-forwarder requests concurrently;
each request contains the complete already-selected remaining hop, and each
individual route processes its two hops in order. Bypassed and idle replicas
have no request or telemetry representation.

Successful flow telemetry contains exactly two selected physical/learning hop
records and one separately named measured selected-pair record. Validation
checks slot, flow, stage, replica, final load, route position, next hop, Pod,
endpoint, separated physical/observation signal identity, exact convolved
likelihood, and pair endpoints before learning. A missing, duplicate, partial,
mismatched, or failed result fails the whole slot; there is no retry,
imputation, partial learning, partial commit, or rejection sentinel. Beliefs
are assigned back to controller state only after complete validation,
selected-only learning, metrics, timings, and result construction succeed.
HTTP results never alter the already-completed policy result.

The controller retains one synchronous discovery client and one synchronous
flow-generator client across all slots. The flow-generator ASGI lifespan owns
one asynchronous first-forwarder pool. Direct executor calls alone may create
one ephemeral client and close it after that call. Every public forwarder owns
two distinct asynchronous clients: the local private-processor client retains
the processor-compatible default idle behavior, while the downstream
forwarder client retains the 30-second keep-alive. Controller construction,
finite experiment completion, request/slot failure, ASGI startup/shutdown, and
explicit repeated close paths have exactly-once cleanup coverage. The
controller request timeouts remain 10 seconds for Kubernetes discovery,
30 seconds for controller-to-flow-generator, and 10 seconds for both
flow-generator-to-first-forwarder and public-forwarder requests.

Kernel slots reuse the Phase 2 selected-only learner and metric assembly.
Predicted utility uses pre-learning beliefs and final loads; physical realized
utility uses physical processing only; observation jitter enters only the
learning signal; measured pair latency enters only raw end-to-end latency and
the raw reference utility; SLA remains strict raw latency `>80.0` ms with
unrounded excess; Jain fairness and strict per-entry equilibrium `<0.04`
remain unchanged. The finite controller retains beliefs and one Greedy policy
cache, runs one experiment, and stops at equilibrium or exactly the explicit
positive maximum iteration count.

Injected monotonic boundaries record discovery, admission/placement, route
dispatch, data-plane wait, feedback/validation, and total slot time. The
existing Phase 2 placement and feedback timings remain available as their
semantic sub-boundaries. Timing never enters selection, learning, metrics,
SLA, fairness, or stopping. `Greedy/kernel_oracle.py` explicitly reconstructs
the same public pure input and replays the already-captured observations and
pairs with no HTTP and no stochastic draw. It compares placements, load
changes, observations, beliefs, utilities, SLA, fairness, and equilibrium,
excluding runtime provenance and wall-clock timing. Normal controller code
does not import or invoke replay and therefore does not double-solve.

Phase 3 revalidated the Hybrid comparison boundary at repository HEAD
`19229c274038db440f3cfdd62ed2102ea4c2c545`:

| Boundary | Active source location | Git blob | Greedy disposition |
| --- | --- | --- | --- |
| Ready discovery and persistent sync API client | `IBG_Hybrid/kernel_kubernetes_discovery.py:32-245` | `b654bbc16eaaaf0e0613d60a2ebc98fff75a0ebc` | Adapt behind Greedy identity/ownership types |
| Finite controller and persistent generator client | `IBG_Hybrid/kernel_controller.py:56-134,215-334,361-559` | `b9408745de6175316481a47915423d16c9b1aea8` | Adapt lifecycle/validation; exclude Hybrid policy/pools |
| Public controller input document | `IBG_Hybrid/kernel_controller_config.py:22-118` | `f47ca640ec55cf4b4a199dd708f5a6e1a76e5163` | Adapt without planning links or hidden inputs |
| Controller executable boundary | `IBG_Hybrid/kernel_controller_service.py:20-66` | `a9bff39c735e89fa7e39a1206af4ab0c6819d9fb` | Adapt without console/policy modes |
| Two-hop request/telemetry schemas | `IBG_Hybrid/kernel_route_contracts.py:32-304` | `c8b54d0183f6cabdc5640c9d875dbe67d43bc838` | Adapt from fixed K=3 to arbitrary K and explicit correlation |
| Concurrent selected-route executor | `IBG_Hybrid/kernel_route_execution.py:28-291` | `aba1b3990a27b94229d576d2f0c20f2b88e524e7` | Adapt persistent pool, N-way concurrency, and fail-whole-slot rules |
| Flow-generator ASGI lifecycle | `IBG_Hybrid/kernel_flow_generator.py:23-87` | `b60183e4bd3ce3b0565cb6754fc6ece9cd2e6e59` | Adapt behind Greedy service/version types |
| Private processor wrapper | `IBG_Hybrid/kernel_processor_service.py:18-59` | `ecb1c8fb539deea1429bd114c6821c20682b7b0e` | Reuse policy-neutral processor service behavior |
| Strictly later selected-hop forwarder | `IBG_Hybrid/kernel_route_forwarder.py:15-38` | `6d1e044a7ab94c3c117c7f810febaeb46da6de3b` | Adapt without Hybrid's stage-3 ceiling |
| Forwarder ASGI wrapper | `IBG_Hybrid/kernel_route_forwarder_service.py:15-23` | `01c77ea880b95fcd9ca4d5ad809cd5663bb49b93` | Adapt with Greedy runtime ownership |
| Shared processor and forwarder behavior | `testbed/cnf_service.py:29-523`; `testbed/route_forwarder.py:29-78,590-625,761-885,1161-1253` | `7717aa7d35498491d3659d8ed7d79b589cac1c9b`; `c112ba0d54cf3cb27a1997ed4c3312e52c2eebaf` | Reuse ports, separated telemetry, ordered forwarding, and client split |
| Worker/client/port reuse contract | `IBG_Hybrid/kernel_infrastructure_contract.py:490-535` | `b4b2d651c7903abc7f735983a0cd106e4b75f98b` | Adapt exact runtime assumptions |
| Private/public serving resources | `deploy/hybrid-kubernetes/replicas.yaml:45-110` | `830abdb9bbe908c74a43ba2437d0d0aef88c4809` | Audit now; implementation remains Phase 4 |
| Flow-generator resources | `deploy/hybrid-kubernetes/flow-generator.yaml:35-57` | `32ec288eeceef9c47ec5f80bcaa294716ac5f4be` | Audit now; implementation remains Phase 4 |
| Controller resources | `deploy/hybrid-kubernetes/dynamic-controller-job.yaml:64-66` | `1e4dbde99f3d76ee529192aae624a6ec87a05f61` | Audit now; implementation remains Phase 4 |

No Phase 3 matched timeout, port, worker, keep-alive, request-count,
telemetry-count, or resource value drifted. Current Hybrid manifests remain:
private processor request/limit `50m/128Mi` and `1 CPU/768Mi`, public
forwarder `25m/128Mi` and `1 CPU/256Mi`, flow generator `50m/128Mi` and
`1 CPU/768Mi`, and controller `2 CPU/256Mi` and `4 CPU/1Gi`; one private
worker, two public workers, ports 8081/8080, and a 30-second downstream/server
keep-alive. These resources are audit data only until Greedy Phase 4.

Reuse is limited to the policy-neutral processor/forwarder and Phase 2
learning/metric behavior. Greedy-owned adaptations cover discovery ownership,
arbitrary-K routes, wire correlation, concurrent dispatch, lifecycle, finite
controller orchestration, timings, and replay. Hybrid pruning, activation,
planning-link selection, lookahead, Monte Carlo, candidate/depth/worker
options, process pools, diagnostics/output, and repetition modes remain
excluded.

### Greedy Phase 4 static image and Kubernetes boundary

Greedy Phase 4 is complete locally. `Greedy/kernel_runtime_profiles.py`
defines the complete canonical processor-private profile document. The private
processor resolves its `(stage, ordinal+1)` entry through
`GREEDY_RUNTIME_PROFILES_PATH`; hidden state and observation seed never enter
the controller document or policy input. `Greedy/kernel_infrastructure.py`
owns explicit-dimension static input validation, exact matched resources,
worker resource preflight, deterministic Kubernetes resource construction,
security validation, readiness-gated controller Job construction, and
dependency-free JSON/YAML rendering/parsing. These modules import silently and
perform no file, container, network, or cluster action.

The long-running resource graph is:

```text
greedy-testbed Namespace
  -> greedy-controller ServiceAccount + Pod get/list Role/RoleBinding
  -> greedy-runtime-profiles ConfigMap (processor-private hidden map)
  -> greedy-controller-inputs ConfigMap (public finite-run inputs/fingerprint)
  -> greedy-flow-generator Service + one Deployment
  -> for every explicit stage 1..K
       greedy-stage-S headless Service
       greedy-stage-S StatefulSet with M Pods
         private-processor :8081, one worker
         public-forwarder  :8080, two workers, 30s keep-alive

exact replica Ready coverage + Ready flow generator
  -> separately rendered finite greedy-controller Job
```

All serving and controller Pods select the sole
`greedy.workload-node=true` worker. Replica and flow-generator Pods disable
service-account token mounting; only the controller Job mounts its
namespace-scoped discovery token. Pod security uses UID/GID 10001,
`runAsNonRoot`, runtime-default seccomp, no privilege escalation, a read-only
root filesystem, and all Linux capabilities dropped. The controller mounts
only `greedy-controller-inputs`; runtime profiles mount only into private
processors. The long-running render can never contain a Job, while controller
Job construction fails without exact canonical Ready identities and a Ready
flow generator.

The deterministic renderer accepts arbitrary explicit `N`, `K>=2`, and `M`.
It creates exactly `K` headless Services and StatefulSets and labels every
replica Pod with `greedy.max-assigned-flows=ceil(N/M)`. JSON was selected as
the emitted format because it is valid Kubernetes YAML and permits strict
offline parse/round-trip validation without adding a YAML library to either
image. `scripts/render_greedy_kubernetes.py` renders only long-running or kind
documents to stdout after validation; it cannot apply them. The explicit
10x3x5 example under `deploy/greedy-kubernetes/examples/` is a comparison
fixture, not a topology default.

`deploy/greedy-kubernetes/Dockerfile.service` copies only policy-neutral IBG
latency/datapath code, shared processor/forwarder code, and Greedy service wire
modules. It excludes Greedy policy, controller, oracle, legacy driver,
Hybrid, MILP, Pandas, SciPy, and optimization sources. The separate controller
image copies the sequential Greedy policy/controller/learning/metric boundary
and a lean strict-SLA helper, but no service entry point, Hybrid solver,
lookahead, Monte Carlo, or process-pool source. Both images use Azure Linux
Python 3.12, install only exact local wheel locks through `--no-index`, and
finish as UID/GID 10001. `scripts/greedy_offline_wheelhouse.py` validates the
Greedy-owned CPython 3.12 Linux/AMD64 manifests and rejects missing,
unexpected, forbidden-solver, ABI/platform, lock, and recorded-digest drift.

The matched workload resources are unchanged:

| Workload | Request | Limit |
| --- | --- | --- |
| Private processor | `50m`, `128Mi` | `1` CPU, `768Mi` |
| Public forwarder | `25m`, `128Mi` | `1` CPU, `256Mi` |
| Flow generator | `50m`, `128Mi` | `1` CPU, `768Mi` |
| Sequential Greedy controller | `2` CPU, `256Mi` | `4` CPU, `1Gi` |

For configuration `N/K/M`, worker request preflight counts `K*M` replica Pods,
the flow generator, and the simultaneously running finite controller. The
explicit 10x3x5 example therefore requires 3175 millicores and 4224 MiB before
system reservation/other workloads are considered. This is request
admission—not a claim about actual consumption or performance.

Phase 4 revalidated the active Hybrid/static boundary at repository HEAD
`f2e0065204570d9631f26953c94729b451ff92b5`:

| Boundary | Active source | Git blob | Greedy disposition |
| --- | --- | --- | --- |
| Service image | `deploy/hybrid-kubernetes/Dockerfile.service:1-38` | `bdb6333a189a8b5a18ad693fd90654b174b32ed5` | Adapt lean contents and ownership |
| Controller image | `deploy/hybrid-kubernetes/Dockerfile.controller:1-43` | `9c528adffa91311f9eb18582584189b65303a5b4` | Adapt; exclude Hybrid policy/pools |
| Offline wheel validation | `scripts/hybrid_offline_wheelhouse.py:1-230` | `412e66c89df29b1ea304a2a60fa379b5f981c3b2` | Adapt to Greedy manifests/cache |
| Namespace/RBAC | `deploy/hybrid-kubernetes/namespace.yaml`; `rbac.yaml` | `f1a892dafcfac954e0ae5820ca950975f95a2b0a`; `e5599da43f04a8d0d55b2dd54e1b4a492cb68b62` | Adapt names; preserve Pod get/list only |
| Replica template | `deploy/hybrid-kubernetes/replicas.yaml:1-286` | `830abdb9bbe908c74a43ba2437d0d0aef88c4809` | Adapt to arbitrary explicit K/M and Greedy profiles |
| Flow generator | `deploy/hybrid-kubernetes/flow-generator.yaml:1-57` | `32ec288eeceef9c47ec5f80bcaa294716ac5f4be` | Adapt ownership; preserve runtime envelope |
| Controller Job | `deploy/hybrid-kubernetes/dynamic-controller-job.yaml:1-75` | `1e4dbde99f3d76ee529192aae624a6ec87a05f61` | Adapt without planning/source overlays |
| Long-running separation | `deploy/hybrid-kubernetes/kustomization.yaml:1-20` | `2e4fcdfdf039837d74d57c9919b44a4a192e297e` | Adapt to deterministic renderer |
| One-worker kind topology | `deploy/hybrid-kubernetes-phase4-small/kind-config.yaml:1-8` | `e756783e3923bf87d69b9df2dc0df613ea1ba727` | Adapt worker label only |
| Runtime constants | `IBG_Hybrid/kernel_infrastructure_contract.py:490-535` | `b4b2d651c7903abc7f735983a0cd106e4b75f98b` | Reuse exact ports/workers/keep-alive |

No Phase 4-relevant value drifted. Phase 4 added no launcher, image build,
kind/kubectl operation, live discovery, topology reconciliation, JSONL, CSV,
or console evidence. Those remain later phases.

### Greedy Phase 5 persistent lifecycle and dynamic topology boundary

Greedy Phase 5 is complete locally. `scripts/run_greedy_kernel.py` is the
single production entry point for `run`, read-only `preflight`, and explicit
Greedy-only `cleanup`. It requires explicit `N/K/M`, maximum iterations, and
profile seed, resolves one positive experiment root independently of the
profile seed, and creates exactly one controller Job. There is no topology
default or repetition mode. The accepted `--csv` and `--parity-replay`
settings are validated and carried in launch configuration only; Phase 5 does
not persist or print experimental evidence.

`Greedy/kernel_profile_reconciliation.py` deterministically materializes the
complete processor-private map. Its keyed 3/3/2/2 state allocator and canonical
observation-seed prefix match the active Hybrid environment allocation, while
its append-only extension supports arbitrary contiguous stages and replicas.
The profile seed never enters the flow-order/root seed or policy. A transition
is valid only when every retained identity has the same hidden state and
observation seed, the requested document has the expected fingerprint, and
removed identities are high suffixes. Only processors receive this map.

`Greedy/kernel_rollout.py` converts owned StatefulSet state into a strict
contiguous topology and constructs bounded replica batches plus highest-stage
add/remove steps. Exact Running/Ready Pod identities and public admission
capacity, together with one Ready flow generator, gate every mutation. An
interrupted transition can continue only when the versioned launcher state
names the exact stable and target configurations and the observed state is an
unambiguous prefix between them. Missing markers, ordinal holes, inconsistent
stage widths, foreign ownership, or malformed labels fail closed.

`Greedy/kernel_lifecycle.py` implements the state machine:

```text
validate launch/profile inputs
  -> validate wheelhouses before Docker unless --skip-build
  -> inspect exact cluster/context/node/namespace ownership
  -> validate worker allocatable against requested serving + one controller
  -> validate or change-scope service/controller image provenance
  -> record an owned stable-to-target transition marker
  -> remove obsolete highest stages/replicas
  -> project retained processor-private profiles and public inputs
  -> add highest stages and bounded replica suffixes
  -> require exact Ready coverage after every batch
  -> validate retained Pod UID/restart identity when no service restart occurs
  -> record stable state
  -> replace only the previous owned finite controller Job
  -> wait for that one Job to complete
```

Fresh bootstrap builds both images offline with `--pull=false` and
`--network=none`, creates only cluster `greedy`, waits for exactly
`greedy-control-plane` and labeled `greedy-worker`, applies Greedy-owned
long-running resources, and then creates the Job. Existing valid clusters are
reused. Equal topology/profile is a serving no-op; flow-only changes patch the
public capacity/controller configuration without replacing Pods. Replica and
stage contraction remove only highest suffixes. `--skip-build` is forbidden on
a fresh cluster, skips wheel/build/load, validates exact retained local and
node image IDs, and avoids a forced restart. Cleanup first performs the same
ownership preflight and deletes only the dedicated Greedy kind cluster.

Phase 5 revalidated the active Hybrid lifecycle boundary at repository HEAD
`f2e0065204570d9631f26953c94729b451ff92b5`:

| Boundary | Active source | Git blob | Greedy disposition |
| --- | --- | --- | --- |
| Cluster, build, resource, lifecycle, seed, and CLI ordering | `scripts/run_hybrid_kernel_phase4.py:65-170,268-690,1041-1190,2534-3150,3224-3333,3400-3598` | `c571940408423410df91480470a79f0007a0f68e` | Adapt under Greedy ownership; exclude series/policy/MC/netem/evidence controls |
| Bounded replica rollout and Ready checks | `IBG_Hybrid/kernel_rollout.py:194-375` | `2a766eb47c1149570b01999335d1cb56772709ff` | Adapt from fixed stages to arbitrary contiguous `K` |
| Profile allocation and retained-prefix validation | `IBG_Hybrid/kernel_profile_expansion.py:407-991` | `8f10eb51ac4fce23a693ccda783f5828f60422d2` | Adapt the environment-only allocator behind Greedy ownership |
| Offline wheelhouse validation | `scripts/hybrid_offline_wheelhouse.py:1-230` | `412e66c89df29b1ea304a2a60fa379b5f981c3b2` | Reuse through the Greedy Phase 4 validator |
| One-control-plane/one-worker kind shape | `deploy/hybrid-kubernetes-phase4-small/kind-config.yaml:1-8` | `e756783e3923bf87d69b9df2dc0df613ea1ba727` | Adapt names and worker label |

No Phase 5-relevant ordering, resource, profile, image, or Ready-gate drift was
found. Hybrid policy/pruning/lookahead/Monte Carlo/process-pool behavior,
repetition, evidence, and unrelated baseline lifecycle targets remain excluded.
All Phase 5 execution coverage uses injected fake command executors; no live
container or Kubernetes action is part of this completed gate.

### Greedy Phase 7 local integration boundary

Greedy Phase 7 completed locally on 2026-08-27 without changing the Phase 1
policy, Phase 2 mathematics, Phase 3 HTTP/controller boundary, Phase 4
resources/manifests, Phase 5 lifecycle, or Phase 6 evidence schemas. The new
`tests/test_greedy_phase7.py` layer composes the already-owned boundaries as a
single offline acceptance gate instead of adding another runtime component.

The integration gate exercises explicit `3x2x1`, `5x2x2`, and `5x4x3`
configurations. For every shape it proves complete sequential L2 placement,
`2*N` total load assignments, `ceil(N/M)` admission, `K-2` bypasses,
cached/uncached equality, bounded cache size, complete processor-private
profiles, deterministic long-running/controller renders, parse round trips,
and the one-control-plane/one-worker kind document. Existing Phase 0--6 tests
remain the detailed gates for fake lifecycle transitions, persistent clients,
route concurrency with ordered hops, replay, metrics, JSONL, CSV, security,
and ownership.

Controller resource sampling is explicitly regression-bound as semantically
inert: two finite fake-adapter experiments with identical public inputs and
telemetry produce identical placements, loads, beliefs, utilities, SLA,
fairness, equilibrium, and stop reason whether CPU/RSS/cgroup throttling
snapshots are collected or absent. Only the optional resource result field
differs. A clean-directory aggregate import test loads every Greedy-owned
Phase 0--6 module except unsafe historical modules, including never importing
`Greedy/main.py`; it proves silent, file-free, global Python-RNG-neutral, and
global NumPy-RNG-neutral imports.

The final `greedy-hybrid-matched-comparison-v1` audit is fixed to repository
HEAD `8e5114e6e9101057da48255962afa65900c6c8d0`. The gate hashes all 35 unique
active Hybrid/shared source and manifest paths represented by the 45 Phase
3--7 audit records and compares them to their recorded Git blobs. All 52
required comparison rows remain equal and ordered; all 11 intentional
policy-only differences remain explicitly unequal and exhaustive. The final
semantic source entries are:

| Boundary | Active source location | Git blob | Disposition |
| --- | --- | --- | --- |
| Fixed two-stage action | `IBG_Hybrid/contracts.py:12-54` | `4f50cb74b56f3739a9dba1be59b80091f8f20732` | Adapt behind Greedy identities |
| Public Ready/capacity admission | `IBG_Hybrid/phase0_contract.py:234-307` | `45eb84512efa7457648ae8667b30e7f83f25f304` | Adapt; exclude planning/candidate feasibility |
| Flow order, selected feedback, and outcomes | `IBG_Hybrid/runner.py:198-218,281-386,544-630` | `b60ddcc0c7d55d7c6d3cc55e2308c194d24389c3` | Adapt behind Greedy slot/metric contracts |
| Keyed physical/observation schedules | `IBG_Hybrid/simulation.py:21-161` | `1b9f59f208885874b57e06e1d92fcabeeccc2db4` | Adapt separate local streams |

Policy-neutral latency, likelihood, learning, selected processor/forwarder
behavior, resource constants, and offline validation remain reusable only
through their recorded boundaries. Greedy-owned schemas, identities,
arbitrary-stage routes, lifecycle, evidence, and reporting remain adaptations.
Hybrid pruning, activation, planning-link selection, future-flow lookahead,
Monte Carlo, policy/process-pool controls, and repeated runs remain excluded.
No Phase 7 live or performance architecture exists; Phase 8 is a separately
authorized live validation action.

## Greedy Phase 8 small live Kernel gate

The separately authorized Phase 8 gate validates the existing architecture on
one dedicated kind cluster: cluster `greedy`, context `kind-greedy`, namespace
`greedy-testbed`, one control-plane node, and one worker labeled
`greedy.workload-node=true`.  The accepted explicit topology is `3x3x2` with
fixed `L=2`, profile seed 17, profile fingerprint
`53de63eb180316c2fc4b9f5f02b078ed`, rollout batch size 1, forced captured
replay, and CSV export.  Every serving and finite controller Pod ran only on
the dedicated worker.

Three live-only compatibility gaps were repaired without changing policy or
metric semantics:

- Kubernetes allocatable memory reported as non-integral-MiB `Ki` is
  conservatively floored to whole MiB for admission preflight.
- local image provenance resolves the linux/amd64 OCI config digest from
  `docker image save`; this is the identity exposed by containerd after
  `kind load`, unlike Docker's local manifest/list ID on the active host.
- evidence accepts at most the mathematically bounded `0.002` unit-mass drift
  from four independently rounded three-decimal belief entries, preserving the
  learner output verbatim while rejecting larger drift.  Lifecycle source
  fingerprints now produce the 64-hex value already required by the Phase 6
  trace schema.

The normal run built and loaded both offline images, reconciled replicas in
single-replica batches, waited for exact Ready coverage, executed 14 slots,
reached equilibrium, passed captured Pure/Kernel replay for every slot, and
persisted one validated JSONL lifecycle plus CSV.  The unchanged skip-build
run built and loaded no images, executed 10 slots to equilibrium, and replaced
only the finite controller Job.  All seven retained serving Pod UIDs, service
image identities, and zero restart counts were unchanged.  The controller Job
UID changed as intended.

Live resources match the active Hybrid comparison envelope: processor
`50m/128Mi` request and `1 CPU/768Mi` limit, forwarder `25m/128Mi` and
`1 CPU/256Mi`, generator `50m/128Mi` and `1 CPU/768Mi`, and controller
`2 CPU/256Mi` and `4 CPU/1Gi`.  Runtime profiles remain mounted only into
private processors; the controller mounts only public inputs.  Controller
process CPU/RSS and cgroup-throttling samples are evidence-only.  No
multi-host, line-rate, DPDK/VPP, scale, or cross-policy performance
architecture is established by this gate.

## Greedy admission-correction architecture boundary

The accepted Phase 8 implementation and its traces are version-bounded
historical `pure-greedy-budgeted-l2-v1` evidence. A paper audit found that the
topology-derived `ceil(N/M)` assigned-flow admission ceiling was introduced by
the implementation plan rather than by `misc/vesal_tex.tex`. The paper's
myopic Greedy baseline observes prior decisions in the current slot and scores
replica `j` at `n_j+1`; it ignores predicted subsequent selections. It is
therefore reactive to already-present congestion, but does not anticipate
future congestion. The hard derived ceiling can mechanically prevent the
premature hot spots that this baseline is intended to expose.

The correction is split across two phases. Phase 8.1 owns an offline
`pure-greedy-budgeted-l2-v2` contract migration. Its policy feasibility uses
canonical identity coverage and public Running/Ready state only. Neither
`GreedyConfiguration`, `PublicReplicaState`, discovery labels, nor controller
inputs derive or expose `max_assigned_flows=ceil(N/M)`. Loads remain unbounded
by topology dimensions within a slot and are still scored at
`current_load+1`, then committed sequentially before the next real flow. The
Kubernetes worker allocatable/request preflight remains unchanged because Pod
scheduling capacity is distinct from a synthetic per-flow admission ceiling.
The hidden latency model's state-conditioned congestion/capacity parameters
also remain unchanged and continue to affect expected and realized processing
behavior rather than action feasibility.

Phase 8.2 owns the separately authorized live migration gate. It must rebuild
every affected image under complete source provenance, reconcile only the
owned Greedy cluster, demonstrate a selected load above the old `ceil(N/M)`
boundary using a deterministic small fixture established offline, and then
repeat unchanged with `--skip-build`. New traces must identify the v2 policy
contract. Existing v1 JSONL remains readable and immutable, while mixed-v1/v2
CSV comparison must fail unless a future explicit migration format is defined.

The fixed `L=2` joint action, distinct increasing stages, `K-2` bypasses,
current-belief expected utility, mandatory complete route, best-feasible
non-positive handling, selected-only learning, physical/raw outcome split,
strict SLA, fairness, and equilibrium semantics do not change. The paper's
per-stage/all-`K` wording and positive-only selection remain known intentional
differences because the user explicitly retained the budgeted two-stage
container baseline and complete-route behavior.

Phase 8.1 completed this offline boundary on 2026-08-27. The active typed
contract is now `pure-greedy-budgeted-l2-v2`; `GreedyConfiguration` and
`PublicReplicaState` contain no topology-derived admission property, and
`GreedyPolicy.evaluate_admission` checks only exact public identity coverage
and Ready state. Discovery, rendered resources, rollout reconciliation, and
launcher state likewise contain no `greedy.max-assigned-flows` label or
controller capacity input. A deterministic `5x2x2` fixture selects the same
high-valued replica five times, above the former capacity of three, while its
score is evaluated at the true projected loads 1 through 5. The first flow is
not evaluated at that eventual load, which proves the policy remains reactive
to earlier real assignments without simulating future flows.

Persistence is version-bounded rather than rewritten. New slot evidence and
JSONL use `greedy-kernel-slot-evidence-v2` and
`greedy-experiment-jsonl-v2` and omit the removed field. Explicit v1 readers
retain the old shape and validation for immutable Phase 8 traces. CSV export
uses a policy-contract marker and a separate default `figures/Greedy/v2`
directory; retained mixed v1/v2 policy columns fail closed. The matched
comparison is now `greedy-hybrid-matched-comparison-v2` and records active
Hybrid's synthetic admission as an unresolved mismatch, not a matched row.

## Greedy end-to-end fairness boundary

Phase 8.3 corrects which per-flow series the Greedy Jain index reads. The
paper's Eq. (e2e_utility) in `misc/vesal_tex.tex` defines per-flow utility as
the selected stage utilities minus the inter-stage link costs, and its metric
list scores Jain over exactly that end-to-end quantity. Greedy previously
scored the link-free predicted series, so a slot whose replicas carried equal
beliefs and equal final loads produced one identical predicted value per flow
and a structurally near-perfect index regardless of what the flows actually
experienced.

The active assembly is `greedy-active-slot-metrics-v2`. `compute_slot_metrics`
now scores `raw_end_to_end_reference_utility_per_flow` -- observed selected
physical utility minus the measured pair latency -- and records a
`fairness_domain_valid` boolean beside the index. Jain is only meaningful on
nonnegative values, and a congested flow can lose more to latency than it
earns, so each flow is floored at zero before scoring: a flow with negative
end-to-end utility gained no utility. The flag is true only when every
unclamped per-flow value was strictly positive, so a report can distinguish an
ordinary equality measurement from one that required the floor. When no flow
gained anything the index is a genuine 0/0; the slot records the documented
`0.0` convention with the flag false rather than a computed value. Unclamped
per-flow end-to-end utilities, the retired predicted series, physical
utilities, pair costs, and raw latency all remain recorded.

Greedy is forbidden from reading link costs at selection time
(`planning_link_cost_ms` and `measured_pair_latency_ms` are
`POLICY_FORBIDDEN_INPUT_FIELDS`, and `link-cost-selection-term` stays in
`EXCLUDED_SELECTION_FEATURES`). This correction therefore changes reporting
only: placement, expected-utility scoring, selected-only learning, SLA, and
equilibrium are untouched.

Persistence stays version-bounded. New evidence and JSONL use
`greedy-kernel-slot-evidence-v3` and `greedy-experiment-jsonl-v3`; v1 and v2
documents remain readable and are still validated against the retired
predicted-utility formula, and must not carry `fairness_domain_valid`. Because
the policy contract is unaffected and remains `pure-greedy-budgeted-l2-v2`, the
CSV marker now pins both the policy and the trace contract, and the default
output directory moves to `figures/Greedy/v3`; a pre-Phase-8.3 marker or a
foreign trace generation fails closed instead of appending a
predicted-fairness column beside an end-to-end one.

## Greedy rebuilt-service rollout classification

`_classify_service_rollout` originally accepted exactly two Pod-template
provenance states: **absent**, the legacy or not-started case that triggers a
canonical apply, and **exact**, matching the target image ID and service source
fingerprint. Anything else failed closed as ambiguous.

That admitted `absent -> exact` but never `exact(old) -> exact(new)`, so a
legitimate service-source change could not be rolled onto existing serving
workloads at all. Earlier rebuilds only passed because the provenance
annotations were being introduced in the same change and therefore read as
absent. Phase 8.3 exposed the gap: `Greedy/slot_contracts.py` is a
`SERVICE_SOURCE_FILES` member, so adding one metrics field moved the service
fingerprint, rebuilt the service image, and left every StatefulSet template on
the previous pair. A partial teardown cannot recover, because the classifier
also requires complete coverage of all four serving resources.

The classifier now accepts a third state, **superseded**, gated on the caller
declaring `rebuild_pending`. When the launcher knows a service rebuild is
committed for this run, a uniform non-target pair is the pre-rebuild template
rather than an ambiguity, and is classified `template-update-required`.

`rebuild_pending` rather than a comparison against the recorded pair is the
correct discriminator, because the transition marker is persisted to
`greedy-launcher-state` *before* the canonical apply. A run interrupted between
those two steps leaves the record already advanced to the target while the
templates still hold the superseded pair, so that pair is no longer recoverable
from the record and no equality test can identify it. What the launcher can
always assert is that it rebuilt the service, which makes any non-target
template stale by construction.

Two call sites declare it. `_reconcile_existing` passes the run's
`service_restart_required`, which is true when the recorded state carries a
pending restart or the service image was built this run. The pending-rollout
check passes it unconditionally, since it only executes when
`service_restart_required` is already recorded.

The fail-closed intent is preserved. Every mode must still agree across all
four serving resources, a mixed set is still `partial or ambiguous`, a
half-written annotation pair still raises, and with no pending rebuild any
non-target pair is still foreign mutation. The final post-apply gate omits
`rebuild_pending` entirely, so a settled rollout must show exact provenance and
cannot be satisfied by a stale template. Overwriting an unexpected uniform pair
during a declared rebuild is safe because the launcher already asserts
exclusive ownership of the namespace and the canonical apply is the corrective
action.

## Planned Hybrid opt-in posterior-transmission mirror

Planned: 2026-08-31. The Hybrid controller currently owns, updates, and reuses
the complete authoritative belief state locally, so the existing observed
control-plane footprint correctly records zero belief TX/RX bytes and messages.
To answer the manuscript's separate posterior-exchange overhead question
without changing that operational architecture, Hybrid will gain a default-off
measurement mirror.

When enabled, a lightweight receiver will run as a separate worker-only Pod
behind a dedicated ClusterIP Service. After the controller has computed a
completed timeslot's posterior updates, it will send deterministic serialized
copies across the Pod network. The receiver will validate the message identity
and payload length and then discard the copy. It will never own, modify, return,
or supply beliefs to placement. The controller's existing local belief state
remains authoritative for every subsequent decision.

The measurement contract will distinguish the exact canonical posterior-vector
bytes from the complete serialized HTTP application-body bytes containing any
required replica identity or envelope fields. It will record message counts and
per-timeslot sums across all mirrored posterior updates. HTTP/TCP/IP/Ethernet
headers, acknowledgements, retransmissions, NIC traffic, and forwarder traffic
remain outside this payload-only result. Existing observed `belief_tx` and
`belief_rx` fields remain zero and must not be relabelled; the new record is an
instrumented posterior-mirror measurement with its own versioned schema.

Disabled mode deploys no receiver and performs no mirror transmission. Enabled
mode changes only the measurement deployment shape and creates real HTTP
traffic carrying non-authoritative copies. Placement, pruning, lookahead/MC,
randomness, physical and observation jitter, learning arithmetic, authoritative
belief continuity, utility, SLA, fairness, equilibrium, selected-route traffic,
and telemetry semantics remain unchanged.

## Hybrid posterior-transmission mirror implemented and locally verified

Completed locally: 2026-08-31. The default-off production mirror now consists
of a worker-only validation/discard HTTP receiver and one persistent controller
sender. After a slot has produced its completed aggregated posteriors, the
controller sends one canonically ordered copy per unique sampled replica across
the Pod boundary. A rejected or incomplete copy prevents authoritative belief
commit and completed-slot evidence. The receiver never supplies beliefs back to
the controller; controller-local beliefs remain the sole decision input.

The versioned snapshot records canonical posterior-vector payload bytes,
complete compact-JSON application-body bytes, and message counts separately.
Enabled evidence is revalidated against the completed belief map, sampled
replica identities, exact body lengths, SHA-256 digests, totals, slot identity,
and receiver-run identity. Existing observed control-plane `belief_tx` and
`belief_rx` remain zero because the mirror is a separate instrumented boundary,
not operational distributed belief ownership.

When both `--posterior-mirror 1` and `--csv 1` are active, host export creates
three atomic wide tables under `figures/IBG_hybrid/posterior_mirror/`: vector
payload bytes, complete application-body bytes, and update messages. Disabled
or legacy traces create no mirror directory. The Hybrid-only summary command
reports each timeslot, run totals, median, and p95 while explicitly excluding
wire/protocol overhead and required distributed-learning claims.

This measurement path does not enter Hybrid metrics or Pure/Kernel parity and
cannot alter placement, pruning, lookahead/MC, learning, utility, SLA, fairness,
equilibrium, selected-route execution, or telemetry. It is application-body
payload evidence only: no NIC, HTTP-header, TCP/IP/Ethernet, multi-host, or
wire-byte measurement is claimed.

The receiver ASGI process is packaged in the existing Hybrid service image,
which owns the pinned Uvicorn runtime. The controller image retains the same
mirror module for its sender/client boundary but remains intentionally free of
Uvicorn. This split reuses existing offline wheelhouses without broadening the
controller runtime dependency set.

The retained-cluster reconciler also carries forward existing non-netem
StatefulSet Pod-template annotations while rendering an impairment transition.
This prevents externally added rollout provenance such as
`kubectl.kubernetes.io/restartedAt` from being silently removed and triggering
an unrelated replica rollout; the requested netem annotation and init container
remain the only impairment-owned template fields.

## Greedy progress-aware rollout waiting

Updated: 2026-09-01. Greedy serving readiness no longer uses one fixed
120-second `kubectl rollout status` deadline for an entire multi-Pod rollout.
The launcher polls exact StatefulSet/Deployment generations, updated/Ready/
available replica counts, revision convergence, and owned Pod UIDs/readiness.
A verified monotonic rollout advance resets a 120-second stall clock. Merely
waiting, restarting a container, or emitting output does not reset it. A
separate topology-bounded total deadline prevents endless Pod replacement from
keeping the launcher alive indefinitely. Final completion still requires exact
revision convergence and exact owned Running/Ready Pod coverage before any
controller Job is created.

## Greedy restart-safe service-rollout provenance

Updated: 2026-09-01. Greedy serving Pod templates now carry two public,
non-policy annotations binding a rollout to the exact service OCI config image
ID and service-source fingerprint already persisted by launcher state. The
launcher classifies the retained serving state as legacy/template-update
required, progressing, or converged. Missing provenance is the one supported
legacy state; partial, mixed, or mismatched provenance fails closed. A
converged pending rollout is reused, and an exact progressing rollout is waited
without another apply or restart.

Canonical reconciliation removes the retired
`greedy.max-assigned-flows` label from retained StatefulSet and flow-generator
Pod templates. When either provenance or this v1 label requires correction,
one canonical apply combines both changes into one Pod-template revision. The
old unconditional `kubectl rollout restart` is removed, preventing the apply
from being followed by a second revision. After exact template and Ready
convergence, the launcher verifies every running private processor, public
forwarder, and flow generator against the expected node-local OCI config ID
before it marks launcher state stable or creates the controller Job. These
annotations never contain hidden state or stochastic seeds and never enter the
policy, learning, or outcome path.
