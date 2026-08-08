# Project Decisions

## Accepted direction

- Use native Docker Engine for the development workflow; Docker Desktop is not part of the testbed.
- Keep the source checkout, Docker data, and cluster data on a local filesystem supported by Docker.
- Use kind with one control-plane node and two worker nodes. kind uses containerd internally.
- Start this roadmap with the decoupled IBG path. Preserve its mathematical and learning logic with minimal alterations.
- Supported target: three stages, five replicas per stage, and three logical flows per slot.
- Represent stages with three StatefulSets: two Pods per stage for the Phase 5 bring-up gate, then five Pods per stage for the supported validation target. Use stable ordinal identities but no persistent storage.
- Use tiny kernel-path HTTP services as CNF stand-ins. They expose health/processing behavior and observable latency/load.
- Run the Python IBG controller in the cluster with a ServiceAccount and narrowly scoped RBAC.
- Admit flows sequentially for placement, then exercise their selected paths concurrently to create contention.
- Preserve the existing metric concepts (aggregate utility, SLA violations, Jain fairness, runtime, and beliefs) while adding slot, Pod, node, placement, and latency metadata.
- Follow the ordered gates in `ROADMAP.md`. Complete and verify one phase before starting the next.
- Validate simulation/Kubernetes behavior at the supported small size; no scaling phase is planned for the exact algorithm.
- Read or update `Tutorial.md` only when the user explicitly requests it; it is not part of automatic phase maintenance.
- Read or update `Report.md` only when the user explicitly requests it; it is not part of automatic phase maintenance.
- Read or update `EVIDENCE_SUMMARY.md` only when the user explicitly requests it; it is not part of automatic phase maintenance.
- Treat the user-added `Chart/` directory as a legacy plot-script work area. Read it only when explicitly directed, inspect only `.py` scripts, edit only on explicit request, and require separate explicit approval before staging, committing, or pushing any of its content.
- Characterize the reference behavior before refactoring, then introduce simulation-backed adapter contracts before Kubernetes implementations.
- The completed baseline kept HTTP latency separate from its synthetic belief observation. Phase 1 explicitly supersedes that choice: selected processing latency is now the belief signal, while request/transport latency and concurrency remain separate telemetry.
- Make the slot runner depend on explicit discovery, traffic, observation, and result-sink ports. Keep simulation implementations as the behavioral baseline for future infrastructure adapters.
- Apply observation likelihoods in the controller learning core; adapters collect observations but do not redefine local belief update or aggregation mathematics.
- Implement the HTTP replica as a small FastAPI/Uvicorn service with environment-provided stable identity and experiment parameters.
- Count active requests inside each replica service and report the admitted concurrency and measured server processing latency. Always release the counter on success or failure.
- The completed baseline generates `legacy_signal` and `legacy_likelihood` through the reference tasting model while leaving belief mutation exclusively in the controller. Phase 1 intentionally supersedes the raw legacy signal with selected processing latency and a load-aware likelihood vector.
- Make the flow generator accept complete controller-selected routes rather than perform placement itself.
- Start logical flows concurrently but await the three selected hops of each individual flow in stage order.
- Validate returned slot/flow correlation and replica identity, then fail the slot request on downstream HTTP, payload, correlation, or identity errors; do not present partial telemetry as a completed slot.
- Correlate every hop with slot, flow, stage, replica, Pod, endpoint, assigned load, modeled/measured processing latency, client latency, concurrency, state estimate, and likelihood. Transitional legacy aliases are compatibility fields only.
- Use one non-root runtime image for the local replica and flow-generator services; keep Docker Compose packaging local to Phase 4 and defer Kubernetes manifests to Phase 5.
- Use exact continuation play for the decoupled IBG: branch over every available replica at each player/load-vector subgame, score choices at their predicted final loads, and memoize subgames.
- Encode each exact load-vector cache key compactly and clear that one-stage memo table immediately after ordered placement finishes. This is a cache-lifetime correction, not an approximation: it preserves the exact recurrence, all candidate actions, sampled utility grid, placement order, and lowest-ID tie rule. Explicit clearing is required because Python's recursive `lru_cache` wrapper otherwise retains its complete state table through a self-cycle after the policy object is dropped.
- Enforce exactly one replica per stage in `BR_EIBG`; the paper's binary choose/skip pseudocode is generalized to the formal one-of-M SFC action constraint.
- Keep the existing belief-driven 30-sample utility grid, utility kernel, learning, embedding, equilibrium, and reporting logic around the corrected solver. “Exact” refers to the SPNE recursion over that sampled grid.
- Break exact utility ties by lowest replica ID so repeated seeded runs remain deterministic.
- Keep `BR_EIBG` as the current roadmap's exact small-instance policy. A scalable approximation, coupled extension, or additional baseline suite requires separate future scope and is not part of this roadmap.
- Derive one-based solver replica IDs from zero-based StatefulSet Pod ordinals and require the full expected Ready ordinal set before solving a stage.
- Store the Phase 5 deterministic replica profiles in one ConfigMap mounted by both replicas and the controller.
- Use the existing HTTP client with the in-cluster ServiceAccount token and CA for namespace-scoped Pod discovery; grant only Pod `get` and `list` permissions.
- Keep simulation observations stage-local, but let Kubernetes defer physical traffic until all stage placements form complete routes; convert returned hop telemetry into the existing observation contract before applying unchanged learning logic.
- The completed baseline preserves final assigned replica load as the legacy congestion input. Phase 1 retains final assigned load as the known conditioning variable for latency generation/likelihood and keeps actual HTTP admission concurrency as separate Kubernetes telemetry.
- Derive controlled observation samples from a deterministic replica seed plus slot, flow, and final congestion so observation generation does not disturb the solver's NumPy stream.
- Validate the supported three-stage/five-replica/three-flow case over seeds 2050, 2051, and 2052, requiring mathematical parity while treating Kubernetes timing and infrastructure metadata as backend-specific.
- Apply the one-shot controller Job only after StatefulSet and flow-generator rollouts complete; do not race validation traffic against endpoint replacement.
- Provide one post-roadmap experiment launcher that creates/reuses kind, rebuilds and loads the runtime image, deploys and waits for workloads, starts a fresh controller Job, and follows its logs.
- In observable experiment mode, retain one evolving replica/belief state across slots and stop only on the existing equilibrium test, bounded by an explicit maximum iteration count.
- Emit compact live iteration output from structured JSONL events, retain the complete repository-local trace under versionable `runs/`, and keep the Phase 6 one-slot comparison output compatible.
- Measure slot duration with a monotonic clock; wall-clock timestamps are not valid elapsed-time sources when host-clock corrections occur.
- Let the experiment launcher accept positive flow, stage, and per-stage replica counts, while retaining three flows, three stages, and five replicas as the default and only Phase 6 parity-validated target.
- Generate experiment stage Services, StatefulSets, and the shared profile ConfigMap from the requested dimensions; remove stale higher-numbered stage resources between runs.
- Preserve all validated profiles exactly and deterministically extend new stage/replica identities from the validated profile templates with unique observation seeds. This changes experiment configuration only, not `BR_EIBG` or its mathematics.
- Require every flow-generator route to contain the same positive contiguous stage sequence beginning at stage 1, rather than embedding a three-stage assumption in the traffic contract.
- Keep Kubernetes CSV export host-side: `--csv 1` converts the completed structured trace into the five legacy report files plus `realized_end_to_end_utility.csv` and, for complete `learning_signal_v1` traces, `logical_learning_footprint.csv` under the repository-local ignored `figures/` directory, avoiding cluster volumes and preserving the default JSONL-only behavior when disabled. The realized-utility report exports the trace's existing `realized_utility_total`; the logical-footprint report exports `learning_signal.logical_payload_bytes` per slot and remains a canonical logical-size metric rather than HTTP or wire bytes. Neither renames or redefines `aggregate_utility.csv`; historical traces without learning-signal records do not receive synthesized values. Use a deterministic six-character hexadecimal hash of timestamp, seed, flows, stages, and replicas as the compact CSV experiment-column identifier; retain full provenance in JSONL and reject duplicate column identifiers.
- Retain FastAPI as the application, identity, health, physical-processing and selected noisy-learning-signal endpoint for every datapath mode. A datapath extension forwards selected traffic; it does not replace replica observation behavior.
- Treat ordinary Linux socket/TCP/IP networking as the explicit `kernel` baseline and the later `dpdk-vpp` path as VPP running with its approved DPDK I/O backend. VPP is user-space software and can use non-DPDK interfaces, but this roadmap does not introduce standalone VPP as a third comparison mode.
- Keep datapath selection behind traffic and telemetry adapters. Kernel and future DPDK/VPP paths must preserve the controller-selected route and the slot/flow/stage/replica/endpoint/Pod/node correlation contract.
- Preserve asymmetric and partial observations in every mode: only a selected FastAPI hop yields one noisy learning signal and likelihood. Other datapath counters or queue measurements cannot update beliefs without another explicit validated mathematical decision.
- Add the DPDK/VPP path only after its topology, DPDK I/O backend, Linux-facing interfaces, lifecycle, readiness, route setup/cleanup, failure behavior, and host resource preflight are documented and testable. The existing Kernel mode must remain independently runnable.
- Defer DPDK/VPP activation until the explicit host preflight for NIC ownership, IOMMU/VFIO, hugepages, CPU/NUMA, privileges, and Kubernetes device resources passes.
- Keep coupled IBG separate from the datapath expansion. Its solver, state, observation, utility, learning, baseline, and acceptance requirements await explicit user instructions.
- Begin the expansion with a dedicated mathematical/parameter revision phase. Each user-directed change must state its intended formula or parameter behavior, be independently characterized with deterministic tests, and re-establish affected simulation/Kubernetes parity before becoming the new baseline for datapath work.
- Use the causal order hidden state -> state/load-conditioned replica latency -> selected private signal -> likelihood/posterior -> next-slot belief. Never infer and overwrite the experiment's true state from the telemetry used to learn it.
- Order states from 1 (bad) to 4 (good). Deterministic profiles are the validation ground truth; experiments may use seeded draws from a declared prior. A controlled state remains fixed for the run, and datapath mode is known context rather than a hidden state.
- Keep selected server processing latency as the physical $q$ variable. Its active law is $Q_\theta(n)=\mu_\theta+h_\theta(n,\kappa_\theta)+J_\theta$, where $J_\theta=|Z_\theta|$ and $Z_\theta\sim\mathcal N(0,\sigma_\theta^2)$. Actual $q$ alone supplies processing utility and SLA latency. The selected-only learning signal is $S_\theta=Q_\theta+E_\theta$, with an independent nonnegative observation half-normal $E_\theta$ and a likelihood conditioned on state, final assigned load, and known datapath mode. Only selected replicas emit it.
- Require state profiles to make bad replicas behave worse statistically through higher baseline latency/jitter, lower effective capacity, and steeper congestion response. Preserve assigned load, admitted concurrency, modeled and measured physical processing latency, observation jitter, noisy learning signal, client latency, and link/transport latency as separate correlated data.
- Replace the inverse utility kernel with $u_k(q)=R_k-\alpha_kq-c_k$, $\alpha_k>0$. Congestion is part of $q$ and must not be penalized again through the former $(1+\gamma n)$ factor.
- Interpret $q$ as latency, so utility is non-increasing in $q$; paper text describing utility as non-decreasing in latency must be corrected when the paper is next revised.
- Define realized end-to-end utility as summed stage utility minus explicitly weighted inter-stage link latency, and define SLA violations by per-flow end-to-end latency thresholds rather than hidden state IDs.
- Do not let replica-pair link latency silently invalidate stage independence. Constant or stage-separable link terms may enter the decoupled solver; pair-dependent link optimization belongs to the future coupled scope, though realized link latency is still deducted in reporting.
- Use injected/seeded latency samples and signal replay for exact mathematical parity. Judge live Kubernetes latency by calibrated distributions, state ordering, congestion response, and asymmetric selected-only sampling rather than exact wall-clock equality.
- Separate formula implementation from numerical calibration. Phase 1 uses provisional test profiles; Phase 2 declares a load horizon and reproducibly chooses latency, utility, link-weight, jitter, and SLA values.
- Calibrate ordered zero crossings $n_1^*<n_2^*<n_3^*<n_4^*$ so bad states become negative early and perfect states remain positive until declared high congestion. Fit latency behavior before choosing reward/cost parameters, and preserve the accepted values, units, target bands, seeds, curves, and sensitivity evidence.
- Prefer recorded grid/constrained search plus seeded Monte Carlo and live spot checks over undocumented manual trial-and-error. Direct utility sweeps beyond three flows are calibration evidence only and do not claim exact-solver scalability.
- Do not interpret negative utility as automatic rejection under the current one-of-M action contract. Maintain a feasible replica per stage over the supported range; any skip or flow-admission rejection policy requires an explicit later decision and new solver/orchestration tests.
- Accept the Phase 2 values as a synthetic design calibration for FastAPI test doubles, not an empirical Kernel, NIC, DPDK/VPP, or line-rate capacity claim. The authoritative state table is `CALIBRATED_STATE_PARAMETERS`; the old provisional name is a transition alias.
- Use a 12-flow direct-evaluation horizon and inclusive zero-crossing bands 3--4, 4--6, 6--8, and 10--12 for states 1 through 4. The active `half-normal-additive-v1` table `(base, ordinary congestion, knee, capacity, jitter scale)` is state 1 `(40,8,12,1,6)`, state 2 `(28,6,8,2,5.25)`, state 3 `(18,4,5,3,4)`, and state 4 `(10,2,2,5,3.25)`, with millisecond latency fields and concurrent-flow capacity. The superseded half-normal `(8,7,5.5,4.5)` scales and earlier symmetric `(4,3,2,1)` scales remain version-bounded historical results.
- The historical physical-plus-pair calibration fixed reward 100 utility units/stage, cost 1 utility unit, processing- and link-latency weights 1 utility unit/ms, and a 110-ms end-to-end SLA threshold. Its 12-flow evidence remains version-bound. The active user-authorized outcome contract is `physical-only-v1`: observed selected physical processing supplies realized utility and a 110-ms SLA. `physical-plus-pair-v1` remains an explicit reversible mode that restores the historical pair deduction. Both physical, pair, raw end-to-end latency, and both utility views must remain logged. This temporary-or-permanent reporting choice was made because the raw public-forwarder pair residual remains unresolved; it changes neither placement nor learning. Deployment profiles must retain cost 1; their legacy capacity/delay/gamma fields do not override the state latency table.
- Require the reproducible calibration gate to preserve state/curve ordering, target crossings, low-load positivity, a feasible option at load 3, at least 80% seeded classification accuracy, no more than 90% mean load-1 classification accuracy, the declared physical-latency SLA separation, and crossing bands under $\pm10\%$ latency/weight and $\pm5\%$ reward sensitivity. The upper accuracy bound records the user requirement that learning observations be meaningfully imperfect.
- For localhost FastAPI conformance, require five observations at baseline and post-capacity loads per state, every signal/likelihood/correlation boundary check, at least 80% categorical accuracy per point, and server scheduling overshoot no larger than $\max(10\text{ ms},10\%)$. This is not the future Kubernetes Kernel-mode tolerance; Phase 3 must measure that independently.
- Before accepting utility values above the current 12-flow per-replica horizon, perform the deferred 50-load synthetic calibration. Preserve the latency and linear-utility formulas and do not change `BR_EIBG`, placement, or a future heuristic as part of that calibration. Its approved target crossing bands are 3--6, 12--20, 25--35, and 45--50 for states 1--4; direct evaluation to 50 never claims 50-flow exact-solver scalability.
- Name the implemented Kubernetes HTTP path `kernel` at every traffic/telemetry boundary. Treat `simulation` as a comparison label, not a deployable datapath, and reject `dpdk-vpp` until its separate design and host-preflight phase is approved and implemented.
- Carry `datapath_mode` in controller-to-flow-generator requests, flow-generator health/responses, every hop, slot results, validation summaries, and JSONL events. Record the runtime image and host/Docker/kind/Kubernetes versions in the run-start event.
- Extend the FastAPI replica `/process` contract with explicit nonnegative observation jitter while keeping legacy zero-jitter payloads parseable. Kernel mode metadata and transport telemetry cannot alter the selected endpoint, final assigned load, noisy selected learning signal, likelihood, posterior, solver grid, placement, physical-only realized utility, or 110-ms SLA rule.
- Preserve historical Phase 3 transport fields and traces under their original per-hop definition, $\max(0,L_{\mathrm{request}}-Q_{\mathrm{processing}})$, but do not reinterpret them as direct consecutive-replica cost. For current traces, keep flow-generator ingress/request overhead separately labelled and exclude it from the pair metric. Measure each selected consecutive pair as $\max(0,L_{\mathrm{pair\ RPC}}-L_{\mathrm{callee\ route}})$, validate exactly `K-1` correlated records per flow, and sum only those records into raw end-to-end latency and the physical-plus-pair reference utility. This pair RPC cost includes ordinary Kernel networking and HTTP boundary work; it is not a claim of pure one-way propagation.
- Accept the Kubernetes Kernel scheduling tolerance when at least 95% of selected hops satisfy measured-minus-modeled processing overshoot $\le\max(10\text{ ms},10\%\text{ of modeled latency})$. Continue to require at least 80% categorical accuracy, load-1 state ordering, observed non-decreasing congestion groups, and exact signal/likelihood/correlation boundaries.
- Validate Kernel mathematical equivalence by replaying the captured selected processing signals, likelihoods, and per-flow transport values through the unchanged runner with deferred complete-route observations. Live measurements are distributional; replayed placements, grids, beliefs, utility, SLA, fairness, and equilibrium must be exact within numerical tolerance.
- Insert a user-directed evidence and report-curation phase before DPDK/VPP design. It may organize, summarize, visualize, and explain existing reproducible Kernel/simulation evidence, but it does not alter the solver, utility, belief signal, SLA, admission boundary, or datapath implementation. `Tutorial.md`, `Report.md`, and `EVIDENCE_SUMMARY.md` remain opt-in: read or edit one only when the user explicitly requests that file.
- Treat replay evidence as code-version-specific. The accepted Phase 3 trace predates the global belief-retention change from 0.6 to 0.8: its live Kernel telemetry remains directly summarizable, but its historical zero-drift replay claim must not be presented as current-HEAD parity. A fresh supported-size trace is required before claiming replay parity under retention 0.8.
- Set the user-directed equilibrium tolerance to a strict per-belief-entry change below 0.033 per slot (after brief 0.03, 0.037, and 0.04 settings). This changes only the stopping criterion; it does not alter placement, utility, latency observations, belief updates, or SLA classification.
- Let `scripts/run_experiment.py --runs N` perform N independent controller Jobs after one cluster/image/deployment preparation step. Each Job starts with a fresh controller/replica belief state and uses the requested seed; the option is intended for repeated live observations, commonly with `--skip-build`. Default behavior remains one run, and every run keeps a separate JSONL trace and, with `--csv 1`, a separate CSV column.
- Implement post-placement pairwise measurement without coupled placement. The exact decoupled solver selects the full route exactly as before; afterward, traffic traverses the selected replicas in stage order, and the measured consecutive-edge costs remain a raw end-to-end/reference-utility view. The active physical-only outcome does not deduct that residual; `physical-plus-pair-v1` restores it. Broad request-minus-processing overhead remains separately labelled telemetry and must not be substituted for pairwise link cost. Pairwise costs do not enter the utility grid or solver, and no coupled IBG behavior is authorized.
- Enforce the hardened pairwise evidence boundary: stale current flow-generator responses that omit required pair/ingress fields fail schema parsing; every pair record must match its source/target Pod and normalized target endpoint as well as stage/replica identity; summed pair costs must equal the reported per-flow raw link metric; and a run may not mix historical and pairwise schemas across iterations. These checks harden reporting/replay only and do not change the solver, placement, utility grid, belief update, or admission behavior.
- Isolate route forwarding from selected processing measurement with two processes/containers per replica Pod: a private processor on port 8081 and a public forwarder on port 8080. The processor is the sole source of physical processing, observation-only jitter, the selected noisy signal, and its likelihood; the forwarder executes only the already-selected route and records transport telemetry. Processor readiness runs a discarded deterministic warm-up sample without creating an observation or advancing the experiment's seeded samples. This is a runtime measurement-boundary correction, not coupled placement or a change to solver, utility, SLA, or rejection behavior.
- Use the implemented Phase 4, datapath-neutral `control_plane_v1` trace contract for a future Kernel--DPDK/VPP comparison. Per slot, record monotonic-wall and controller-CPU timing for discovery, admission/planning through route dispatch, and feedback processing after telemetry returns; report their active-control sum while keeping selected-route wait time separate as data-plane execution. Count controller-boundary HTTP application-payload bytes and messages for Kubernetes discovery, route command, selected telemetry, and reserved future belief exchange. Exclude forwarder-to-forwarder selected-route RPCs and do not claim transport/header wire bytes. This instrumentation must not alter solver behavior, placement, selected-only processing observations, beliefs, utility, pairwise reporting, SLA, or equilibrium.
- Use the completed bounded Phase 4 `solver_resource_v1` branch before any heuristic work. Opt-in `--memory 1` emits one block per completed slot: current controller RSS before admission, sampled active-slot peak, RSS after feedback, peak incremental bytes, exact-policy peak memo entries, post-embedding residual entries, and per-stage cache records. Current RSS comes from the controller process rather than Pod limits or a lifetime high-water mark. Report memory in bytes/MiB and cache in entries only—do not stack unlike units, relabel these as network telemetry, or derive them from old traces. A future stacked memory plot may use baseline RSS plus incremental working memory; cache entries remain a separate annotation/series. The instrumentation is off by default and does not change the exact solver, placement, selected-only learning, utility, SLA, pair measurement, or runtime resources. The user-run 15x8 result is exploratory Exact baseline evidence; a later separately authorized heuristic must use this identical schema and matched dimensions for a fair comparison.
- Treat deletion and recreation of the disposable local `ibg` kind cluster as the provisional recovery for a post-reboot infrastructure failure, not as a normal experiment step or a confirmed root cause. The observed persisted-cluster symptoms were intermittent in-cluster `Temporary failure in name resolution` and selected-route `ReadTimeout` failures despite Ready Pods; a fresh cluster restored the supported run. On the next reproduction, capture Docker, kindnet, CoreDNS, kube-proxy, node, DNS, and cross-node route evidence before deleting the cluster. This operational investigation must not alter IBG or datapath semantics.
- Report the decentralized selected-only learning-information burden through a separate `learning_signal_v1` logical footprint, not by relabelling `selected_telemetry_rx`. Canonically encode only stage, flow, selected replica, assigned load, noisy learning signal, and four-state likelihood for each selected hop; require exactly `flows * stages` records regardless of available replica count. Physical latency and observation-jitter diagnostics stay outside this logical projection. Report logical bytes and mean bytes per selected hop, while retaining the full flow-generator response as the independently measured controller-boundary telemetry payload. The logical footprint is neither actual wire traffic nor a raw-telemetry comparison and must not be used to claim byte savings that the current reporting envelope does not transmit.
- Treat `Chart/` as a user-directed legacy compatibility area. Modernize only explicitly authorized `.py` scripts against current host-side CSV/JSONL contracts; do not use a plot script to redefine metric semantics, mix historical/current schemas, or imply an unvalidated datapath result. Each authorized `Chart/<plot>/` folder is self-contained: its script defaults to primary and optional baseline CSV inputs beside that script, never shared `figures/`. Preserve its original visual design/theme and embedded text unless the user explicitly requests a change. Once authorized, iterative visual tuning stays local and is recorded in handoffs only when the user explicitly marks it final. Finalized plots are Jain, SLA-small version 2, and utility-small. The latter uses the current `realized_end_to_end_utility` CSV contract, preserves the original orange IBG mean/standard-deviation design, applies a trailing five-timeslot average, uses discrete timeslots and a 2,500--3,500 y-axis, and skips its optional sibling MILP input when absent. Every other Chart script remains opt-in.
- Preserve physical `half-normal-additive-v1` state scales 6/5.25/4/3.25 ms and separate them from the user-authorized `half-normal-observation-v1` learning-noise scales 7.2/6.3/4.8/3.9 ms. Active realized utility and the 110-ms SLA use observed physical latency only; raw physical-plus-pair utility/SLA values remain available through the explicit alternate outcome mode. Observation noise affects only the selected learning signal and subsequent beliefs.
- Compute learning likelihoods from the exact convolution of the independent physical and observation half-normal laws. Record physical processing latency, observation jitter, and noisy signal separately, requiring `signal = measured processing + observation jitter`. The seeded observation stream is independent from the seeded physical sample stream.
- Accept the observation scales locally because the seed-2050, 5,000-sample calibration produces 81.38% minimum categorical accuracy and 87.74% mean load-1 accuracy, satisfying the declared 80% minimum and 90% low-load maximum while leaving the physical SLA distribution unchanged. Current-image supported trace `runs/ibg-experiment-20260721T145856Z.jsonl` also passed the live Kernel gate and exact replay after the successful normal build/deploy. Do not revise either scale table without reporting new evidence first; older traces remain version-bounded.
- Earlier 15-flow/8-replica investigation traces are historical 110-ms physical-plus-pair evidence: they ended with 10/15 and 13/15 violations from high post-placement pair cost even though no final flow exceeded 110 ms before that deduction; a repaired 19-slot trace still finished at 14/15 violations with 62.06 ms mean final pair cost. A pre-observation-jitter trace also had 14/15 violations and 74.39 ms mean pair cost. The separated observation model is therefore not a proven direct cause. The active 110-ms physical-only contract is a reversible reporting decision, not a jitter, solver, or runtime remedy.
- Treat controller cache lifetime and pair-route variance as separate. The exact-policy cache repair removed the deterministic five-slot OOM and reduced the 15x8 median admission time to 10.06 s without altering exact behavior. The earlier one-worker separated/physical-only A/B did not confirm CPU throttling and therefore did not justify a resource change at that time. The later no-controller diagnosis established concurrent single-worker HTTP queueing, and the separately authorized Phase 4.1 two-worker validation then showed that the original 500m forwarder quota caused new correlated stalls. Use the measured Phase 4.1 allocation instead: two Uvicorn workers only for the public forwarder, request/limit 25m/1 CPU and 128/256 MiB memory; keep the private processor single-worker and unchanged.
- Diagnose the remaining pair-RPC residual with opt-in forwarding-path telemetry, not a semantics change. Historical `forwarding_path_v1` retains its shared-clock source-request, target-handler, and source-response boundaries. Current `forwarding_path_v2` preserves those aggregates while splitting target application ingress/dispatch, private-processor HTTP admission, private work, processor response, downstream-route wait, and completion; it also exposes the source local-response-to-outbound-request gap. Require v2 when diagnostics are requested from the current runtime, but keep `scripts/forwarding_path_summary.py` compatible with historical v1 evidence. These timestamps are valid only as same-clock Kernel diagnostics and must not be presented as one-way/wire latency or future cross-host evidence. Keep the existing pair-cost formula and all solver, learning, utility, SLA, and equilibrium inputs unchanged.
- Accept Phase 4.1 as a Kernel runtime correction, not an IBG logic change. Two public-forwarder Uvicorn workers reduce measured concurrent application queueing; they do not alter placement, the exact recurrence, utility grids, observations, belief aggregation, pair-cost semantics, SLA, or equilibrium. Retain the raw measured pair residual. The clean exploratory 15x8 trace `runs/ibg-experiment-20260721T191634Z.jsonl` and its zero-drift replay are comparison evidence only; the supported-size evidence remains `runs/ibg-experiment-20260721T145856Z.jsonl`.
- Treat the first live `forwarding_path_v2` result as localization evidence, not authorization for a resource or metric change. In `runs/ibg-experiment-20260721T202043Z.jsonl`, the dominant variable pair boundary is source request start to target ASGI ingress; same-worker and cross-worker means are effectively equal, selected-forwarder cgroup throttling is zero, and exact replay has zero drift. Do not retune CPU/memory, normalize the residual, or change SLA/utility/pair semantics. A further diagnostic may split the remaining combined boundary into source HTTP-client pool/connect/send, transit, target server admission, and response-read milestones before any runtime fix is selected.
- Accept `forwarding_path_v3`/`http_client_path_v2` as diagnostic-only extensions. Trace `runs/ibg-experiment-20260721T205120Z.jsonl` shows 418 TCP connects for 420 pair RPCs, 7.74--8.08-second inter-slot idle gaps, and then-default 5-second HTTPX/Uvicorn keep-alive windows. Treat expired pooled connections followed by concurrent reconnect bursts as the established source-boundary mechanism. The authorized controlled setting matches public-forwarder HTTPX `keepalive_expiry` and Uvicorn `timeout_keep_alive` at 30 seconds, above the measured slot gap, while retaining default HTTPX connection limits. This is an A/B configuration under evaluation, not evidence that the residual is solved. Do not alter pair semantics, resources, solver, learning, SLA, utility, or jitter as part of that test.
- Retain the matched 30-second keep-alive setting as the active Phase 4.1 runtime configuration while its result is diagnosed further. It applies only to the downstream public-forwarder HTTPX client and public Uvicorn server; local processor calls use a separate HTTPX client with the processor-compatible default window. The split avoids reusing a local socket after the single-worker processor's unchanged 5-second Uvicorn timeout. Its normal-build A/B trace `runs/ibg-experiment-20260721T210935Z.jsonl` reduced new connections from 418/420 to 243/420 and source-to-target-ingress mean from 13.23 to 11.38 ms, confirming that pooled connections now survive across slots. It did not establish stable pair cost: all-slot mean was still 42.19 ms/flow versus 43.22 ms before, with an unstable upper tail. Do not claim the Phase 4.1 residual solved, tune connection limits/resources, or change raw pair semantics from this one comparison.
- Keep the completed worker/runtime residual diagnosis diagnostic-only. `forwarder_runtime_v1` adds public-forwarder worker identity, bounded event-loop scheduling-lag samples, active diagnostic request counts, and best-effort source socket identity to v3 traces. It is additive: it must not change the raw pair formula, HTTP client configuration, runtime resources, solver behavior, placement, learning, utility, SLA, or equilibrium. Keep the existing `pool_wait_ms` name for trace compatibility, but describe it as source pre-transport time rather than a confirmed HTTPX capacity-pool queue; the current client leaves connection capacity unbounded.
- Treat source public-forwarder event-loop delay as a supported proximal contributor to the remaining residual, not a complete root cause. In normal-build exploratory trace `runs/ibg-experiment-20260727T105911Z.jsonl`, all 540 selected links carried the runtime block and link cost correlated 0.705 with source event-loop maximum lag; the 55 p90-tail links averaged 40.41 ms source maximum lag versus 7.95 ms in the lower half. The same association remains within reused connections, so reconnects are not the only contributor. Worker identity, socket grouping, route locality, active application concurrency, selected-forwarder cgroup throttling, and the collected global host-pressure/conntrack observations did not isolate a single bad worker or explain the tails. The remaining distinction—worker event-loop occupancy versus OS/runtime descheduling—requires separately authorized, read-only per-worker scheduler counters; it does not authorize a mitigation or retuning.
- DPDK/VPP work is deferred until further notice. Keep its read-only, fail-closed Phase 5 preflight (`dpdk_vpp_preflight_v1`) dormant as reference only; do not invoke, extend, test, or document it further without explicit user authorization. `dpdk-vpp` remains outside the deployable runtime allow-list and Kernel remains the only active/default mode.
- Temporarily freeze the current decoupled IBG-Exact chapter as the reproducible reference for a later IBG-Hybrid comparison. Do not change exact behavior, runtime, evidence, or schemas as part of opening the new chapter. IBG-Hybrid is not an authorization to infer or implement a heuristic: its objective, algorithm, telemetry boundary, matched experiment protocol, and acceptance criteria must be supplied and approved first.
- Supersede only the former lack of Hybrid authorization: the user has now supplied the initial scope and authorized coupled/budgeted IBG-Hybrid as the active development track. Keep IBG-Exact frozen throughout that work.
- Treat IBG-Hybrid as the coupled evolution of IBG-Exact rather than an unrelated simulation or infrastructure fork.
- Use the current `IBG_Hybrid/` files as an old prototype only. Preserve useful ideas, but replace behavior that conflicts with the paper or current Exact contracts.
- Implement one public IBG-Hybrid algorithm containing candidate pruning, limited lookahead, and Monte Carlo rollout components.
- Start Hybrid at 20 flows, 3 stages, and 10 replicas per stage.
- Require exactly one replica from every stage. A Hybrid action is a complete ordered route of length `K`; reject the old two-stage `L=2` action.
- Use one randomized flow order per slot because the complete route is one coupled action.
- Keep all route decisions belief-driven. Hidden true replica state must not be read by route scoring, link scoring, pruning, lookahead, or Monte Carlo.
- Include known consecutive-link cost, availability, and approved node/resource or budget feasibility in coupled action evaluation.
- Reuse the current Exact physical latency, separated observation jitter, exact learning likelihood, belief retention 0.8, selected-only learning, outcome modes, 110-ms active SLA, and strict `<0.033` equilibrium rule until an explicitly approved Hybrid calibration changes one of them.
- Reuse existing discovery, complete-route traffic, private-processor/public-forwarder, telemetry, result, and Kubernetes contracts wherever they are algorithm-neutral.
- Keep Kernel as the only active/default runtime. DPDK/VPP remains deferred.
- Print only compact metrics after each Hybrid slot. Preserve detailed routes, observations, beliefs, and rollout data in structured traces.
- Audit diagnosis-script compatibility after the main pruning/lookahead implementation. Defer `netem_v1` until the basic Hybrid simulation and Kernel integration are stable.
- Defer the paper's bandit-based adaptation to an optional final Hybrid phase.
  It is neither a replacement for the required pruning/lookahead/Monte-Carlo
  policy nor authorization to expand the observation boundary. Any UCB,
  Thompson-sampling, fallback, or rollout-kernel role requires separate
  fixtures and matched evidence.
- Before accepting Phase 0, resolve whether pruning size `C` counts replicas per stage or complete routes, whether lookahead scores focal utility or truncated social welfare, the exact meaning of depth `D`, the Monte Carlo continuation kernel, activation thresholds, and the units and aggregation of capacity/budget feasibility.
- Reject the old prototype's unenforced budget, two-of-three-stage action, hidden-state-derived link cost, post-hoc-only coupling, immediate-utility double count, unseeded Monte Carlo, old latency/learning/SLA semantics, import-time execution, and verbose per-flow output.

## IBG-Hybrid budget-action correction

The preceding Hybrid additions originally selected a complete three-stage SFC
route. The user has clarified that the active intended model is the general
budgeted formulation: `L=2`, exactly two distinct stages are selected, and
the remaining stage is bypassed entirely. This supersedes only the earlier
Hybrid complete-route interpretation.

- A Hybrid action contains exactly two `(stage, replica)` pairs with different
  stage IDs.
- `IBG_Hybrid/budgeted.py` defines `HYBRID_STAGE_BUDGET = 2` as the code-level
  source of truth. The current planner rejects another supplied value rather
  than silently changing the action shape.
- The policy jointly chooses the two stages and their two replicas; it does
  not independently choose the best stages or replicas.
- The skipped stage has no placement, processor request, observation, or
  utility contribution for that flow.
- The old prototype's two-of-three-stage action is not itself a defect. Its
  missing budget enforcement, incorrect link/hidden-state behavior, rollout
  double count, old stochastic contracts, and lack of modern adapters remain
  defects to repair.
- Hybrid must extend the Exact complete-route traffic contract to support a
  selected two-stage chain that may be noncontiguous or start after stage 1.
  The processor/forwarder split and all selected-only learning boundaries are
  retained.
- Accept `netem_v1` as an opt-in external transport-robustness test around the frozen IBG-Exact baseline. It uses a replica-Pod init container with only `NET_ADMIN` to apply configured normal-distribution delay/jitter on `eth0` egress, records that configuration in the trace, and is absent when `--netem 0`. It must not feed network delay into the processor-generated learning signal or change placement, utility/SLA inputs, the two existing jitter laws, or raw pair measurement.
- Evaluate `netem_v1` primarily through equilibrium, true-state posterior growth, and the fraction of selected Good/Excellent replicas under a matched no-netem run. Utility and SLA may be reported as secondary outcomes but do not prove that network impairment entered learning. Defer packet loss: a dropped selected request currently fails the complete slot, and retry, imputation, or missing-observation policies would change the experiment contract.
- Reject the current VMware host for genuine DPDK/VPP comparison: it has four visible vCPUs, one visible VMXNET3 PCI NIC, no separately identifiable dataplane NIC, zero hugepages, no IOMMU groups or VFIO device, and no installed VPP/DPDK tools. Do not detach the only management NIC, use unsafe no-IOMMU VFIO, or substitute VPP over a Linux interface and label it DPDK. Kernel remains the default and independently runnable.

## Deliberately deferred

- DPDK/VPP activation, SR-IOV, hugepages, NUMA tuning, real telecom CNFs, and line-rate claims until the corresponding planned phases and validation gates complete.
- Prometheus/Grafana until basic controller-provided telemetry works.
- Budgeted/coupled IBG migration until a separate mathematical scope is approved.
- Large-scale testbed sizing and remote/dedicated Linux hardware.

These omissions still allow validation of Kubernetes orchestration, sequential placement, asymmetric observations, congestion effects, belief learning, utility, SLA behavior, fairness, and control-loop runtime.

## IBG-Hybrid Phase 1 decisions

- Accept the import-safe `IBG_Hybrid` package boundary and remove the old
  import-time experiment loop from `IBG_Hybrid/main.py`.
- Keep `IBG_Hybrid/budgeted.py` as the single code-level owner of
  `HYBRID_STAGE_BUDGET = 2`; configuration, prototype planning, and prototype
  embedding reject any other value.
- Represent an action as exactly two typed selections from distinct stages,
  ordered by increasing stage ID. This canonical order defines deterministic
  enumeration and exact-tie behavior without independently ranking stages.
- Enforce the active three-stage problem shape in `HybridConfiguration`.
  Replica IDs must be positive and within the configured per-stage count.
- Represent pre-decision coupled load as one immutable global stage-major
  matrix. Committing an action increments only its selected replicas; the one
  skipped stage is absent from placement and load change.
- Make feasibility explicit through `FeasibilityResult` rather than encoding
  rejection in a score or an invalid replica ID.
- Use the exhaustive coupled oracle only as a tiny correctness fixture. Its
  objective and feasibility rules are injected, canonical ties choose the
  first action, and hard size limits prevent use at 20x3x10.
- Do not treat retained prototype pruning, rollout, latency, learning,
  utility, SLA, link, reporting, or output functions as Phase 1 correctness
  contracts. Production pruning/lookahead/Monte Carlo and Exact-component
  integration remain later phases.

## IBG-Hybrid Phase 0 final decisions

The paper, old prototype, and accepted initial target now differ as follows:

| Area | Paper text | Old prototype | Accepted Hybrid contract |
|---|---|---|---|
| Action/budget | General set permits `1..L`; other SFC text requires every stage | Always two stages but old `budget` was not authoritative | Exactly `L=2`, two distinct stage/replica pairs, third stage fully bypassed |
| Feasibility | Availability plus an underspecified node resource vector | No Ready/capacity enforcement | Ready plus declared positive per-replica assigned-flow limit; missing admission or pair-link metadata rejects the action |
| Node resources | CPU/memory/bandwidth capacity notation | Not implemented | Existing Pod requests are not per-flow charges; a future per-flow resource vector needs a new versioned contract |
| Pruning `C` | Prose says top `C` replicas per stage; notation table says paths | `C=8` per stage, then undocumented top-`X=8` joint actions | `C=5` feasible replicas per stage, dynamic belief/load-aware score, no `X`; 75 maximum `L=2` actions |
| Link coupling | Deterministic selected host-pair cost | Hidden true-state lookup and later post-hoc deduction | One required known directed selected-pair planning cost; no hidden state or measured runtime residual in selection |
| Lookahead value | Exact budgeted algorithm scores the focal player at predicted future loads; approximation wording says average utility | Adds current and future-player utilities and counts the focal immediate value twice | Evaluate the focal route once at projected loads; never sum future-player welfare |
| Depth `D` | Simulate the next `D` flows | Includes the focal action inside its depth handling | `D=2` future arrivals after committing the focal action; clamp to remaining flows |
| Monte Carlo | `S` epsilon-noisy greedy continuations; later text inconsistently mentions a bandit kernel | Unseeded `S=50`, epsilon `0.10` | `S=50`, epsilon-greedy joint continuation over feasible pruned actions; bandit deferred to Phase 10 |
| Activation | Example high contention `rho>0.7`, high priority, or high entropy; entropy threshold omitted | Monte Carlo path effectively always active | MC for normalized entropy `>=0.75`; else lookahead for contention `>=0.70` or high priority; else greedy |
| Seeds | Not specified | Entropy-seeded default RNG with no provenance | Independent versioned BLAKE2b flow-order and candidate/sample rollout seeds derived from one root seed |
| Learning/runtime | Sparse selected observations and a future sidecar blueprint | Old learning, utility, SLA, CSV, and prints | Reuse frozen Exact latency/learning/outcome/runtime contracts in later phases; compact slot metrics only |

Additional accepted decisions:

- Rank feasible replicas per stage by shared belief-driven expected stage
  utility at `current load + 1`, breaking ties by lowest replica ID. The
  paper's static-zero-load pruning phrase is superseded for this project by
  its own load-aware greedy definition and the active Exact latency model.
- Enumerate all pruned `L=2` actions at the initial `C=5`; do not add the old
  top-`X` cut or local search unless measured Phase 2 evidence later requires
  a separately accepted approximation.
- Score a complete action as the two selected expected stage utilities at the
  focal flow's projected final loads minus one known directed pair-link cost
  at one utility unit/ms.
- Use maximum Ready-replica assigned-load/capacity ratio as normalized
  contention. Use maximum normalized Shannon entropy among feasible pruned
  replica beliefs for uncertainty activation.
- Give Monte Carlo activation precedence over lookahead, and lookahead
  precedence over greedy, so exactly one internal path is selected for every
  decision.
- Future deterministic and stochastic continuations use joint greedy actions
  over the feasible pruned action set. MC epsilon exploration is uniform over
  that same set. Bandit logic cannot enter the core rollout kernel before
  optional Phase 10.
- Keep configured planning pair cost separate from the one raw measured
  selected-pair outcome record. The active two-hop physical-only outcome and
  110-ms SLA remain unchanged.
- Record contract/parameter versions, activation values and reason, flow
  order, root seed, derived seed scheme, focal candidate, and MC sample count
  in future Hybrid traces.

## IBG-Hybrid Phase 2 decisions

- Accept `IBG_Hybrid.policy.IBGHybridPolicy` as the single production-facing
  Phase 2 coupled greedy/pruning boundary. The old prototype policy and the
  tiny exhaustive oracle are not production dependencies.
- Keep the policy input belief-only: global loads, Ready/assigned-flow
  admission metadata, belief vectors, and configured directed pair-link
  costs. Do not pass runtime replica objects, true state, legacy replica cost,
  or measured pair residuals into Phase 2 selection.
- Reuse the frozen Exact analytical state/load utility through
  `IBG.latency_model.expected_state_utility`; form belief expectation in
  Hybrid without copying the Exact latency or linear-utility implementation.
- Extract the replica-local portion of Phase 0 feasibility into
  `evaluate_replica_admission_feasibility` and make complete Phase 0
  feasibility call it. This preserves the established rejection strings and
  rules while giving Phase 2 one authoritative Ready/capacity filter before
  pruning.
- Enumerate all structural canonical `L=2` actions for pre-pruning
  accounting. Prune only locally Ready/capacity-feasible replicas, at
  `current_load + 1`, independently per stage with `C=5`.
- Keep retained replica order as score-descending/lowest-ID-on-tie for
  inspection, but enumerate retained complete actions in canonical
  stage/replica order. Select by strict score improvement so exact complete
  action ties choose the first canonical action.
- Apply directed pair-link feasibility after forming a complete action.
  Score every feasible pruned action as the sum of its two cached
  belief-driven stage utilities minus the configured planning link cost at
  one utility unit/ms.
- Record both replica and complete-action accounting: available and locally
  feasible replicas by stage, retained identities, structural actions,
  complete feasible actions before pruning, total/feasible pruned actions,
  and deterministic rejection-reason counts.
- Raise `NoFeasiblePrunedAction` with the completed accounting when no valid
  complete action survives. Do not use an invalid replica ID, negative
  infinity, or a partial one-stage placement as a fallback.
- Keep lookahead, Monte Carlo, bandit, runner, traffic, learning, metrics,
  replay, Kubernetes, diagnostics, and netem out of Phase 2.

## IBG-Hybrid Phase 3 decisions

- Add deterministic limited lookahead as `IBGHybridPolicy.select_lookahead`;
  retain `select_greedy` unchanged as the Phase 2 continuation boundary.
- Derive later-flow count from the immutable state's complete `L=2`
  assignment count and configured slot size. Reject a decision after all
  configured flows have already been committed.
- For every canonical root-feasible pruned action, create an independent
  branch, commit the focal action once, and run exactly
  `min(D, remaining flows after focal)` joint-greedy continuations.
- Recompute Phase 2 admission feasibility, belief/load-aware pruning,
  directed-link feasibility, scoring, and candidate accounting at every
  continuation state. Do not cache a stale root candidate set across loads.
- Evaluate a completed branch only as the focal action's two stage utilities
  at the final projected loads minus its configured planning link once. Do
  not add the immediate focal score or any continuation-player welfare.
- Preserve canonical strict-improvement ties for both Phase 2 continuations
  and the final focal choice.
- Return the selected focal commit as `HybridSolverResult.state_after`.
  Retain simulated future states and continuation decisions only in immutable
  lookahead detail; they are not real placements.
- Record root Phase 2 accounting and the full Phase 2 decision/accounting at
  every continuation step. Treat a branch that cannot complete its required
  continuation as non-selectable, retain its failure accounting, and raise
  `NoFeasibleLookaheadAction` only when every focal branch dead-ends.
- Keep Monte Carlo, activation thresholds, flow ordering, orchestration,
  execution, learning, metrics, replay, Kubernetes, diagnostics, netem, and
  bandit work deferred to their existing later phases.

## IBG-Hybrid Phase 4 decisions

- Add `IBGHybridPolicy.select_monte_carlo` as the seeded rollout method of the
  existing public policy. Preserve Phase 2 `select_greedy` and Phase 3
  `select_lookahead` behavior unchanged.
- Attempt exactly `S=50` candidate-specific samples for every root-feasible
  pruned focal action. Commit the focal once per sample and clamp `D=2` to
  the actual later flows in the configured slot.
- Build every sample seed only through `RolloutSeedKey` and
  `derive_rollout_seed`, including root seed, slot, decision position, flow,
  focal action, and sample index. Use one local `random.Random` instance per
  sample and never a shared RNG.
- Recompute the unchanged Phase 2 feasible-pruned joint action set and
  accounting at every updated continuation state. Do not reuse the root pool
  as a continuation pool.
- Implement epsilon-greedy continuation exactly: probability `0.90` selects
  the Phase 2 greedy result; probability `0.10` draws uniformly from the
  current feasible-pruned tuple. At epsilon zero every step is greedy; at
  epsilon one every step is a seeded uniform exploration draw.
- Retain the current feasible action tuple and accounting with every rollout
  step so exploration membership and updated-state pruning are auditable.
- Score every completed sample only by the focal action at projected final
  loads, with the focal planning link deducted once. Do not add immediate
  focal value, continuation-player welfare, or another link deduction.
- Compute a focal candidate mean from completed samples only. Record failed
  samples separately; reject the candidate only if all `S` samples fail, and
  raise `NoFeasibleMonteCarloAction` only if every focal candidate is
  rejected.
- Preserve strict canonical focal ties on equal sample means. Greedy rollout
  ties remain Phase 2 canonical ties; seeded exploration is intentionally
  random within the complete current feasible pool.
- Keep automatic activation, flow-order randomization, runner/traffic,
  learning, metrics, replay, Kubernetes, diagnostics, netem, and bandit logic
  out of Phase 4.

## IBG-Hybrid Phase 5 decisions

- Accept `IBG_Hybrid.runner.run_hybrid_slot` as the pure Phase 5 lifecycle
  boundary. It orchestrates the existing `IBGHybridPolicy`; it does not
  duplicate or replace Phase 2 pruning/greedy, Phase 3 lookahead, or Phase 4
  Monte Carlo mathematics.
- Derive exactly one slot-wide flow order with
  `derive_flow_order_seed(root_seed, slot_id)` and one local RNG. Keep that
  stream independent from rollout, physical-processing, and
  observation-jitter seeds.
- Obtain activation inputs from the current feasible pruned action pool.
  Preserve total precedence: Monte Carlo at entropy `>=0.75`; otherwise
  lookahead at contention `>=0.70` or explicit high priority; otherwise
  greedy.
- Commit exactly the selected focal `L=2` action to real slot loads. Retain
  lookahead/Monte-Carlo continuation states only in immutable policy detail.
- Complete all 20 placements before observation generation. Require exactly
  40 selected observations and 20 selected-pair outcome records at 20x3x10;
  reject incomplete, duplicate, wrong-route, wrong-load, or unselected
  adapter data before learning.
- Keep hidden true state inside the in-process simulation adapter. Use
  separately derived physical and observation seeds and the unchanged Exact
  physical sampler, observation-only sampler, convolved likelihood, and
  state estimator at final assigned load.
- Reuse `IBG.learning.apply_observations` and the frozen Exact
  `Replica.local_update`/`Replica.aggregation` methods as the selected-only
  posterior/aggregation implementation. Apply the complete observation batch
  once, retain `0.8`, and keep strict equilibrium at every entry change
  `<0.033`.
- Compute expected Hybrid utility from the two selected stages at final loads
  minus configured planning link. Compute active realized utility and SLA
  only from selected physical processing. Preserve one simulated measured
  pair per flow solely in raw end-to-end latency and the physical-plus-pair
  reference utility.
- Call unchanged Exact linear utility, outcome-latency, `SLA_v`, Jain
  fairness, and equilibrium helpers. Do not copy formulas into Hybrid when an
  algorithm-neutral Exact helper applies.
- Keep Phase 5 results immutable and in memory. The runner prints nothing;
  the explicit printable wrapper emits exactly one compact line. Add no
  CSV/pickle sink, HTTP, containers, Kubernetes, replay, diagnostics, netem,
  DPDK/VPP, or bandit behavior.
- Treat the completed low-entropy 20x3x10 measurement as local pure-slot
  evidence only. Uniform initial beliefs activate full `S=50` Monte Carlo for
  every decision and exceeded the local command-session lifetime of 1,000
  seconds; do not turn that non-terminal attempt into a runtime result or
  weaken `C`, `D`, `S`, epsilon, seed ownership, or rollout detail to make it
  fit.

## IBG-Hybrid activation correction decision (pending implementation)

The earlier Phase 0/5 decision that activated Monte Carlo whenever maximum
normalized belief entropy was at least `0.75` is superseded. That threshold
is not sufficient by itself: the paper presents Monte Carlo as an exceptional
response to uncertainty following conditions such as scaling, failure, or
churn, while greedy pruning is the normal path and limited lookahead handles
contention or high priority.

Adopt an explicit immutable slot-level uncertainty-event flag, defaulting to
false. Automatic precedence will be: Monte Carlo only for
`uncertainty_event && entropy >= 0.75`; otherwise lookahead for contention
`>= 0.70` or high priority; otherwise greedy. Uniform initial beliefs alone
must therefore use the normal greedy/lookahead path. This does not change
`L=2`, `C=5`, `D=2`, `S=50`, epsilon `0.10`, any policy-method mathematics,
seed ownership, or the deferral of Bandit/UCB/Thompson work. Implementation
and tests remain the immediate next task.

### Superseding lookahead-default decision

The preceding activation correction is incomplete where it says greedy is the
normal placement path. For the active user-authorized IBG-Hybrid algorithm,
accept the paper's Pruned Lookahead Rollout as the default: every feasible
focal flow first receives `C=5` candidate pruning and then `D=2` lookahead,
with clamping only at the end of the slot. Future simulated flows use the
unchanged joint-greedy policy over their updated pruned feasible pool.

The paper's dynamic low-contention greedy commit describes an optional
fast-path variant; it is not enabled as the default Hybrid Lookahead decision
in this project. Greedy remains a continuation policy and an independently
reportable pruning-only baseline. Monte Carlo remains an exceptional branch
for explicit uncertainty/churn plus high entropy. This supersedes both the
old entropy-only MC trigger and the newly appended greedy-normal-path wording.

### Core-Hybrid and Monte-Carlo separation

Accept two distinct next steps. First complete the normal IBG-Hybrid
Lookahead algorithm: `C=5` pruning and default `D=2` focal lookahead for each
feasible flow, using joint greedy only as the continuation policy. Automatic
Monte Carlo is disabled for this core completion path, including during normal
uniform-belief startup.

Second, reopen Monte Carlo only as a dedicated design phase. The current
`75` focal candidates times `S=50` rollout structure took about 68 seconds
for one 20x3x10 decision and cannot be described as an operational fallback.
Do not mask that issue by silently lowering `S`, `D`, or the candidate set,
using stale pools, or claiming a runtime guarantee. Any scalable MC redesign
needs its own explicit contract and evidence before MC can be automatically
enabled.

### Core-lookahead correction accepted

- Version the corrected automatic-selection contract as
  `ibg-hybrid-policy-contract-v2`.
- Make `PipelinePath.LOOKAHEAD` the only path returned to automatic core slot
  orchestration. Continue recording entropy, contention, and priority as
  diagnostics without allowing them to trigger MC or greedy placement.
- Keep the last two effective horizons deterministic: for 20 placements at
  configured `D=2`, positions 1--18 use depth 2, position 19 uses depth 1,
  and position 20 uses depth 0.
- Permit immutable action-space reuse and belief-value/load utility
  memoization inside one `IBGHybridPolicy`. Cache identity includes the full
  belief value and load, so changed learned beliefs cannot reuse a stale
  value. These optimizations must not change feasibility, accounting,
  ordering, objective, or selected action semantics.
- Retain the explicit Phase 4 MC implementation only for correctness
  characterization. It remains inaccessible from automatic slots until the
  separate MC redesign is accepted.

### Current `D=3` manual override

Supersede the active default lookahead depth with `D=3` at user direction.
This is versioned as `ibg-hybrid-policy-contract-v3` and applies to the
current core lookahead runner for manual inspection. The explicit MC method
shares the parameter object but remains unreachable from automatic slots and
is still deferred for redesign.

### Professor-authorized MC decision

Accept a separate deterministic root-selection parameter `Q=10` for the
future production MC path. After ordinary `C=5` per-stage pruning and complete
action feasibility/scoring, retain the top ten canonical complete actions by
their immediate joint score. MC then gives each retained focal candidate its
full `S=50` seeded rollout budget. `Q` is not the per-stage pruning size and
does not replace `C`.

All simulated future flows use the unchanged Phase 2 greedy policy rather
than deterministic lookahead; active `D=3` remains their rollout horizon.
The selected candidate is the greatest mean focal-only projected value, with
canonical ties. No Bandit/UCB/Thompson policy is authorized. The historical
all-pruned-actions Phase 4 method remains a test/reference boundary only;
the new top-`Q` MC path is the required production redesign.

### `D=3` override reverted

The temporary manual `D=3` override is superseded. Restore default `D=2` as
`ibg-hybrid-policy-contract-v4` for ordinary pruned lookahead and the future
MC greedy-continuation horizon. This does not alter `Q=10`, `C=5`, `S=50`,
epsilon, or the no-Bandit decision.

## MILP baseline decisions

- Temporarily pause IBG-Hybrid and Monte Carlo work. Preserve the completed
  Hybrid core-lookahead implementation, the explicit historical exhaustive
  MC reference, and the unimplemented professor-directed top-`Q=10` redesign
  exactly as they are until the user reopens that track.
- Make `MILP/` the active workstream. Keep both `IBG/` and `IBG_Hybrid/`
  frozen while establishing the baseline.
- Implement the centralized coupled/budgeted MILP baseline, not the old
  decoupled per-stage model and not the recursive budgeted IBG/SPNE algorithm.
- Use `N`, `K`, and per-stage replica counts as runtime configuration
  variables. The initial paper-scale default is `N=15`, `K=3`, and 10
  replicas per stage (`M=30` total).
- Match the user-authorized Hybrid action budget: each flow selects exactly
  `L=2` replicas from two distinct stages out of three. The skipped stage has
  no assignment, load, processing, link endpoint, observation, utility, or
  SLA contribution. This project choice supersedes the paper's SFC-specific
  `L=K` remark for this MILP workstream.
- Interpret `L` as action cardinality. Do not reuse the old random replica
  `cost` field or hard-coded `B=20` as the stage budget. A monetary/resource
  budget would be a different, separately versioned constraint.
- Optimize the complete slot jointly for aggregate social welfare at final
  replica loads. MILP does not process flows sequentially and does not use an
  IBG flow-order, best response, pruning, lookahead, rollout, epsilon, or
  bandit policy.
- Give the MILP planner perfect true-state knowledge, as the paper explicitly
  defines this baseline. This exception is confined to `MILP/`; true state
  remains prohibited from Exact and Hybrid decision logic.
- Reuse the frozen state/load-conditioned physical-latency and linear-utility
  semantics. Compute deterministic expected physical utility under each
  known true state and final load; do not optimize the old two-state inverse
  utility, noisy observation signal, or measured wall-clock latency.
- Deduct exactly one configured directed planning-link cost for every selected
  two-stage route. Keep this coefficient separate from the later measured
  selected-pair outcome.
- Require exact `L=2` shape, Ready availability, declared assigned-flow
  capacity, valid replica IDs, and complete directed pair-link metadata.
  Missing metadata or infeasibility must fail explicitly rather than produce
  a partial placement or replica ID zero.
- Do not infer per-flow CPU/memory/bandwidth charges from Kubernetes Pod
  requests. Add node-resource constraints only after an explicit demand and
  node-capacity contract is accepted.
- Accept “MILP optimal” only with a proven optimal solver status. For a time
  limit or nonzero gap, report the incumbent, best bound, relative/absolute
  gap, runtime, backend/version, and termination reason without an optimality
  claim.
- Keep the formulation backend-neutral. The paper's result is specifically
  Gurobi 10.0; local correctness may use a declared open-source backend, but
  results must never merge runtimes or solver claims across backends.
- Keep solver construction/solve pure and import-safe. Imports may not run an
  experiment, seed global RNGs, print, or write CSV/pickle files.
- Do not make belief convergence an MILP stopping condition. Perfect-state
  MILP may execute selected routes and record matched observations for common
  telemetry, but those observations do not update or influence its policy.
- Reuse algorithm-neutral Exact simulation/runtime and metric helpers through
  adapters where semantics match. Reuse Hybrid's two-stage route *shape* if
  stable, but do not depend on Hybrid policy, candidate accounting,
  lookahead, Monte Carlo, activation, or learning behavior.
- Keep all MILP-specific documentation in these existing top-level handoffs;
  do not create Markdown files under `MILP/`.

### MILP cutoff decision

- Require a user-adjustable `--cutoff SECONDS` option on the future MILP
  command. Validate that it is finite and strictly positive and apply it to
  every solve invocation.
- Record the requested cutoff and actual solve duration with solver status,
  incumbent, best bound, and optimality gap.
- A cutoff is an operational limit, not an optimality tolerance. A feasible
  incumbent returned at the cutoff remains non-optimal unless the backend
  separately proves optimality before termination.

## MILP Phase 0 decisions

- Accept `MILP/phase0_contract.py` and
  `milp-coupled-phase0-contract-v1` as the formulation source of truth. It is
  pure and import-safe and does not import the unsafe legacy entry point.
- Record that the paper describes a centralized perfect-state MILP solved by
  Gurobi 10.0 at up to `N=15`, `K=3`, and `M=30`, but does not print a full
  linearized MILP. Treat the Phase 0 variable/constraint construction as the
  explicit project model for the user-authorized exact `L=2` action.
- Use one-based runtime-configurable flow, stage, and per-stage replica
  indices. The initial default is 15 flows, three stages, ten replicas per
  stage, and 30 replicas total. Require canonical stage/replica ordering, exactly two
  distinct selected stages, exactly one selected replica in each, and `K-2`
  fully bypassed stages per flow (one at the initial three-stage profile).
- Require complete admission metadata for all replicas and complete finite
  nonnegative directed planning-link metadata for all lower-stage/higher-
  stage replica pairs. Ready and assigned-flow-per-slot capacity constrain
  placement. Do not infer a flow-resource vector from Pod requests.
- Use binary placement `x`, selected-stage `y`, final-load indicator `z`
  (including load zero), and directed-pair `p` variables. Link placement to
  stage selection, load indicators, capacity, availability, and binary-AND
  pair variables through the Phase 0 constraint catalog.
- Maximize whole-slot social welfare at final loads. Each selected occurrence
  uses deterministic expected physical utility under its replica's known true
  state and final load; deduct exactly one configured planning-link cost per
  flow. Beliefs, private signals, learning, flow order, observation jitter,
  measured pair latency, and runtime telemetry are not planner inputs.
- Canonically order extracted records by flow/stage/replica. Do not claim a
  symmetric backend assignment is canonical. A later deterministic secondary
  solve or objective-preserving canonicalization must be documented; do not
  hide an epsilon objective perturbation.
- Validate `--cutoff` as finite and strictly positive seconds, without an
  implicit default, clamp, or rounding. Carry the same requested duration to
  the backend adapter and retain it in result provenance.
- Phase 1 must expose the runtime dimension variables through `--flow`,
  `--stage`, and `--replica`, alongside `--cutoff SECONDS`. The current
  Phase 0 module deliberately provides validation/configuration only, no CLI.
- Normalize maximization gaps as
  `absolute=abs(best_bound-incumbent)` and
  `relative=absolute/max(1,abs(incumbent))`. Only matching incumbent/bound and
  zero gaps with a proven backend status may set `optimality_proven`.
- Keep six distinct statuses: proven optimal, time limit with incumbent, time
  limit without incumbent, infeasible, unbounded, and solver/configuration
  error. Retain cutoff, build/solve times, backend/version, termination,
  incumbent, bound, gaps, and supported model counts.
- Select locally available SciPy 1.18.0 `scipy.optimize.milp` with embedded
  HiGHS 1.12.0 as the candidate development backend for later small
  deterministic correctness tests. It passed a trivial local solve. Gurobi,
  OR-Tools/CBC, PuLP, python-mip, highspy, Pyomo, GLPK, and standalone HiGHS
  are absent; install nothing in Phase 0. Never present SciPy/HiGHS evidence
  as Gurobi 10.0 or paper replication.
- Retain the twelve confirmed legacy mismatch categories as deterministic
  source-characterization tests. Do not import or repair the unsafe legacy
  experiment in Phase 0; replacement and CLI work begin in Phase 1.

## MILP Phase 1 decisions

- Accept `milp-coupled-phase1-boundary-v1` as the import-safe package and
  configuration boundary. Reuse the Phase 0 dimensions, action, admission,
  welfare, status, gap, and provenance types rather than defining competing
  semantics.
- Keep `N`, `K`, and uniform per-stage `M` as runtime CLI inputs named
  `--flow`, `--stage`, and `--replica`. Defaults are 15, 3, and 10; they are
  not limits. Require positive integers, `K>=L`, and keep `L=2` fixed.
- Require `--cutoff SECONDS` for explicit execution. Preserve the finite
  positive value exactly in `MILPConfiguration`; do not add a hidden default,
  clamp, rounding rule, or optimality interpretation.
- Store complete MILP planner inputs as canonical immutable tuples: every
  replica has true-state plus Ready/capacity data, and every structurally
  possible lower-to-higher-stage pair has one configured planning cost.
  Returned dictionary views are copies, not mutable stored state.
- Wrap a possible incumbent only with the unchanged Phase 0
  `SolverRunProvenance`, canonical placement, and
  `SocialWelfareBreakdown`. Incumbent presence and objective values must
  agree; Phase 1 introduces no new status or gap convention.
- Select the already installed SciPy 1.18.0 `scipy.optimize.milp` with
  embedded HiGHS 1.12.0 as the future free Phase 2 development backend. The
  Phase 1 gate detects capability and versions only; it does not solve a
  model. Install no other solver and make no Gurobi/paper-runtime claim.
- Limit the exhaustive oracle to tests with at most four flows and 100,000
  complete placements. It uses Phase 0 feasibility and final-load social
  welfare, preserves canonical exact ties, and must reject 15x3x10 before
  enumeration.
- Replace the legacy `milp_main` import-time experiment with a guarded
  configuration-only entry point. Retire the invalid old budgeted solver
  explicitly, and remove OR-Tools from legacy header import requirements.
  Preserve the Phase 0 mismatch catalog as historical evidence rather than
  preserving invalid executable behavior.
- Keep production model construction/solving, simulation, common outcome
  metrics, scale evidence, Kernel/Kubernetes reuse, replay, and diagnostics
  deferred to MILP Phases 2--6.

## MILP Phase 2 decisions

- Accept `milp-coupled-phase2-model-v1` and
  `milp-coupled-phase2-solver-v1` as the production-facing pure coupled MILP
  boundary. Keep model construction independent from SciPy data structures;
  translate to the free backend only inside the solver adapter.
- Implement the Phase 0 `x/y/z/p` formulation literally. Use explicit rows
  for `L=2`, selected-stage/replica linkage, Ready status, capacity, zero-
  inclusive final-load selection, load reconstruction, directed-pair AND
  linearization, and one pair per flow.
- Precompute every known-state/final-load stage coefficient with unchanged
  `IBG.latency_model.expected_state_utility`. Do not copy the latency or
  linear-utility formula into MILP and do not import Hybrid scoring.
- Negate stage welfare for SciPy minimization and add the configured planning
  link positively. Reconstruct the returned maximization objective through
  the Phase 0 helper before accepting an incumbent.
- Pass the exact requested cutoff to the primary SciPy/HiGHS native
  `time_limit` option and request `mip_rel_gap=0.0`. Count model build time
  separately from all solve/canonicalization time.
- Canonicalize proven optima with objective-preserving sequential secondary
  solves, one flow at a time, using only remaining per-run cutoff. Do not use
  an epsilon perturbation. If secondary canonicalization cannot finish,
  retain the valid proven primary optimum, normalize objective-symmetric flow
  labels, and record that only flow-label canonicalization completed.
- Validate backend vectors and every constraint independently before
  extraction. Reject fractional, out-of-bounds, incomplete, wrong-objective,
  or otherwise infeasible incumbents as solver/configuration errors.
- Normalize SciPy status and minimization bounds into the six Phase 0 result
  categories. A timed incumbent requires a finite bound and computed Phase 0
  gaps; a timeout without an incumbent remains distinct; only backend status
  zero with matching reconstructed objective receives proven-optimal status.
- Keep the Phase 1 CLI configuration-only until Phase 3 supplies an explicit
  complete problem/slot input. Do not synthesize default true states,
  readiness, capacity, or link metadata merely to make the CLI solve.
- Build but do not solve the 15x3x10 boundary in Phase 2. Its 5,475 variables
  and 14,115 constraints are structural evidence only; cutoff/scale behavior
  remains Phase 4 work.
- Continue deferring physical simulation, observations, SLA/fairness,
  15x3x10 runtime evidence, Kernel/Kubernetes traffic, replay, and diagnostics
  to MILP Phases 3--6.

## MILP Phase 3 decisions

- Keep the runner as orchestration around `solve_coupled_milp`; do not embed,
  duplicate, approximate, or fall back from the Phase 2 formulation.
- Execute only proven optima and validated timed feasible incumbents. Preserve
  the latter's unproven status and reject every result without a complete
  incumbent before generating an observation.
- Finish the centralized placement before simulation. Generate exactly two
  selected observations and one selected-pair outcome per flow, using final
  replica loads; bypassed and unselected replicas remain absent.
- Use independent deterministic local physical, observation, and measured-pair
  RNG streams. Seed derivation includes root seed, slot, flow, selected
  identity, and final load where applicable and never touches global RNGs.
- Reuse the frozen Exact state/load physical sampler, observation-only
  half-normal sampler, convolved likelihood, state estimator, utility/SLA,
  physical-versus-pair outcome separation, and Jain comparison semantics
  without modifying `IBG/`.
- Keep measured-pair outcome profiles outside `MILPProblemInput`. They are
  simulation-only data and cannot replace the configured planning-link
  coefficient or enter the solver objective.
- Retain likelihoods and noisy signals as telemetry only. MILP performs no
  belief update, posterior aggregation, equilibrium test, sequential flow
  ordering, Hybrid policy, or convergence loop.
- Keep the pure runner silent and results in memory. Permit only the explicit
  wrapper to print one completed-slot metrics line; keep all file reporting
  deferred.
- Validate the default 15x3x10 runner shape with a supplied complete incumbent
  in Phase 3, but reserve an actual cutoff-bound default solve and scale claim
  for the Phase 4 gate.

## MILP Phase 4 decisions

- Add a separate, versioned synthetic scale profile instead of making the
  ordinary dimension CLI fabricate true-state, admission, planning-link, or
  measured-pair data. The profile is benchmark evidence, not deployment data.
- Keep `--cutoff SECONDS` mandatory on the guarded benchmark and propagate it
  unchanged to the existing native solver limit. Do not reinterpret it as a
  hard process deadline or an optimality tolerance.
- Run each scale case through the public Phase 2 solver exactly once and the
  Phase 3 slot boundary only when a validated incumbent exists. Preserve
  timeout-without-incumbent evidence without simulation or fallback.
- Use a fixed increasing ladder `(1,2,1)`, `(2,3,2)`, `(5,3,4)`, `(10,3,6)`,
  `(15,3,10)` for local evidence while retaining arbitrary valid runtime
  dimensions in the public case constructor.
- Require exhaustive oracle equality only on deliberately tiny cases. Never
  invoke the oracle at the 15x3x10 boundary.
- Record process peak RSS as an explicitly scoped process-lifetime high-water
  mark. Do not label it solver-only memory or subtract an unreliable baseline
  after the process has already reached a higher peak.
- Record local SciPy/HiGHS results as free-backend evidence. Backend parity is
  unavailable because no second backend is installed; do not infer Gurobi
  10.0 or paper-runtime parity.
- Accept the actual 15x3x10 one-second result only as a time-limited feasible
  incumbent: objective 1628.29, best bound 2281.98, relative gap 0.401463.
  It is executable but not optimal.
- Keep evidence in memory and print one compact line per explicitly invoked
  case. Do not add CSV, pickle, JSONL, report files, HTTP, containers, or
  Kubernetes work in Phase 4.
- Permit `--verbose` only as an opt-in benchmark display mode. It prints a
  start banner and native HiGHS progress, including any objective-preserving
  canonicalization solves. Keep `disp=False` and one completion line as the
  default; verbosity must not change solver mathematics or evidence.

## MILP Phase 5 decisions

- Keep Exact and Hybrid frozen. Reuse their algorithm-neutral processor,
  forwarder, latency, observation, likelihood, outcome, and infrastructure
  boundaries without importing Hybrid policy logic or changing existing
  route behavior.
- Define a separate `milp-two-selected-stage-route-v1` contract. Require two
  distinct increasing stages per flow, permit noncontiguous and non-stage-1
  routes, permit different stage pairs across flows, and completely omit the
  other `K-2` stages.
- Discover the complete expected Running/Ready ordinal set before constructing
  `MILPProblemInput`. Missing readiness, profiles/capacity, or complete
  directed planning-link metadata is a configuration failure, not a partial
  model.
- Require planning-link metadata to be a versioned explicit document. The
  launcher accepts a user-supplied nonnegative `--planning-link-ms` and expands
  it to every structurally possible directed pair; no measured Kernel pair or
  legacy replica cost is used as an optimization coefficient.
- Invoke `solve_coupled_milp` exactly once per slot. Execute a proven optimum
  or validated time-limited incumbent while preserving its unproven label;
  fail every non-incumbent status before traffic and add no heuristic fallback.
- Complete placement before traffic, then execute all selected routes
  concurrently while preserving sequential execution inside each two-hop
  route. Validate final assigned loads from the complete route set.
- Reuse the unchanged private processor on port 8081 and public forwarder on
  port 8080. Preserve one processor worker, two forwarder workers, current
  CPU/memory requests and limits, separate HTTP clients, and the 30-second
  downstream keep-alive.
- Keep true state controller-private. It may enter the authorized MILP input
  and private processor configuration but never appears in an observation or
  public result. MILP performs no belief update or equilibrium iteration.
- Keep physical processing, observation-only jitter, noisy likelihood signal,
  configured planning link, measured pair, and raw end-to-end latency
  separate. Observation-only jitter never enters realized utility or the
  physical-only 110-ms SLA; Kernel telemetry never enters the MILP objective.
- Use an isolated `milp-testbed` namespace, MILP-specific flow generator and
  controller, separate image, and namespace-scoped get/list RBAC so Exact
  remains independently reproducible.
- Keep the pure/controller runner silent and allow only one compact completed-
  slot line by default. `--verbose` may add an immediate start banner and
  native HiGHS progress. Do not write CSV/pickle output or alter evidence.
- The Hybrid parity audit is outcome-only. The applicable latency, jitter,
  likelihood, utility, SLA, measured-pair, raw-reference, and Jain policies
  already agree; do not import Hybrid pruning, lookahead, Monte Carlo,
  activation, beliefs, or learning into MILP.
- Defer replay/diagnostic compatibility to Phase 6. Netem, forwarding-path and
  cgroup evidence extensions, DPDK/VPP, bandits, Gurobi, new calibration, and
  report generation remain outside Phase 5.

## MILP Phase 6 decisions

- Accept `milp-coupled-phase6-trace-v1` and
  `milp-coupled-phase6-replay-v1` as the MILP replay boundary. Traces are
  immutable, JSON-safe, in-memory by default, and perform no file output.
- Keep all authorized true-state/admission information inside the trace's
  explicitly private planner-input/replay section. Never add true state to a
  selected observation or treat it as measured telemetry.
- Make ordinary replay solver-independent. Reconstruct feasibility, final
  loads, final-load known-state welfare, configured planning-link deduction,
  physical-only utility/SLA, raw pair reference utility, and Jain fairness
  without building or solving a model.
- Categorize and reject contract, placement, load, configured-coefficient,
  objective, solver-status, observation-count, pair-count, metric, SLA, and
  fairness drift. Measured selected-pair latency can affect only outcome
  metrics and can never replace a configured planning coefficient.
- Keep solver replay optional. Require accepted objective and canonical
  placement equality only for a recorded proven optimum. A timed incumbent
  remains unproven even if a later rerun proves an optimum, and identical
  timed placements are not a reproducibility requirement.
- Treat controller timing and model resource accounting as MILP adaptations;
  treat Kernel HTTP/forwarding/cgroup telemetry as algorithm-neutral and
  opt-in; treat payload counts as logical records unless wire capture exists.
  Explicitly reject Exact memo-cache, learning-footprint, belief/equilibrium,
  and Hybrid pruning/lookahead/Monte-Carlo diagnostics as inapplicable.
- Keep every diagnostic opt-in and behavior-neutral. Optional process RSS is
  labelled process memory, separate from variable/constraint counts; no
  solver-only memory claim is inferred.
- Phase 6 does not authorize netem, new forwarding/cgroup instrumentation,
  DPDK/VPP, beliefs, bandits, Gurobi, new calibration, CSV/pickle/JSONL
  reporting, or changes to Phases 0--5.

## MILP Kernel live-repair decisions

Updated: 2026-08-01.

- Keep the existing absolute trailing-root-label Service and Pod DNS forms.
  Read-only in-Pod checks proved that both trailing and non-trailing names,
  including `kubernetes.default`, failed while cluster networking was stale;
  after restarting `kindnet`/`kube-proxy` and recycling only MILP workloads,
  the same absolute names resolved and cross-node connections succeeded.
- Treat the first failure as cluster lifecycle state, not a MILP cutoff,
  solver, URL, utility, or SLA defect. Do not hard-code Service or Pod IPs and
  do not weaken readiness checks.
- Record the live route rejection as a Phase 5 correctness gap: the Exact
  forwarder enforces a contiguous next stage and cannot execute every accepted
  `milp-two-selected-stage-route-v1` action.
- Correct that gap only with an isolated MILP forwarder boundary that permits
  exactly one strictly later selected hop, including 1 to 3 and 2 to 3. Do
  not modify Exact or Hybrid forwarder behavior, route contracts, algorithms,
  latency/jitter, utility/SLA, resources, clients, or keep-alive settings.
- The MILP-specific forwarder correction remains pending implementation and
  focused/live validation. Until then, retain the failed transcript and do
  not label the Kernel slot complete even though its primary solver run proved
  the attempted placement optimal.

### MILP Kernel forwarder correction accepted

Updated: 2026-08-01.

- Accept `milp-kernel-two-stage-forwarder-v1` as the isolated execution
  adapter for `milp-two-selected-stage-route-v1`. It permits exactly one
  strictly later selected hop and therefore supports both contiguous and
  noncontiguous two-stage actions.
- Keep the shared Exact validator as the default. The new protected hook and
  runtime-injection seam are behavior-preserving for Exact; unchanged Exact
  forwarder tests must continue proving that stage 1 to stage 3 is rejected.
- Change only the MILP StatefulSet forwarder application target. Preserve the
  processor/forwarder split, ports, workers, resources, HTTP clients,
  keep-alive, physical/observation laws, likelihood, pair telemetry, utility,
  SLA, and default diagnostic behavior.
- Require the live controller to run ordinary Phase 6 mathematical/outcome
  replay in memory before reporting completion. A replay failure fails the
  Job rather than emitting a successful metrics line.
- Treat a single trailing HTTP root slash as equivalent endpoint syntax in
  replay because `AnyHttpUrl` adds it during live serialization. Do not relax
  any other endpoint or Pod/stage/replica identity check.
- Accept the final 2x3x2 live gate as successful. It used one public solver
  invocation, exact `L=2`, two routes, four observations, two measured pairs,
  separate 4-ms configured planning cost and 14.045-ms measured-pair outcome,
  and successful replay. This is small live evidence, not 15x3x10 capacity or
  Gurobi/paper-runtime evidence.

### MILP Kernel launcher progress decision

Updated: 2026-08-01.

- Make the MILP Kernel launcher's preflight and deployment progress automatic,
  not conditional on `--verbose`. Users must be able to distinguish image
  work, cluster readiness, replica rollout, controller creation, and solver
  execution from terminal output alone.
- Report the requested physical footprint honestly: `stage * replica` Pods,
  two containers per Pod, and one processor plus two public-forwarder serving
  workers per Pod. A request above the 2x3x2 live boundary receives a capacity
  notice but remains runtime-configurable; no new arbitrary dimension cap is
  accepted.
- Keep native HiGHS progress behind `--verbose`, and keep controller result
  output, solver semantics, latency/utility/SLA policies, and no-file-output
  behavior unchanged.

## MILP experiment-input parity decisions

Updated: 2026-08-01.

- Accept `milp-experiment-profile-v1` as the same-input boundary for pure and
  Kernel MILP experiments. Equal dimensions/model counts are insufficient;
  the canonical profile fingerprint must match.
- Keep Phase 4 `milp-scale-synthetic-profile-v1` unchanged and separately
  labelled as scale evidence. Do not compare it with Kernel runtime unless
  both paths deliberately receive the same canonical input.
- Reuse only true state from shared Exact runtime profiles. Never interpret
  legacy `ReplicaProfile.capacity` as MILP admission.
- Define MILP capacity in `assigned-flows-per-slot`; use flow count as the
  dimension-aware per-replica default and expose
  `--assigned-flow-capacity FLOWS`. This is not calibrated capacity evidence.
- Retain uniform planning links but label them objective-constant under exact
  `L=2`. Accept a complete directed JSON table through `--planning-links` for
  pair-sensitive experiments.
- Fingerprint dimensions, cutoff, action cardinality, states, readiness,
  capacities, links, outcome-pair profiles, source, and modes. Never
  substitute measured pair outcomes into this profile.
- Keep solver/model/status/canonicalization behavior unchanged. Kernel-only
  endpoints and transport outcomes are added after shared placement is fixed.
- Accept the 2x3x2 same-input result as planner parity at that boundary, not
  15x3x10 capacity evidence or a Gurobi/paper-runtime claim.

### MILP planning-latency priority correction

Updated: 2026-08-01.

- Reject a uniform planning-link coefficient as the default latency-aware
  MILP experiment input. It remains permitted only as an explicit smoke/control
  case, because exact `L=2` makes its one deduction per flow objective-constant.
- Prioritize a deterministic complete heterogeneous directed planning-latency
  profile shared byte-for-byte by pure and Kernel runs. Its provenance and
  fingerprint must be retained.
- Keep actual measured Kernel pair latency as post-placement outcome telemetry.
  It must not be fed directly back into the same slot's solve or substituted
  for the declared planning coefficient.
- Do not alter the frozen state/load physical latency, jitter, utility, SLA,
  cutoff, central MILP formulation, or outcome separation while making this
  input-profile correction.

### MILP replica-rollout scalability investigation

Updated: 2026-08-03.

- Pause the pending latency-aware planning-profile implementation until the
  user resumes it.
- Prioritize a scoped investigation of MILP Kernel replica rollout scalability:
  scheduler fit, node capacity, Pod resources, readiness, startup failures,
  and actual resource consumption.
- Treat current per-Pod resources as a baseline, not a proven scaling optimum:
  processor 50m CPU/128Mi request and 1 CPU/768Mi limit; forwarder 25m
  CPU/128Mi request and 1 CPU/256Mi limit.
- Do not change resources merely to force a desired replica count. Any change
  requires measured evidence and rollout/readiness regression checks. Do not
  change MILP mathematics, latency, utility, SLA, learning, or Exact/Hybrid.

### MILP deployment ownership separation

Updated: 2026-08-03.

- Separate MILP's deployment-control surface from IBG before any scalability
  tuning: resource manifests, labels, ConfigMap/path, deterministic runtime
  profile source, and Kubernetes Ready discovery are MILP-owned.
- Preserve the current processor/forwarder worker counts and resource values
  during this separation. A later MILP-only resource or rollout change must
  not mutate `testbed/kubernetes_resources.py`, the IBG runtime profile, or
  IBG discovery labels.
- Retain only algorithm-neutral shared processor/HTTP and frozen Exact
  latency/outcome components where their semantics apply; sharing those does
  not make the deployment settings shared.

### MILP lean service-image decision

Updated: 2026-08-03.

- Split MILP controller and long-running service images without changing
  worker counts, requests/limits, processor behavior, route execution, or
  solver semantics. Only the controller may install/use SciPy/HiGHS and
  pandas.
- Do not infer a Pod RSS reduction merely from a smaller image. Measure RSS,
  CPU, Ready time, and rollout behavior at the target replica scale before
  changing resource specifications.

- Accept the first measured lean-image result at 12x3x6: the forwarder cgroup
  sample fell from 175.5MiB to 119.7MiB on average without changing its two
  workers; the processor remained about 40.6MiB. Keep requests/limits and
  worker counts unchanged until a separate controlled scaling decision.

### MILP processor right-sizing and bounded rollout decision

Updated: 2026-08-03.

- Apply the first MILP-only resource adjustment only to the private processor:
  retain 50m CPU request and one-CPU limit, lower memory request from 128Mi to
  64Mi, and lower memory limit from 768Mi to 256Mi. The sampled 40.6MiB
  processor footprint supports the cap for the tested service image, but a
  memory limit is a safety boundary rather than a mechanism that forces normal
  RSS lower.
- Preserve the public forwarder exactly: two Uvicorn workers, 25m CPU/128Mi
  request, and 1 CPU/256Mi limit. Its observed approximately 120MiB footprint
  and prior CPU-throttling evidence do not authorize a reduction.
- Accept a MILP-launcher-only bounded rollout control. It requires a positive
  `--rollout-batch-size`, defaults to two replicas per stage, applies the same
  target to every requested stage, and waits for all stages before a later
  batch. It must always finish at the user-requested per-stage replica count.
- This is solely an isolated MILP deployment/scheduling change. It does not
  change any Exact/Hybrid workload, MILP model/policy, physical or observation
  jitter, latency/utility/SLA behavior, traffic contract, or reporting.
- Accept the fresh 6x3x3 `2 -> 3` live gate: all nine replica Pods became
  Ready with zero restarts and the controller completed one valid MILP slot.
  Treat this as a small rollout/resource validation, not as a 12x3x6
  before/after or a larger-capacity guarantee.

### MILP existing-replica batching correction

Updated: 2026-08-03.

- Reject the original behavior that scaled every existing MILP StatefulSet
  down to the first batch before a scale-up. Batch size controls only newly
  required replicas when a consistent existing deployment is present.
- For example, default batch size two and existing three replicas/stage with
  target six must preserve the existing desired count and use `3 -> 5 -> 6`.
  A fresh topology still uses `2 -> 4 -> 6`; a lower user-requested target
  remains an intentional scale-down.
- Require all requested stages to exist with the same desired count before
  preserving an existing rollout. A partial or inconsistent MILP StatefulSet
  set fails explicitly, avoiding an unsafe implicit reconciliation.
- Do not claim this count correction preserves existing Pod processes. The
  current changed profile ConfigMap hash deliberately updates the Pod template
  and rolls existing Pods when dimensions/profile data change. A future
  non-disruptive profile-distribution design is separate from batching.

### MILP append-only profile scale-up decision

Updated: 2026-08-03.

- Remove the global runtime-profile hash from the MILP StatefulSet Pod
  template. It caused an unnecessary rolling replacement of every existing
  Pod whenever a new replica profile was appended.
- Permit non-disruptive scale-up only when the profiles of existing
  `(stage, replica)` identities are exactly unchanged. The launcher compares
  the live ConfigMap with the planned runtime profiles before applying it.
- Reject an attempted change to an existing identity's profile explicitly.
  An existing processor reads its profile at process startup, so silently
  changing the ConfigMap without a refresh would make controller and processor
  behavior disagree.
- Accept the one-time legacy-hash migration plus the live 5-to-6 gate: every
  ordinal 0--4 Pod UID remained unchanged; only ordinal 5 was created per
  stage. This preserves active Pod processes during append-only scale-up and
  does not alter workers, resources, traffic, MILP policy, or outcomes.

### MILP planning-link profile decision

Updated: 2026-08-03.

- Retain both mutually exclusive user controls. `--planning-link-ms` is the
  unchanged uniform smoke/control mode and is labelled
  `uniform-objective-constant`; `--planning-links PATH` is the latency-aware
  input boundary for a complete `milp-planning-links-v1` directed table.
- Treat only lower-stage-to-higher-stage replica pairs as valid, matching the
  frozen increasing-stage two-hop route. Require every such pair exactly once
  at the requested dimensions, with strict integer IDs and finite nonnegative
  millisecond coefficients.
- Retain planning-link source/version/mode with the canonical experiment
  fingerprint in pure and Kernel provenance. Equal dimensions are not enough
  for parity; equal canonical planner inputs are required.
- Accept an explicit deterministic example generator for repeatable tests and
  operating examples, but label it not calibrated and never select it
  implicitly. Empirical planning-link calibration remains a separate future
  evidence task.
- Keep measured Kernel pair latency outcome-only. No observed same-slot pair
  value may feed back into the centralized solve or mutate the configured
  planning profile.

### Future cross-baseline seeded hidden-state decision

Requested: 2026-08-03. Deferred; no current behavior changes.

- Add a general --seed control, defaulting to 2050, to initialize one
  deterministic hidden-state assignment per experiment.
- Do not regenerate hidden states at each slot/iteration. Keep the assignment
  fixed for the complete experiment and retain both the seed and full state
  map in provenance.
- For a fair IBG-Exact/IBG-Hybrid/MILP comparison, require the same generated
  state-profile seed or the same recorded state map across all baselines.
- Keep this state-profile seed distinct from physical/observation/flow-order
  outcome seeds. Changing it changes the planner population; it is not merely
  a telemetry-noise change.
- Implement only when explicitly reopened, with pure/Kernel parity and
  controlled profile-refresh behavior where running Pods must receive new
  state configuration.

### MILP temporary synthetic-scale profile decision

Updated: 2026-08-03.

- Accept `--planner-profile synthetic-scale` only as an opt-in diagnostic. It
  reuses the Phase 4 benchmark's complete state/capacity/link input for the
  requested dimensions and `--profile-seed`; it is not a default, calibration,
  or measured-network model.
- Require pure and Kernel builders to have the same canonical fingerprint, and
  require matching runtime Pod states before traffic.
- Keep normal `runtime` mode unchanged. Synthetic mode supplies its own links
  and rejects the two planning-link flags rather than mixing input sources.

### MILP profile-difficulty finding and temporary remedy

Updated: 2026-08-03.

- Accept the profile mismatch as the confirmed explanation for why a normal
  Kernel run and `MILP.benchmark` with equal dimensions may have radically
  different solver times. It is not evidence that Kubernetes accelerates the
  same MILP.
- The old runtime profile's repeated state pattern and smooth demo-link formula
  differ from the benchmark's hash-derived state/link tables. Do not attribute
  the effect to one coefficient without a separate ablation experiment.
- Use synthetic-scale only for a controlled same-input comparison. Keep normal
  runtime mode and future evidence-backed planning-latency calibration separate.

## IBG-Hybrid infrastructure feasibility decisions

Updated: 2026-08-06. Evaluation only.

- Accept the MILP deployment-ownership pattern as the required direction for
  a future Hybrid Kernel path, but require a separate Hybrid namespace,
  manifests, labels, ConfigMaps, profiles, discovery, controller, images, and
  rollout state. Do not share mutable deployment ownership with Exact or MILP.
- Accept the service/controller image split as reusable architecture. A Hybrid
  service image must contain only replica/forwarding/flow-generator runtime
  dependencies; a Hybrid controller image must contain the Hybrid policy and
  learning stack. Do not carry SciPy/HiGHS into either image without an actual
  Hybrid dependency.
- Preserve the algorithm-neutral processor/forwarder boundary: one private
  processor worker on 8081, two public-forwarder workers on 8080, separate
  clients, and the active keep-alive behavior. Require a versioned Hybrid
  exactly-two-hop validator supporting noncontiguous selected stages and routes
  beginning after stage 1. Do not use Exact's contiguous validation or import
  MILP's controller/solver behavior.
- Treat the MILP processor memory reduction to 64Mi request/256Mi limit as a
  candidate requiring Hybrid-specific evidence. Preserve 50m/1 CPU and the
  existing forwarder resources/workers as the initial baseline. No further
  resource reduction is accepted by this evaluation.
- Accept bounded all-stage batching, existing-count preservation, and
  append-only profile validation as reusable launcher behaviors. Scale-up must
  add only missing ordinals, keep existing identity profiles unchanged, reject
  drift, and wait for complete Ready coverage before starting Hybrid policy
  execution.
- Keep Hybrid beliefs/controller state out of Pod runtime profiles. Hidden
  state and observation-seed configuration may be distributed to processors;
  beliefs remain controller-private learning state and must persist correctly
  across Hybrid slots.
- Reject transfer of MILP's one-centralized-solve lifecycle, clairvoyant true
  state, assigned objective, SciPy/HiGHS dependency, incumbent handling, or
  one-slot controller semantics. Hybrid remains belief-driven, sequential
  within placement, and iterative across learning slots.
- Reject one combined final-scale infrastructure readiness gate. Each future
  Hybrid infrastructure phase requires separate authorization and acceptance;
  live scale increases occur only after the immediately preceding phase passes.
  Future Monte Carlo controller cost remains separate and does not alter
  replica resources or outcomes.
- This evaluation authorizes no code, manifest, image, deployment, resource,
  routing, algorithm, latency, learning, utility, SLA, or telemetry change.

## IBG-Hybrid MC professor-baseline decision

Updated: 2026-08-06. This supersedes the earlier planned `Q=10` production-MC
shortlist; retain that decision as historical context only.

- For production MC root selection, rank the complete feasible pruned action
  pool by its Phase 2 immediate joint score and canonical ordering, then retain
  the top five complete routes. If fewer than five routes are feasible, retain
  all of them. Candidates outside that set receive no production MC rollouts.
- Preserve current per-stage `C=5` pruning. The professor's five-route MC
  shortlist is a different quantity and must receive a distinct explicit name
  in code; it must not weaken or redefine per-stage pruning.
- Retain `S=50` independent candidate-specific rollouts and keep `D=2` as the
  accepted project MC horizon. Do not change D as part of this correction.
- Define MC noise solely as seeded epsilon-greedy future action choice:
  normally the updated-state Phase 2 canonical greedy action, occasionally a
  seeded uniform action from that same updated feasible/pruned pool. Do not
  call deterministic lookahead in a rollout and do not use hidden true state,
  physical/observation randomness, or measured pair outcomes for planning.
- Score and average the focal flow's projected final utility only, deducting
  its planning link exactly once. Preserve deterministic root ties and commit
  only the final selected focal action.
- Keep the historical all-feasible-root Phase 4 MC implementation as a named
  reference/test boundary. Keep automatic MC disabled; a future uncertainty
  event/activation decision is separate.
- Postpone every evaluated Hybrid rollout/resource optimization until the
  Hybrid Kubernetes/node implementation is explicitly reopened. This MC work
  authorizes no image, manifest, cluster, node, resource, batching, profile,
  or traffic change.

### IBG-Hybrid separate MC-depth decision

Updated: 2026-08-06. This supersedes the preceding statement that `D=2` is the
complete MC horizon.

- Split the overloaded depth meaning into explicit `D_LOOKAHEAD=2` and
  `D_MC=10` controls. `D_LOOKAHEAD` belongs only to normal deterministic
  Hybrid lookahead and remains unchanged.
- `D_MC` covers the first ten future simulated arrivals after a tentative MC
  focal route, clamped to the actual remaining arrivals. Each one uses the
  updated-state Phase 2 greedy policy with seeded epsilon noise.
- Complete every remaining hypothetical flow after that MC window with the
  pure canonical Phase 2 greedy policy. It has no epsilon noise, no
  deterministic lookahead, and no recursive MC. Its committed branch loads
  remain part of the focal route's final projected utility.
- Record both configured/effective depths in MC decision and sample detail.
  Do not retain an ambiguous shared depth field or silently alter
  `D_LOOKAHEAD` while changing `D_MC`.

## IBG-Hybrid professor-baseline MC implementation decision

Updated: 2026-08-06.

- Accept `ibg-hybrid-policy-contract-v5` as the active Hybrid policy contract.
- Keep per-stage pruning fixed at `C=5`; it continues to produce at most 75
  complete roots at three stages and `L=2`.
- Fix the production MC root shortlist at five complete routes, ranked by
  existing immediate joint score and canonical ties. Do not expose the old
  `Q=10` behavior and do not reinterpret per-stage `C` as this shortlist.
- Keep `S=50`, epsilon `0.10`, focal-only final-load scoring, and one configured
  planning-link deduction. Roots outside the shortlist receive no production
  samples and cannot be selected.
- Keep `D_LOOKAHEAD=2` and `D_MC=10` as independent parameters. The first
  clamped `D_MC` future arrivals use updated-state epsilon-greedy Phase 2;
  every remaining branch arrival uses updated-state pure canonical Phase 2
  greedy so its congestion still affects focal utility.
- Forbid deterministic lookahead and recursive MC everywhere inside an MC
  branch. The only stochastic choice is seeded uniform exploration from the
  current feasible/pruned action pool during the MC window.
- Retain the former all-feasible-root, lookahead-depth MC only through the
  explicitly named historical/reference method. It is not production policy.
- Keep automatic slot orchestration on deterministic lookahead. MC activation,
  parallelism, Kubernetes/node rollout work, and all infrastructure changes
  remain deferred and require separate authorization.

## IBG-Hybrid explicit MC execution and worker decision

Updated: 2026-08-06.

- Accept `--policy mc` as the only full-slot route to production MC; automatic
  activation remains unavailable. Omitting the option continues to select
  deterministic lookahead for every real focal flow.
- Accept bounded process parallelism only across independent shortlisted-root
  rollout groups. Keep real focal flows sequential because each sees the real
  committed load state from its predecessors.
- Set the explicit MC CLI default to three workers on the current four-CPU
  host, leaving one CPU available to the operating system. `--mc-workers N`
  remains a positive user override.
- Preserve seed-derived rollout behavior and canonical input-order collection;
  parallel completion timing must never affect placement or MC results.
- This is an execution-speed decision only. It does not revise v5 root
  selection, `C=5`, `S=50`, `D_MC=10`, the pure-greedy tail, focal objective,
  learning, or any outcome contract.

### Manual-MC boundary retained

Updated: 2026-08-06.

Keep Monte Carlo manually selected only through `--policy mc`. Do not add
automatic MC activation from entropy, contention, priority, uncertainty-event,
or any other runtime input unless the user explicitly reopens that scope.

### MC process-pool lifetime

Updated: 2026-08-06.

Create the bounded local MC process pool once per explicit MC slot, reuse it
for all sequential real focal decisions, and close it before simulation and
learning. This removes repeated worker startup only; it is not Kubernetes work
and does not permit concurrent real-flow placement.

## Hybrid Kernel implementation and optimization sequencing

Updated: 2026-08-06.

- Use the detailed Hybrid Kernel Phase 0--8 roadmap as one merged sequence:
  apply rollout/image/resource work with the implementation phase that needs
  it, rather than creating a parallel optimization-only track.
- Establish first a Hybrid-owned L=2 route contract and small live baseline;
  then add image ownership, bounded rollout, existing-replica preservation,
  append-only profiles, and resource decisions in their dependency order.
- Do not apply the MILP processor-memory candidate or any other resource
  reduction until Hybrid-specific cgroup and live-route evidence supports it.
- Preserve the existing one-private-processor/two-public-forwarder architecture
  as the initial reusable baseline. It is not permission to modify Exact or
  share mutable deployments/profiles with Exact or MILP.
- Treat each scale increase as an explicit evidence gate, not as a fixed final
  target. Hybrid MC controller resource needs are measured separately from
  replica service resources.

## IBG-Hybrid Kernel Infrastructure Phase 0 decisions

Accepted: 2026-08-06.

- Accept `ibg-hybrid-kernel-infrastructure-phase0-v1` as the Hybrid Kernel
  ownership contract. Hybrid owns `ibg-hybrid-testbed` and names its mutable
  Kubernetes objects with the `ibg-hybrid-` prefix. Exact and MILP namespaces,
  selectors, ConfigMaps, images, and rollout state remain foreign and frozen.
- Accept separate future image ownership:
  `ibg-hybrid-testbed:kernel-service-v1` for processor/forwarder/flow-generator
  responsibilities and `ibg-hybrid-testbed:kernel-controller-v1` for policy,
  learning, and slot orchestration. This freezes names and dependency roles;
  it does not build either image.
- Keep the processor runtime profile minimal and versioned: replica identity,
  hidden state, and observation seed only, with complete canonical coverage.
  Beliefs remain controller-private; admission capacity and planning-link data
  remain separate controller inputs.
- Require future discovery to accept only the exact configured set of Hybrid-
  labelled Running/Ready StatefulSet ordinals in the Hybrid namespace. Missing,
  duplicate, foreign, unready, mislabelled, or wrong-ordinal replicas must fail
  before placement or traffic.
- Freeze the controller ordering as discovery, complete sequential placement,
  traffic, telemetry validation, selected-only learning, and result emission.
  Preserve beliefs across slots, keep hidden true state out of planning, and
  keep MC manual-only.
- Reuse Exact's one-worker processor, two-worker forwarder, ports, split HTTP
  clients, and keep-alive behavior as an unchanged infrastructure boundary.
  Do not implement the Hybrid L=2 route extension until Infrastructure Phase 1
  and do not accept resource right-sizing until Infrastructure Phase 7.
- Phase 0 authorizes no manifest, Kubernetes API adapter, image build,
  deployment, cluster operation, traffic, route contract, resource change, or
  algorithm/outcome change.

## IBG-Hybrid Kernel Infrastructure Phase 1 decisions

Accepted: 2026-08-06.

- Accept `ibg-hybrid-two-selected-stage-route-v1` as the future Hybrid Kernel
  route contract and `ibg-hybrid-kernel-route-execution-v1` as its pure
  execution result boundary.
- Require exactly two selected hops per flow in increasing stage order. Permit
  noncontiguous stage 1 to stage 3 and stage-2-first routes. Require the
  explicit skipped stage to be exactly the one absent from the two hops.
- Require complete placement before route construction. Reconstruct final
  assigned loads from every committed focal action, use canonical flow order,
  and reject stale load values or endpoint drift.
- Require route execution to return exactly two identity/load-correlated
  processor observations and one identity-correlated measured pair per flow.
  Partial, extra, reversed, wrong-load, wrong-endpoint, or wrong-pair telemetry
  fails explicitly.
- Define selected-only outcome inputs from the two returned hop records. The
  skipped stage contributes no request, endpoint, observation, learning
  signal, physical processing total, or pair endpoint.
- Reuse Exact's public-forwarder implementation through a Hybrid subclass that
  changes only continuation validation to allow one strictly later selected
  stage. Keep Exact's contiguous forwarder frozen and unchanged.
- Reuse Exact's Kernel datapath, processor-response, measured-pair, convolved-
  likelihood, and state-estimation contracts directly. Do not import MILP
  solver/controller behavior or alter Hybrid policy, learning, utility, SLA,
  latency, jitter, or MC activation.
- Keep the HTTP service wrapper, Kubernetes adapters/manifests, images,
  deployment, and live traffic in later phases. Phase 1 authorizes no cluster
  action or resource change.

## IBG-Hybrid Kernel Infrastructure Phase 2 decisions

Accepted: 2026-08-08.

- Accept `deploy/hybrid-kubernetes/` as the sole Phase 2 manifest boundary.
  Use namespace `ibg-hybrid-testbed`, Hybrid-owned object names/labels/selectors,
  and namespace-scoped Pod `get`/`list` RBAC only. Do not share mutable
  ConfigMaps, Services, StatefulSets, Deployments, Jobs, images, or rollout
  state with Exact or MILP.
- Accept a small four-flow/three-stage/two-replica static manifest template for
  mocked Phase 2 validation. This is not a live, resource, or scale gate. Keep
  the controller Job outside the long-running Kustomize base so complete
  rollout remains a prerequisite for controller traffic.
- Accept `ibg-hybrid-kernel-runtime-profile-v1` as the processor ConfigMap
  document and `ibg-hybrid-kernel-controller-inputs-v1` as the separately
  mounted admission/planning document. Runtime profiles contain only replica
  identity, hidden state, and observation seed. Controller inputs contain
  assigned-flow capacities and directed planning links. Neither contains
  beliefs, and the controller must not mount hidden-state profiles.
- Require the Hybrid Kubernetes adapter to query only the Hybrid namespace and
  selector and to reject every incomplete or inconsistent Pod set before
  placement: missing, duplicate, unexpected, foreign, non-Running, unready,
  mislabelled, wrong-name, or wrong-ordinal Pods are errors.
- Accept the Hybrid-only ASGI processor, forwarder, and flow-generator entry
  points as wrappers around the completed Phase 0/1 and frozen Exact runtime
  boundaries. The flow generator accepts only
  `ibg-hybrid-two-selected-stage-route-v1`; Exact's contiguous request remains
  unchanged and invalid at the Hybrid endpoint.
- Reuse `run_hybrid_slot` as the controller lifecycle rather than copying
  placement, learning, or metric mathematics into Kubernetes code. Its traffic
  adapter is invoked once only after all focal placements, accepts no simulated
  pair-outcome input, and must validate the entire two-observation/one-pair set
  before selected-only learning.
- Accept `ibg-hybrid-kernel-observation-provenance-v1` for Kernel observations.
  It identifies the discovered Pod/UID/endpoint and deliberately has no pure-
  simulation physical or observation seed fields. Hidden true state is not a
  controller replica value, policy input, or observed signal.
- Keep configured planning-link cost and measured selected-pair latency as
  separate inputs. Preserve physical plus independent observation-jitter
  learning signals, the exact convolved likelihood, physical-only active
  outcome/SLA behavior, and skipped-stage absence.
- Preserve one private processor worker on 8081 with the current Exact
  50m/1 CPU and 128/768 MiB baseline, plus two public forwarder workers on 8080
  with 25m/1 CPU and 128/256 MiB, split HTTP clients, and 30-second public
  keep-alive. Do not apply the 64/256 MiB candidate before Phase 7 evidence.
- Phase 2 authorizes no image build/load, cluster start, resource apply,
  rollout, live traffic, automatic MC activation, netem, diagnostics, replay,
  reporting, calibration, resource right-sizing, or large-scale validation.

## IBG-Hybrid Kernel Infrastructure Phase 3 decisions

Accepted: 2026-08-08.

- Accept separate Hybrid-owned `Dockerfile.service` and
  `Dockerfile.controller` boundaries with the unchanged Phase 0 image names.
  Use explicit file allowlists rather than copying the repository wholesale.
- Accept narrow image-local `IBG_Hybrid` initializers so importing a service
  module cannot execute the eager repository facade. Use a behavior-identical
  L=2 compatibility module in both images instead of copying the legacy
  pandas/SciPy-bearing `budgeted.py`; this is packaging isolation, not an
  algorithm or configurable-budget change.
- Limit the service dependency manifest to NumPy, FastAPI, HTTPX, and Uvicorn.
  Copy only frozen Exact processor/forwarder dependencies and Hybrid service,
  route-contract, executor, and profile modules. Exclude controller, policy,
  runner, learning orchestration, belief retention, reporting, MILP,
  SciPy/HiGHS, OR-Tools, and pandas.
- Limit the controller dependency manifest to NumPy, FastAPI, and HTTPX. Keep
  deterministic lookahead, manually selected MC, selected-only learning,
  metrics, Ready discovery, controller adapters, and the Job entry point.
  Do not copy a Hybrid ASGI service entry point or install Uvicorn. Continue
  using the Exact route wire schema without starting any server.
- Accept image-local lean Exact header/report compatibility files containing
  only the frozen methods and functions exercised by Hybrid learning and
  metrics. Require functional equality tests against `IBG/header.py` and
  `IBG/report.py`. Do not change the frozen Exact source or its tests.
- Keep runtime profiles and hidden true state out of the controller image and
  Job mounts. Beliefs remain controller-private; capacity/planning inputs and
  measured pair outcomes remain separate.
- Preserve the Phase 2 commands, ports, worker counts, client split,
  30-second keep-alive, probes, and processor/forwarder resources. Resource
  reduction remains Phase 7 work.
- Permit local image builds only without pulling or new network access in this
  phase. The network-disabled service build proved the Docker definition and
  context but found no cached dependency wheels, so no completed image or
  in-image inspection is accepted. Do not build via new network access, build
  the controller, push, kind-load, deploy, or run live traffic until separately
  authorized.

### Infrastructure Phase 3 image-validation decision

Accepted: 2026-08-08.

- Accept the successfully built local service and controller images as the
  completion of the Phase 3 image gate. Their Phase 0 tags, numeric non-root
  user, commands, port ownership, dependency inventories, and source
  inclusions/exclusions were inspected directly.
- Accept a temporary BuildKit named-context bind mount of the user-downloaded
  wheelhouse for the controller build. Require `--network=none`; do not copy
  the wheelhouse into the repository or image. Keep the committed dependency
  manifest as the resolver contract.
- Accept a 300-second pip read timeout in `Dockerfile.controller` as a build-
  transport setting only. It changes no package range, policy, learning,
  telemetry, utility/SLA, runtime resource, or Kubernetes behavior.
- Require in-image import checks to remain read-only and network-disabled.
  Constructing/importing ASGI objects for inspection is allowed; starting
  Uvicorn, invoking the controller Job, contacting Kubernetes, or sending HTTP
  traffic remains outside Phase 3.
- Phase 3 is complete. Image loading, deployment, and the first live small-
  topology gate remain Infrastructure Phase 4 and require separate approval.

## IBG-Hybrid Kernel Infrastructure Phase 4 decisions

Accepted: 2026-08-08.

- Bound the first live Kernel gate to two flows, three stages, one replica per
  stage, two controller slots, four long-running Pods, and one finite Job.
  Keep the Phase 2 base reusable and put only the reduced profiles, controller
  inputs, replica counts, and validation Job in a sibling Phase 4 overlay.
- Keep the controller Job outside the long-running Kustomize boundary. Apply it
  only after all configured Hybrid replica ordinals and the flow generator are
  Ready. Do not treat Kubernetes scheduling or partial discovery as permission
  to send traffic.
- Require the live gate to exercise both a noncontiguous 1-to-3 route and a
  stage-2-first 2-to-3 route. Accept only exactly two selected observations and
  one measured pair per flow; skipped-stage requests, observations, learning,
  metric inputs, and pair endpoints remain invalid.
- Accept seedless Pod identity provenance for Kernel observations. Keep hidden
  state and observation seed only in Pod runtime profiles, beliefs only in the
  controller, and admission capacity plus planning links in the separate
  controller-input ConfigMap.
- Accept pure/Kernel semantic parity by replaying the already returned complete
  Kernel telemetry through the pure slot boundary. This validation sends no
  second flow-generator request and compares placements, final loads, belief
  updates, and metrics while excluding wall-clock elapsed time.
- Preserve the raw measured pair evidence without normalization. In particular,
  the first-slot 1-to-3 pair measured about 425.056 ms while its configured
  planning link was 0 ms. This does not enter physical-only realized utility or
  the 110-ms SLA and does not authorize diagnostics or latency-law changes.
- Preserve all Phase 2/3 processor and forwarder workers, ports, HTTP clients,
  keep-alive windows, probes, and resources. Infrastructure Phase 4 authorizes
  no rollout batching, append-only profiles, right-sizing, automatic MC,
  netem, diagnostics, calibration, or scale increase.
- Mark Infrastructure Phase 4 complete after two successful slots, exact Ready
  coverage, belief retention, semantic parity, and stable Pod UIDs with zero
  restarts/OOM/evictions. Infrastructure Phase 5 remains separately authorized
  bounded-rollout work.

## Hybrid live-cluster isolation correction

Accepted: 2026-08-08.

- Reject further Hybrid use of the historical `ibg` kind cluster. Its retained
  Exact/MILP state makes restarting the cluster an implicit start of unrelated
  workloads and violates the intended ownership isolation even though the
  Kubernetes namespaces themselves are distinct.
- Use only a dedicated single-node cluster named `ibg-hybrid` and context
  `kind-ibg-hybrid` for the small Hybrid live gate. Validate the exact node
  identity and reject foreign baseline namespaces or workload Pods before any
  Hybrid resource apply or traffic.
- Require the kind node image and both Hybrid images to exist locally. The
  isolated runner must not pull or download an image as a side effect.
- Default the dedicated live-gate lifecycle to deletion after success or
  failure so its memory is released. Retention requires an explicit
  `--keep-cluster`; cleanup may affect only `ibg-hybrid` and must never stop,
  scale, or delete the shared `ibg` cluster or frozen Exact/MILP resources.
- Keep the historical Phase 4 evidence valid, but supersede its operating
  procedure. Future Phase 4 repetition and Phase 5 rollout work must extend the
  dedicated-cluster boundary rather than reviving the shared cluster.

## Hybrid persistent lifecycle and skip-build phase assignment

Accepted: 2026-08-08. This latest decision supersedes only the automatic-
deletion/`--keep-cluster` portions of the preceding isolation correction.

- Retain the dedicated `ibg-hybrid` cluster, its node, loaded images, and
  Hybrid workloads after both successful and failed runs. Create it only when
  absent and validate isolation before every reuse. Normal completion must not
  be treated as cleanup.
- Keep cleanup as an explicit Hybrid-only action. It may delete `ibg-hybrid`
  but must never target the historical `ibg` cluster. Cluster recreation is a
  recovery event, not a normal experiment step.
- In the corrected Phase 4 runner, a normal rerun loads the already-built local
  service/controller images, explicitly restarts only Hybrid serving
  workloads, waits for Ready coverage, and replaces only the completed Hybrid
  controller Job. No image build is added retroactively to Phase 4.
- Assign the user-facing `--skip-build` option to Infrastructure Phase 5. Match
  Exact semantics across both Hybrid images: skip Docker build, skip kind
  image load, skip forced service restart, reuse the persistent node's images,
  but continue manifest/count reconciliation, Ready validation, and fresh Job
  creation. Fail closed when the node does not contain both expected tags.
- Keep append-only ConfigMap/profile behavior and proof of existing Pod UID/
  process retention in Infrastructure Phase 6. A Phase 5 `--skip-build`
  scale-up must not pre-empt or weaken Phase 6's profile-drift rejection.
- Preserve persistent-cluster reuse through Phases 7 and 8 so resource and
  incremental-scale evidence has continuous Pod/node provenance. Explicit
  recreation starts a new evidence lineage.

## Persistent Phase 4 lifecycle gate accepted

Accepted: 2026-08-08.

- Accept two consecutive small live runs on the same dedicated node as the
  Phase 4 cluster-lifecycle proof. The Docker container ID and Kubernetes node
  UID remained identical, while the shared Exact/MILP cluster stayed stopped.
- Accept the second run's service Pod UID changes as expected normal-run
  behavior because it deliberately reloaded images and forced only Hybrid
  service rollouts. Do not mislabel this as Phase 5 `--skip-build` evidence.
- Accept deletion/recreation of only the completed Hybrid controller Job as
  the correct per-run controller lifecycle. The dedicated node and serving
  boundary remain running after completion.
- Keep Phase 5 unstarted. Its acceptance must separately prove both images are
  already loaded, skip build/load/forced restart, and retain existing service
  Pod UIDs while still producing a fresh complete controller Job.
- For that future image-presence proof, inspect the node container runtime's
  normalized `docker.io/library/ibg-hybrid-testbed` tags and platform image
  IDs. Do not infer absence from `kind load` comparing the host manifest-list
  identity: the second Phase 4 run unnecessarily re-imported both images even
  though `crictl images` confirmed their node-local tags and platform images.

## Post-Phase-7 manual MC Kubernetes decision

Accepted for future sequencing: 2026-08-08. No implementation is authorized by
this decision alone.

- Insert Infrastructure Phase 7.5 after resource evidence and before
  incremental scale validation. Keep Phase 8 as the scale phase rather than
  combining the first MC integration with a topology increase.
- Expose Kubernetes MC only through explicit controller Job arguments
  `--policy mc` and `--mc-workers N`. With no policy argument, deterministic
  lookahead remains unchanged. Automatic MC activation remains prohibited.
- Reuse the existing frozen MC algorithm exactly: per-stage `C=5`, canonical
  top-five complete roots, `S=50`, `D_MC=10`, seeded epsilon-greedy window,
  pure greedy tail, focal final-utility scoring, canonical ties, and manual-only
  execution. Phase 7.5 is integration/resource evidence, not algorithm work.
- Keep the MC process pool controller-local, bounded, one per slot, reused
  across focal decisions, and closed before traffic/learning. Do not add MC
  workers to replica Pods or change the service image.
- Require pure/Kernel fixed-seed placement and final-load parity plus equality
  between one and multiple MC workers. Preserve complete-placement-before-one-
  request, exactly two observations/one pair per flow, skipped-stage absence,
  belief retention, selected-only learning, and hidden-state exclusion.
- Run the first live MC gate at the Phase 7-accepted topology with Phase 5
  `--skip-build` and Phase 6 profile/UID preservation. Record controller CPU,
  RSS, worker count, deadline, restarts, completion, and failure behavior
  without retuning service resources.
- Phase 7.5 authorizes no scale increase. In Phase 8, manual MC at each larger
  topology requires a separate choice and fresh controller sizing; lookahead
  success does not automatically authorize MC at that scale.
