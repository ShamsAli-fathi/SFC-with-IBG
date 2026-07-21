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

Each Kubernetes replica Pod separates the private processor from the public route forwarder. The processor listens only on Pod-local port 8081 and exposes `GET /health`, `GET /warmup`, and `POST /process`. It remains one Uvicorn worker. `POST /process` accepts positive slot/flow IDs and final `assigned_load`, samples state-conditioned physical processing delay, performs the work, independently samples observation-only jitter, and returns modeled/measured processing latency, observation jitter, noisy learning signal, admitted concurrency, a categorical state estimate, and the four-state load-aware likelihood vector. The public forwarder listens on port 8080, owns `POST /process-route`, calls its co-located processor, and forwards an already-selected route to the next public forwarder. Phase 4.1 runs two Uvicorn workers only for this public-forwarder application so concurrent route RPCs do not all depend on one application worker. Thus forwarding I/O cannot share the processor's Uvicorn event loop or inflate physical processing latency, and adding forwarder workers does not replicate or change the processor's stateful sampling path. Transitional `legacy_*` aliases remain in the wire response for trace compatibility but do not define the active belief model.

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

The controller emits newline-delimited `IBG_EVENT` records for run start, each completed iteration, and run completion. Events include the explicit datapath mode, runtime image and environment versions, initial/final replica snapshots, per-stage flow order and placements, selected observations, utility/SLA/fairness/timing metrics, beliefs before and after the slot, and maximum belief change. Slot durations use a monotonic clock so WSL wall-clock corrections cannot distort elapsed time. The launcher renders those events as concise live text and stores the complete JSONL trace under the repository-local versionable `runs/` directory.

When `--csv 1` is selected, the launcher converts the completed host-side JSONL trace into the five legacy reports—`time.csv`, `sla_violations.csv`, `aggregate_utility.csv`, `jain_index.csv`, and `replica_results.csv`—plus `realized_end_to_end_utility.csv` and, when every completed slot records `learning_signal_v1`, `logical_learning_footprint.csv`. The realized-utility report exports the existing `realized_utility_total` trace metric: summed actual processing utility across all flows and stages minus the trace's recorded link-latency penalty, using the configured link-latency weight. The logical-footprint report exports each slot's `learning_signal.logical_payload_bytes`; it is the canonical selected-only learning-information size model, not actual HTTP or wire bytes. Current traces record only consecutive selected-replica pair costs for the realized-utility penalty; older traces retain their historical request-overhead meaning and must remain tied to their code version. Older traces without a complete learning-signal schema retain their historical CSV set rather than receiving fabricated footprint values. The added reports do not redefine the legacy aggregate series. All reports are written under the repository-local ignored `figures/` directory; no Kubernetes volume or controller-side filesystem persistence is involved. Metric reports retain one column per experiment, identified by a deterministic six-character hexadecimal hash of the timestamp and run configuration; complete provenance remains in the corresponding JSONL trace. Belief snapshots include the initial state followed by every completed iteration.

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

where $E_\theta$ is independent observation-only noise with active state-1-through-state-4 scales $\omega_\theta=7.2,6.3,4.8,3.9$ ms. This `half-normal-observation-v1` term never enters actual processing latency, end-to-end SLA latency, or realized utility. The learning boundary computes $\ell_\theta=f_S(s\mid\theta,n,m)$ from the exact convolution of the physical and observation half-normal densities and passes all four likelihoods through the existing posterior/aggregation structure. A categorical estimate may report $\arg\max_\theta\ell_\theta$, but it does not drive the update. Unselected replicas produce no observation. Assigned final load, modeled and measured physical processing latency, observation jitter, noisy learning signal, admitted concurrency, client latency, and link/transport latency remain separate correlated fields.

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
| 1 (bad) | 40 | 8 | 12 | 1 | 6 | 3 |
| 2 | 28 | 6 | 8 | 2 | 5.25 | 5 |
| 3 | 18 | 4 | 5 | 3 | 4 | 7 |
| 4 (good) | 10 | 2 | 2 | 5 | 3.25 | 11 |

The accepted policy values are $R_k=100$ utility units per selected stage, $c_k=1$ utility unit, $\alpha_k=1$ utility unit/ms, $\alpha_{\mathrm{link}}=1$ utility unit/ms, and end-to-end SLA threshold $\tau=110$ ms. The user-directed Phase 4 recalibration used the final five slots from ten current forwarding-isolated 12-flow Kernel runs: their 600 end-to-end flow latencies average 88.84 ms, with p90 108.46 ms and p95 113.78 ms. At 110 ms, 47/600 (7.83%) are violations; this restores a meaningful, non-saturating classification signal. Thus the stage-latency zero-utility threshold is 99 ms. Under the active physical law, expected low-load utilities for states 1 through 4 are approximately 54.21, 66.81, 77.81, and 86.41; at the supported exact load of three flows they are approximately -9.79, 46.81, 69.81, and 82.41. The game still assigns every flow, but a feasible state-4 option remains available in the supported profile set.

The full seeded run uses 5,000 samples per state/load with seed 2050. With the separate observation law, minimum categorical accuracy is 81.38% and mean load-1 accuracy is 87.74%; the gate requires at least 80% minimum accuracy and at most 90% mean load-1 accuracy so the design is both usable and deliberately imperfect. The complete likelihood vector—not the category—continues to drive belief updates. Scaling all physical latency parameters or $\alpha_k$ by $\pm10\%$, and changing reward by $\pm5\%$, preserved ordered crossings inside the accepted bands. The unchanged physical-latency SLA sweep for homogeneous three-stage, load-3, zero-transport routes produced violation probabilities 1.0, 1.0, 0.0002, and 0.0 for states 1 through 4; observation-only noise is excluded from this calculation. These are model checks, not predictions for mixed live routes.

The earlier localhost Uvicorn conformance result predates the separated learning signal and remains version-bounded historical evidence. Current live validation additionally requires nonnegative observation jitter, exact equality $s=q_{\mathrm{measured}}+e$, and likelihood equality under the convolved density while retaining the physical scheduler-overshoot check. After a successful normal image build/deploy, fresh current-image supported trace `runs/ibg-experiment-20260721T145856Z.jsonl` reached equilibrium in 16 slots and passed the Kernel gate (86.11% classification and 97.22% server-overshoot compliance) plus exact 16-slot replay with zero drift. The supported trace was launched with `--skip-build` only after that normal build/deploy had succeeded.

The calibration horizon exceeds three flows only through direct utility evaluation and does not expand the supported equilibrium-validation size. `deploy/kubernetes/profiles.json` fixes all active stage costs at 1 and maps replicas to states; the calibrated state table supplies active latency parameters. Legacy profile capacity, delay, gamma, base-delay, and congestion-delay fields remain for trace/schema compatibility and must not be interpreted as the accepted latency law.

Negative utility currently indicates an unattractive or infeasible assignment but does not reject a flow: the exact decoupled policy enforces one replica per stage. Adding skip/reject changes the action/admission model and must not be smuggled in as a parameter choice. Phase 2 must record the chosen interpretation and defer rejection behavior unless separately authorized and tested.

## Deferred utility-horizon extension

Before a future experiment or heuristic study uses accepted utility values for per-replica loads above 12, extend the synthetic calibration to $N_{\mathrm{cal}}=50$. This is direct latency/utility evaluation only: it must preserve the active $Q_\theta(n)$ law and $u(q)=R-\alpha q-c$, must not alter `BR_EIBG`, add heuristics, change placement, or claim 50-flow exact-solver scalability.

The user-requested target crossing bands are state 1: 3--6, state 2: 12--20, state 3: 25--35, and state 4: 45--50. The extension must select/fix suitable state parameters, generate utility curves for loads 1--50, rerun seeded Monte Carlo and sensitivity checks, update deterministic tests and all handoffs, and state explicitly that the horizon is per-replica assigned load rather than total logical flows. It is a deferred calibration requirement, not part of the completed Phase 3 Kernel-baseline work.

## Implemented Phase 3 Kernel baseline

`kernel` is now an explicit runtime mode at the adapter, controller, flow-generator request/response, slot-result, validation-summary, and JSONL-event boundaries. The flow generator rejects unimplemented runtime modes and verifies that the requested mode matches its configured mode. Historical Phase 3 traces carry non-negative per-hop `transport_overhead_ms=max(0, request_latency_ms-processing_latency_ms)` fields. Current traces retain compatible hop fields but add explicit observation jitter, noisy learning signal, `links`, and separate generator-ingress fields; only physical processing plus `links[*].link_cost_ms` supplies end-to-end SLA and realized utility. The private processor retains the `/process` request/response contract; the public forwarder alone exposes `/process-route` for an already-selected route. Simulation is labelled `simulation` for comparison but is not a deployable datapath mode.

`scripts/phase3_kernel_baseline.py` validates a completed supported-size JSONL trace. It requires one selected observation and one correlated Kernel hop for every placement, exact correlation of physical processing, observation jitter, noisy signal, and likelihood vectors, all four-state ordering at load 1, non-decreasing observed congestion groups, at least 80% categorical accuracy, and equilibrium. It validates historical request-overhead traces under their original schema. For current traces it additionally requires exactly `K-1` consecutive, route-correlated pair records per flow; verifies each cost formula, source/target Pod identity, normalized target endpoint, and equality between the pair sum and the deducted per-flow link metric; checks separately labelled non-negative ingress telemetry; and rejects schema mixing within one run. The Kubernetes live scheduling gate is statistical: at least 95% of selected hops must have measured-minus-modeled server processing overshoot no larger than $\max(10\text{ ms},0.1Q_{\mathrm{modeled}})$. Communication and ingress timings are reported distributionally without an unsupported deterministic upper gate.

The accepted seed-2050 supported-size run used image `ibg-testbed:kernel-phase3`, Docker 29.6.1, kind 0.32.0, and Kubernetes 1.36.1. It reached equilibrium in nine iterations and produced 81 complete selected hops over assigned loads 1--3. Mean/p50/p95/max processing latency was 16.33/13.13/36.59/52.60 ms; server overshoot was 2.07/0.97/7.52/10.54 ms with a 98.77% tolerance pass rate; and transport overhead was 6.85/6.43/11.31/17.87 ms. Load-1 mean processing latency remained ordered at 49.06, 39.27, 21.31, and 12.52 ms for states 1 through 4, observed state-3/state-4 congestion groups were non-decreasing, and categorical accuracy was 83.95%. A preliminary cold single-slot run observed a 60.30 ms transport outlier, which is why no unsupported deterministic transport ceiling is claimed.

The same validator replays every captured selected signal, likelihood, and per-flow transport value through the unchanged simulation runner with Kubernetes-style deferred complete-route observations. All nine replayed slots matched their Kernel trace exactly: 81 placements and observations matched, and maximum drift across utility grids, likelihoods, beliefs, aggregate/per-flow and realized utility, processing/link/end-to-end latency, SLA, fairness, and equilibrium was zero.

## Implemented Phase 4 control-plane measurement contract

The future Kernel--DPDK/VPP comparison needs a datapath-neutral controller metric, but it must not confuse selected-route execution with control-plane work. A versioned `control_plane_v1` block is therefore emitted once per completed Kubernetes slot. It records monotonic-wall and controller-CPU timing for discovery; admission/planning from slot start through route-plan dispatch; feedback processing from returned telemetry through validation, observation conversion, belief update, metrics, and equilibrium; and their sum as active control time. Time spent awaiting the dispatched selected route is recorded separately as `data_plane_wait_ms` and is never presented as control-plane decision time.

The same block counts controller-boundary HTTP application-payload bytes and messages, partitioned into Kubernetes discovery, controller-to-flow-generator route command, flow-generator-to-controller selected telemetry, and reserved zero-valued belief-exchange fields. Forwarder-to-forwarder RPCs on the selected route remain data-plane traffic and are excluded. Counts use application-body bytes rather than unsupported TCP/IP or protocol-header wire-byte claims. The contract preserves the current selected-only noisy learning signal and does not change route selection, solver inputs, pair-cost deduction, learning, SLA, or equilibrium behavior.

A separate versioned `learning_signal_v1` block measures the logical selected-only learning-information footprint without reclassifying the larger telemetry response. It canonically projects each selected observation to UTF-8 JSON containing only stage, flow, selected replica, assigned load, noisy selected learning signal, and the four-state likelihood vector. Physical processing latency and observation-jitter diagnostics are excluded alongside route endpoints, Pod/node metadata, transport, pair costs, ingress data, categorical state estimates, and legacy aliases. A completed slot must contain exactly `flows * stages` records; the number of available but unselected replicas cannot increase it. The block reports record count, canonical logical-payload bytes, and mean bytes per selected hop.

`learning_signal_v1` is a reproducible size model for the information contract used by selected-only learning. It is not the actual flow-generator HTTP response size, a TCP/IP wire-byte measurement, or evidence that the current reporting envelope transmits only this projection. The actual aggregate response remains measured independently as `control_plane_v1.payload_bytes.selected_telemetry_rx`. No raw-telemetry counterfactual or byte-saving ratio is inferred.

## Current exploratory 15x8 runtime investigation

The 110 ms SLA rule is unchanged and observation-only jitter is excluded from its latency input. In the earlier exploratory 15-flow/8-replica traces, physical processing averaged 67.01 and 70.74 ms/flow in the final slot, but selected pair costs averaged 50.95 and 60.36 ms/flow, producing 10/15 and 13/15 violations. No final flow exceeded 110 ms before pair cost. This remains a runtime/reporting investigation, not evidence to retune the SLA or alter the physical/observation distributions.

The prolonged controller symptom has a concrete exact-solver cache-lifetime cause and is repaired. A 15x8 stage evaluates 490,314 exact load-vector subgames. Recursive `lru_cache` creates a wrapper/function self-cycle, so merely dropping a completed policy left that entire memo table alive until cyclic garbage collection. The policy now uses an exact-equivalent packed load-state key and clears its memo table in a `finally` block immediately after `embedding` completes. The recurrence, candidate actions, sampled utility grid, ordered placement, and lowest-replica-ID tie rule are unchanged. A normal-build 15x8 trace, `runs/ibg-experiment-20260721T144252Z.jsonl`, completed 19 slots without OOM and replayed with zero drift; median elapsed/admission/controller-CPU times were 10.41/10.06/9.91 s, respectively, versus the previous roughly 15 s slots. The controller cgroup remained at about 207 MiB with zero OOM events during the run.

The pair metric is deliberately a selected RPC-boundary residual, `max(0, caller HTTP elapsed - callee route-handler elapsed)`. It includes ordinary public-forwarder queueing/scheduling and HTTP/Kubernetes work outside the callee handler, not only a stable network-link delay. The newly added selected-forwarder cgroup before/after measurements disconfirmed the prior throttling hypothesis: the separated-mode diagnostic run recorded zero throttling deltas across 299 selected-forwarder samples, and the physical-only A/B had just one 6.104 ms event that did not coincide with a high pair cost. The cgroup probes themselves add route-wait work, so a clean no-probe run was also retained. Do not change forwarder CPU resources on the basis of cumulative lifetime counters.

The opt-in `forwarding_path_v1` diagnostic further decomposes a selected pair residual without redefining it. For each source-to-next-stage RPC it records the source request start, target public-forwarder handler start/finish, and source response receipt on the current shared Unix-epoch clock, then reports source-to-target-handler, target-handler, and target-finish-to-source durations. It is a same-clock Kernel diagnosis aid, not a wire, one-way, or portable cross-host latency measurement. `link_cost_ms` remains the existing caller-duration minus callee-route-duration value; these fields do not affect placement, learning, utility, SLA, or equilibrium. `scripts/forwarding_path_summary.py` validates complete opt-in traces and summarizes the three segments.

The independent pair-residual/SLA symptom was subsequently localized with no-controller fixed-route probes to concurrent HTTP/1.1 scheduling/queueing across single-worker public forwarders. Phase 4.1 applies a runtime-only correction: each public-forwarder container runs two Uvicorn workers, while its private processor remains single-worker and unchanged. The forwarder request remains 25m CPU, its measured two-worker CPU limit is 1 CPU, and its memory request/limit is 128/256 MiB. The 1-CPU limit is evidence-based: the initial two-worker/500m probe produced correlated quota stalls, while the repeated same-/cross-worker probe at 1 CPU recorded zero throttle deltas. The one-worker forwarder peaked at 52.4 MiB; two-worker validation peaked at about 141 MiB with zero memory events or restarts, leaving headroom under 256 MiB.

In the post-correction fixed-route probe, five-wave means were 6.57/5.75 ms for six simultaneous same-/cross-worker requests and 7.73/8.01 ms for fifteen, compared with the diagnosed one-worker six-request waves of 9.46/21.07/24.50 ms and 23--38 ms first-wave fifteen-request costs. Clean exploratory trace `runs/ibg-experiment-20260721T191634Z.jsonl` reduced all-slot pair cost from 45.78 to 36.81 ms per flow and p95 from 80.09 to 63.22 ms relative to diagnostic trace `runs/ibg-experiment-20260721T180604Z.jsonl`; source-to-target-handler mean/p95 fell from 18.18/40.11 to 13.65/31.72 ms. It ended at 0/15 SLA violations with 67.71/27.58/95.29 ms final physical/pair/end-to-end means and realized utility 3025.72, and exact replay had zero drift. This is favorable exploratory evidence, not a formal 15x8 gate or a guarantee that every run beats the earlier healthy snapshot; the unchanged raw pair metric still records real runtime variation.

`scripts/control_plane_summary.py` validates complete traces and reports per-run median and p95 admission, feedback, active-control, controller CPU, payload-byte, message-count, separately labelled data-plane-wait values, actual selected-telemetry response bytes, and—when present—the separate logical learning-signal record and byte metrics. Future comparisons must hold seed, dimensions, profiles, controller image, and measurement schema fixed. `data_plane_wait_ms` may differ by datapath mode but remains a separately reported execution outcome.

## Planned Kernel and DPDK/VPP expansion boundary

The current HTTP route is the named `kernel` baseline: the flow generator reaches the controller-selected first public forwarder, whose co-located private processor produces physical processing latency and the separate noisy selected learning signal; public forwarders relay the remaining already-selected route using `/process-route` over ordinary Linux TCP/IP and Kubernetes networking. The planned comparison path is `dpdk-vpp`: a VPP user-space forwarding component using an approved DPDK I/O backend between selected route peers while preserving FastAPI application processing, route identity, controller placement, and the learning contract. VPP can operate with non-DPDK interfaces and can integrate with the Linux control plane, but neither is a separate comparison mode in this roadmap.

Datapath selection belongs behind traffic and telemetry adapters. Every mode must retain slot, flow, stage, replica, endpoint, Pod, and node correlation, and must fail a slot rather than report a partial completion. FastAPI remains the source of exactly one selected-hop noisy learning signal and its four-state likelihood vector, with physical processing and observation jitter retained as separate diagnostics. Kernel and DPDK/VPP counters, transport latency, or queue measurements remain separately identified, and unselected replicas must not be queried or treated as observations.

The future `dpdk-vpp` mode is intentionally not implemented or claimed. It starts only after host preflight establishes safe NIC, IOMMU/VFIO, hugepage, CPU/NUMA, privilege, and Kubernetes device-resource handling. Coupled IBG is a separate future mathematical scope and must not be introduced through these datapath adapters.
