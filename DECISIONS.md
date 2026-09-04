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
  `<0.04`.
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

## Hybrid Infrastructure Phase 5 rollout and image-reuse decisions

Accepted: 2026-08-09.

- Accept `ibg-hybrid-kernel-rollout-v1` as the Hybrid-owned, policy-free
  count/rollout contract. Require exactly stages 1--3 under the frozen Hybrid
  namespace, names, labels, selectors, Service identities, and Pod-template
  ownership, with one consistent existing desired count.
- Forbid implicit scale-down. A requested count below the existing count fails,
  equality is a rollout no-op, and a higher already-profiled count advances by
  deterministic bounded targets. Apply one target to all three stages before
  waiting for exact Running/Ready ordinals, and start no controller Job until
  the final target is complete.
- Reconcile manifests through a temporary count override that preserves the
  validated existing count before batching. Do not reapply the static
  one-replica overlay in a way that transiently shrinks a later persistent
  topology.
- Match Exact-compatible `--skip-build` semantics across both Hybrid images:
  no Docker build, no kind load, and no forced serving-workload restart, while
  isolation, manifest/count reconciliation, readiness, and fresh controller
  Job creation remain mandatory. `--skip-build` requires an existing
  `ibg-hybrid` cluster and never creates or contacts the shared `ibg` cluster.
- Derive each locally selected image's unique linux/amd64 config digest from a
  temporary offline OCI export, then require the same full config ID under the
  normalized runtime tag in each accepted node's `crictl` inventory. Do not
  compare the local multi-platform index digest with a node config digest, use
  kind-load output as presence evidence, or hardcode the Phase 4 short IDs.
- Accept `--pull=false --network=none` as the only normal-build mode in this
  runner. A missing local base/dependency/cache fails closed; no dependency
  download, image pull, host installation, or weakened image claim is allowed.
- Require pre/post UID and per-container restart-count equality for every
  existing serving Pod under `--skip-build`. Replacing the finite controller
  Job remains correct and does not imply persistence of controller-private
  beliefs across independent Job lifecycles.
- Keep the current live target at one replica per stage. Reject a requested
  count not already covered by both immutable runtime and controller profile
  documents. Append-only profile growth and its new-ordinal live proof remain
  exclusively Infrastructure Phase 6.
- Accept the unchanged-count live gate on the persistent node as Phase 5
  evidence: all serving UIDs/restarts and the node UID remained unchanged,
  only the controller Job was replaced, both required route shapes and full
  telemetry/parity passed, and the shared `ibg` nodes stayed stopped.

## Hybrid Infrastructure Phase 6 append-only-profile decisions

Accepted: 2026-08-09.

- Accept `ibg-hybrid-kernel-profile-expansion-v1` as the policy-free
  fail-before-write boundary and
  `ibg-hybrid-infrastructure-phase6-3x3x2-v1` as the exact target source
  identity. Keep the Phase 4/5 one-replica overlay unchanged as historical
  input rather than overwriting it.
- Preserve every old runtime identity, hidden state, and observation seed;
  every old admission capacity; and every old directed planning-link value.
  Permit only the three new runtime/admission identities and nine new links
  required for complete three-stage/two-replica coverage. Continue rejecting
  beliefs in ConfigMaps and hidden state or observation seeds in controller
  inputs.
- Treat the configuration change from two to three flows and one to two
  replicas plus the new source identity as document-level Phase 6 metadata,
  not permission to mutate an existing processor identity. Existing-profile,
  admission, or link drift remains a separately approved refresh operation.
- Require live deployed documents to be read and compared before either
  ConfigMap is reconciled. Missing old entries, duplicates, partial additions,
  unexpected identities, malformed/incomplete links, and runtime/controller
  configuration disagreement fail before a Kubernetes write or scale action.
- Require a server-side count-preserving dry-run and exact StatefulSet Pod-
  template equality before ConfigMap apply. Retain fixed ConfigMap names with
  no generator hash, profile checksum annotation, or `subPath`. Existing
  processors keep their startup-loaded immutable profile while new ordinals
  read the updated projected document.
- Require `--skip-build` for the Phase 6 target. Reconcile profiles first,
  verify their exact deployed contents, keep all existing Pod UIDs/restart
  counts, add only ordinal 1 at each stage, require exact 2/2 Ready coverage,
  and only then replace the finite controller Job.
- Accept the successful 3x3x2 two-slot live gate as Phase 6 evidence. Both
  required route forms, six observations/three pairs per slot, final loads,
  skipped-stage absence, belief retention, separated jitter/latency inputs,
  seedless provenance, and pure/Kernel parity passed while the shared `ibg`
  nodes stayed stopped.
- Keep processor/forwarder resources, images, workers, ports, clients,
  keep-alive, probes, policy, learning, metrics, utility, SLA, and jitter laws
  frozen. Phase 7 owns resource evidence; Phase 7.5 owns manual Kubernetes MC;
  Phase 8 owns any larger scale.

### Phase 6 explicit topology CLI decision

Accepted: 2026-08-09.

- Match the Exact/MILP dimension option names by accepting singular and plural
  flow, stage, and replica flags in the Hybrid Kubernetes runner.
- Treat the explicit tuple only as a selector for a complete approved profile:
  accept `2x3x1` and `3x3x2`, infer flow/stage from replica when omitted for
  compatibility, and reject every other tuple before cluster access.
- Keep the stage count fixed at three because the frozen L=2 Hybrid semantics
  select exactly two distinct stages while bypassing the third. Dimension
  syntax does not authorize a different action model.
- Print the resolved topology before an accepted execution. Do not create
  profiles dynamically, weaken append-only validation, scale beyond two, or
  pre-empt Phase 8 incremental approval.

## Hybrid Infrastructure Phase 7 resource decisions

Accepted: 2026-08-09.

- Accept `ibg-hybrid-kernel-resource-evidence-v1` as the policy-free live
  resource evidence boundary and retain both the historical 128Mi/768Mi
  baseline and the explicit processor-only 64Mi/256Mi candidate projection.
  Require exact live container coverage and keep CRI working set, CRI RSS,
  cgroup current/peak/events, process RSS, and CPU throttling as separate
  quantities.
- Accept processor requests 50m CPU / 64Mi memory and limits 1 CPU / 256Mi
  memory for the Hybrid Phase 7-accepted topology. The candidate's maximum
  processor cgroup peak was 46,583,808 bytes and maximum working set was
  42,487,808 bytes, leaving 221,851,648 bytes below its limit, with zero
  processor throttling, memory events, restarts, OOM/eviction, or post-Ready
  probe failure across the five-slot live gate.
- Keep each public forwarder unchanged at two workers, 25m/1 CPU, and
  128Mi/256Mi. Its candidate-run maximum cgroup peak was 129,314,816 bytes,
  maximum working set was 125,370,368 bytes, and its throttling/memory-event
  deltas were zero. This phase provides no authority to retune it.
- Keep the flow generator and controller declarations unchanged. The final
  controller gate completed in 6 seconds against a 600-second deadline,
  sampled 69,238,784 bytes maximum process RSS, used 2,396,824 CPU usec, and
  recorded 116,940 throttled usec. This remains ample lookahead evidence but
  does not size the future Phase 7.5 MC worker pool.
- Treat the processor resource change as an explicit rollout, not a violation
  of Phase 5/6 process preservation. Require the flow generator and dedicated
  node to remain stable, record all six new stage-Pod UIDs, and require zero
  restarts. A later unchanged candidate rerun must again preserve those new
  identities.
- Accept only startup-before-Ready connection-refused/503 probe events during
  the deliberate rollout. Any fatal resource event, node pressure, or probe
  failure after exact Ready coverage rejects the gate. The accepted run had
  no post-Ready probe failure and no Memory/Disk/PID pressure.
- Keep lookahead as the only Kubernetes policy in Phase 7. Phase 7.5 remains a
  separate manual-only `--policy mc` integration/resource gate at this same
  topology and accepted service-resource profile. Phase 8 remains the only
  larger-scale authority.

## Hybrid Infrastructure Phase 7.5 manual MC decisions

Accepted: 2026-08-09.

- Accept `ibg-hybrid-kernel-mc-controller-v1` as the controller-only policy
  interface. Omitted policy remains deterministic lookahead. MC requires both
  explicit `--policy mc` and `--mc-workers N`; the worker count is positive and
  capped at two, the largest value measured by this gate. Reject workers with
  lookahead and prohibit automatic MC.
- Reuse the frozen top-five-root, `S=50`, `D_MC=10`, epsilon-greedy-window and
  pure-greedy-tail implementation unchanged. One bounded executor belongs to
  one slot, is reused across every focal placement, and must close and join
  before traffic, telemetry processing, learning, or the next slot. Never
  silently fall back to lookahead on worker failure.
- Accept a controller-only source ConfigMap mount for this no-build gate. It
  overlays only controller adapter/validation/CLI files in the finite Job and
  is not mounted by any serving workload. This preserves the explicit ban on
  rebuilding or loading images while keeping the future controller Dockerfile
  complete. Runtime profiles, controller inputs, beliefs, and hidden state do
  not enter this ConfigMap.
- Accept fixed-seed one-worker/two-worker equality for placements and final
  loads and same-policy pure/Kernel replay parity for every live slot. Kernel
  physical and measured-pair timings may vary between separately executed Jobs
  and remain outcomes, not policy inputs or parity targets.
- Retain the existing controller requests 100m CPU / 256Mi and limits 2 CPU /
  1Gi. The one-worker Job used 3,367,647 CPU usec, zero throttled usec, a
  62,308,352-byte cgroup memory peak, and 71,356,416-byte maximum process RSS.
  The two-worker Job used 3,408,358 CPU usec, 897 throttled usec, a
  67,727,360-byte cgroup memory peak, and 71,315,456-byte maximum process RSS.
  Both completed in eight seconds with 592 seconds of deadline margin, so no
  controller or service resource change is accepted.
- Keep Phase 8 as the sole incremental-scale authority. Phase 7.5 authorizes
  neither larger flows/replicas/stages nor automatic MC at any scale.

## Hybrid Infrastructure Phase 8 Gate 1 decisions

Accepted: 2026-08-09.

- Accept exactly `4x3x2` as the first Phase 8 incremental topology and retain
  `2x3x1` and `3x3x2` compatibility. Require explicit
  `--skip-build --flow 4 --stage 3 --replica 2`; reject every other new tuple
  before cluster contact. This decision does not authorize a final scale.
- Treat the `3x3x2 -> 4x3x2` transition as flow-only. Advance only the source
  identity and `num_flows`; preserve all six runtime profiles, admission
  capacities, and twelve planning links exactly. Reject any old-entry drift
  or incomplete coverage before ConfigMap reconciliation.
- Keep admission capacities at two flows per replica. The live gate produced
  admission-safe final loads totaling eight selected placements, so no
  controller-only capacity expansion is needed at `4x3x2`.
- Preserve every StatefulSet template and serving process across this gate.
  ConfigMap reconciliation may not imply a scale or rollout; only the finite
  Phase 8 controller Job may be recreated. Existing processors retain the
  immutable profile loaded at process start.
- Keep Gate 1 deterministic-lookahead only. Omitted policy remains lookahead,
  `--mc-workers` is absent, and MC at `4x3x2` or any larger topology requires
  separate Phase 8 authorization and controller evidence.
- Retain the accepted Phase 7/7.5 resource declarations. Two live slots had
  zero serving throttling/memory events/restarts, no fatal or post-Ready probe
  event, no node pressure, and 578 seconds of controller deadline margin;
  there is no evidence-based reason to retune service or controller resources.
- Leave the next Phase 8 increment undecided until separately authorized. The
  present headroom supports considering a `5x3x2` lookahead-only flow step,
  while MC at `4x3x2` remains an independent alternative requiring its own
  controller measurement. Neither path is automatically approved by Gate 1.

## Hybrid dynamic-topology correction decisions

Accepted: 2026-08-09.

- Treat the `2x3x1`, `3x3x2`, and `4x3x2` tuple whitelist as historical
  incremental-gate evidence only. The final Hybrid launcher accepts any
  positive flow and replica counts, fixes stages at exactly three, resolves
  dimensions before cluster contact, and continues to reject implicit shrink.
  `--skip-build` means image reuse, not topology selection.
- Accept `ibg-hybrid-kernel-dynamic-topology-v1` as the generation rule.
  Preserve canonical profiles exactly; cycle same-stage canonical hidden-state
  templates only for missing ordinals; derive new observation seeds solely
  from stage/replica identity using the reserved Cantor-pair rule. Do not add a
  general seed flag, beliefs, or hidden state to controller inputs.
- Set each replica's admission capacity to
  `ceil(num_flows / num_replicas)`. This guarantees enough aggregate capacity
  in every stage for all flows. Capacity changes are legal only when this
  formula changes; arbitrary deployed admission drift remains an error.
- Require all three increasing stage pairs and the complete `R x R` replica
  cross-product. Preserve accepted links exactly and assign new pairs their
  canonical stage-pair value. Planning links remain pre-placement metadata and
  measured pairs remain post-traffic telemetry.
- Require deployed documents to match the deterministic rule before mutation,
  proposed documents to match the exact generated target, and every old
  runtime/link entry to remain unchanged. Reconcile fixed-name ConfigMaps only
  after a server-side dry run proves no StatefulSet Pod-template mutation.
- Reuse the Phase 5 equal-stage bounded rollout and exact Ready checks. At the
  accepted `10x3x5` gate, targets were four then five and only ordinals 2--4
  were created. The controller Job remains forbidden before final complete
  Ready coverage.
- Accept the live two-slot lookahead gate and its unchanged rerun as the first
  proof of the corrected interface. Each slot produced twenty observations and
  ten measured pairs after ten complete placements; route, learning, belief,
  provenance, jitter/link, admission, final-load, and parity checks passed.
- Retain all Phase 7/7.5 resource declarations. The resource preflight fit the
  then-current one-node allocatable envelope, sampled serving peaks remained
  below limits, the controller retained 584 seconds of deadline margin, and no
  memory event, serving restart, OOM/eviction, post-Ready probe failure, or
  node pressure occurred. Do not add a node or retune resources automatically
  as part of dynamic scaling. A separately authorized topology correction will
  use one Hybrid control-plane node plus one worker node, with all Hybrid
  workloads scheduled on that worker; it requires its own inventory,
  placement, resource, and parity gate.
- Recognize a correctly labelled completed dynamic controller Pod as
  Hybrid-owned during reuse preflight. It is finite rollout state, not a
  foreign workload; delete/recreate only its Job after isolation validation.
- Keep MC manual-only. This correction does not authorize MC at `10x3x5`, an
  automatic policy switch, scale-down, new stages, resource changes, or edits
  to the frozen Exact/MILP trees.

## Hybrid completed-slot console decisions

Accepted: 2026-08-09.

- Use one Hybrid-owned formatter for pure lookahead, pure MC, Kernel
  lookahead, and manual Kernel MC. Formatting begins only from a completed
  immutable `HybridSlotResult` and may not affect solver, traffic, learning,
  metrics, equilibrium, or storage.
- Print one structured human block immediately after each validated slot and
  before the next slot begins. Include only iteration/slot, active outcome
  mode, per-flow latency, predicted/realized/physical/raw utility, SLA count,
  fairness, execution time, and equilibrium.
- Do not display flow order, placements, observations, learning signals,
  beliefs or belief changes, detailed machine evidence, or CSV-writing text in
  the experiment console.
- Treat `aggregate_expected_utility_per_flow` as the already-summed result of
  the selected stage components. Do not reconstruct it from placement details
  or add presentation data to the solver contract.
- Keep `physical-only-v1` as the active Hybrid outcome mode. Therefore the
  displayed outcome latency and realized utility intentionally match the
  physical view; pair and raw end-to-end values remain separate references.
- Preserve complete Kernel validation evidence as prefixed controller output,
  but filter it from the human host console. The host follows logs live,
  retains normalized JSON privately for current evidence consumers, and still
  performs the existing finite-Job and serving-process checks.
- Carry the formatter in the controller image and the existing controller-only
  no-build source ConfigMap. Do not add it to or mount it in service Pods.
- This presentation change authorizes no Exact edit, CSV behavior change,
  image build/load, deployment, live traffic, topology/resource change, or
  automatic MC activation.

## Hybrid production experiment lifecycle decisions

Accepted: 2026-08-09.

- Make `run` the normal Hybrid Kubernetes experiment interface. Require
  explicit positive `--flow`, `--stage`, `--replica`, and `--max-iterations`;
  keep stages fixed at three and retain plural topology aliases.
- Keep `run-small` as a compatibility boundary for historical infrastructure
  evidence. It may retain fixed slot counts and route assertions, but the
  production controller must not call `run_small_live_gate`.
- Accept `ibg-hybrid-kernel-experiment-lifecycle-v1` as a thin sequential loop
  over the existing stateful controller adapter. Emit each completed slot before
  the next call, stop on the first frozen equilibrium result, otherwise stop at
  the exact positive maximum, and report reached/not reached plus the completed
  iteration count.
- Preserve beliefs only inside the controller adapter across slots. The loop
  rejects belief discontinuity and does not introduce a ConfigMap, service,
  policy-input, or hidden-state channel.
- Propagate the requested limit into the rendered dynamic Job rather than a
  manifest constant. Remove the historical 600-second active deadline only for
  production rendering so it cannot pre-empt the explicit iteration bound;
  historical gate deadlines remain unchanged.
- Supersede the earlier decision to show per-flow latency in the human console.
  Show no `Latency:` section or per-flow latency text. Preserve every latency
  calculation and field in `HybridSlotResult` and machine evidence unchanged.
- Retain immediate host log following and hide prefixed JSON from the human
  console. Do not print placements, flow order, observations, learning signals,
  beliefs, CSV messages, or raw evidence.
- Keep lookahead as the omitted-policy default. Keep MC explicit and preserve
  the existing Kubernetes restriction to accepted `3x3x2` candidate resources
  and one or two workers; do not infer general dynamic-topology MC support.

## Hybrid intentional replica scale-down decisions

Accepted locally: 2026-08-11. Live `8 -> 5` evidence requires separate approval.

- Supersede the Phase 5 prohibition on explicit scale-down. A positive
  user-supplied `--replica` is an intentional target: equality is a no-op,
  increases use bounded batches, and decreases use one exact all-stage target.
- Version the rollout result as a direction-aware contract with separate added
  and removed ordinals. For `8 -> 5`, permit only zero-based ordinals `5--7` to
  disappear; never remove a retained ordinal or recreate the cluster.
- Require deterministic source and target profile generation before mutation.
  Preserve retained runtime identity/state/seed and planning links exactly;
  permit only high-ordinal profile/admission removal and links with a removed
  endpoint. Admission changes remain limited to `ceil(flows / replicas)`.
- During scale-down, keep the old complete ConfigMaps until the higher Pods are
  absent. Dry-run the target, scale and wait first, then reconcile reduced
  ConfigMaps, revalidate templates/documents/readiness, and only then start the
  finite controller Job.
- Under `--skip-build`, preserve retained Pod and flow-generator UIDs/restarts
  and explicitly prove removed Pods absent. Do not claim preservation for an
  intentionally removed Pod.
- Treat scale-down as zero added Pods in resource preflight. Preserve all
  resources, images, workers, ports, clients, probes, keep-alive, algorithms,
  telemetry, learning, utility, SLA, jitter, and production-loop behavior.
- Reuse only the MILP direct-target rollout concept. Do not copy its current
  scale-up-oriented profile validator, which is not a correct complete
  scale-down validation path.

## Hybrid initial/final belief-console decision

Accepted: 2026-08-11.

- Supersede the blanket human-console belief omission only at production-run
  boundaries: print one initial snapshot before slot one and one final snapshot
  after equilibrium or maximum-iteration termination.
- Retain belief-free per-timeslot metric blocks; do not print belief deltas,
  learning signals, observations, placements, or flow order.
- Reuse Exact's title, alignment, ordering, bracket, and three-decimal vector
  style, but omit its state/capacity/delay/gamma columns. Hidden processor state
  remains unavailable to and undisclosed by the Hybrid controller.
- Apply the snapshots equally to default lookahead and explicit MC production
  runs. Do not change the historical `run-small` gate or any mathematics.

## Hybrid reproducible offline image-build decision

Accepted locally: 2026-08-11.

- Replace cache-dependent Hybrid Docker pip installation with versioned local
  service/controller wheelhouses. Keep wheel binaries ignored and local; commit
  their exact manifests and transitive lock files rather than ephemeral `/tmp`
  paths.
- A normal run validates both complete wheelhouses before any cluster action or
  Docker build, then builds with `--pull=false --network=none`, kind-loads both
  Hybrid images, and restarts only Hybrid serving workloads. It must fail closed
  on missing, unexpected, incompatible, lock, or recorded-digest wheel data.
- `--skip-build` deliberately bypasses wheelhouse validation as well as build,
  kind-load, and serving restart. It remains bound to local node-image tag/config
  validation and the existing topology/reconciliation/Job boundary.
- Require Dockerfiles to install only from their matching copied wheel cache
  using pip `--no-index --find-links`; no downloader, package-manager network
  installation, Python index configuration, MILP source, SciPy/HiGHS, or
  OR-Tools is permitted.
- Permit the explicit helper to copy already supplied wheels only after it has
  validated the complete source set. Do not add an automatic download path.

### Offline build evidence

- The user explicitly authorized the one-time pinned wheel acquisition on
  2026-08-11. Both wheelhouses validated and clean network-disabled local builds
  succeeded. This is local image evidence only: no kind load, deployment,
  container start, or Kubernetes mutation was authorized or performed.

## Hybrid seeded hidden-state allocation decision

Accepted locally: 2026-08-11.

- Require `--profile-seed` on the normal production `run` CLI. Keep it separate
  from policy root, flow ordering, MC rollout, physical jitter, observation
  jitter, and observation-seed domains. It controls hidden-state placement only.
- Accept `ibg-hybrid-profile-state-allocation-v1` with the fixed public
  Very Good/Good/Bad/Very Bad mix `30/30/20/20`. Use deterministic ten-replica
  strata with exact `3/3/2/2` counts and hash-ranked feasible prefix choices.
  Every arbitrary prefix must remain within one replica of its ideal quota.
- Require the allocator to be a stable infinite per-stage prefix: same seed and
  dimensions are byte-identical, scale-up never changes an existing identity,
  and scale-down removes only higher ordinals. Retain the independent stable
  observation-seed rule.
- Keep seeded provenance only on the processor runtime side. Do not place the
  profile seed, state mix, hidden state, observation seed, or reconstructable
  allocation information in controller inputs or controller mounts.
- Preserve legacy fixed documents as historical fixtures. Treat the legacy
  generator as compatibility behavior, not the production seeded interface.
- Require explicit `--refresh-runtime-profiles` for any existing allocation-seed
  transition. Restrict refresh to `--skip-build`, equal replica counts, and no
  resource-template rollout; replace only identities whose hidden state changes,
  stage by stage with exact Ready gates. UID preservation does not apply to those
  deliberate replacements.
- Do not change policy, lookahead, MC, learning, utility, SLA, equilibrium,
  latency/jitter, routing, metrics, console output, or belief initialization.


## Hybrid management/workload node-separation decisions

Accepted locally: 2026-08-15. Live replacement of the current cluster remains
separately gated.

- Use exactly one kind control-plane and one kind worker named
  `ibg-hybrid-control-plane` and `ibg-hybrid-worker`. This is management/workload
  separation inside one physical host, not multi-worker or multi-host evidence.
- Give only the worker `ibg-hybrid.workload-node=true`. Require that selector on
  every Hybrid replica, flow-generator, and finite controller Job Pod template.
  Do not rely only on the default control-plane taint.
- Fail closed unless both nodes are Ready, their control-plane/workload roles are
  disjoint, and every existing Hybrid workload Pod is bound to the worker. The
  historical one-node cluster is not an in-place migration target for the new
  runner.
- Validate both Hybrid images on both kind nodes while collecting serving CRI
  statistics from the worker that actually hosts the containers.
- Size dynamic admission against worker allocatable resources only. Count
  existing nonterminal worker-bound requests plus the unchanged proposed
  replica/flow-generator/controller requests; exclude control-plane management
  demand and terminal Jobs from the worker workload sum.
- Preserve every accepted Hybrid algorithm, L=2 routing, selected-only learning,
  physical/observation jitter, physical-only outcome utility/SLA, planning-link
  versus measured-pair separation, telemetry, resource declaration, rollout,
  profile, and console contract. Preserve frozen Exact and MILP sources.
- Require separate approval before deleting or replacing the current live
  `ibg-hybrid` cluster. A future clean-cluster gate must prove actual worker-only
  replica/flow-generator/controller placement, worker resource fit, restart and
  readiness safety, and unchanged pure/Kernel parity before this correction is
  accepted as live evidence.
- Make no same-worker/cross-worker, multi-host, NIC, SR-IOV, DPDK/VPP, hugepage,
  line-rate, or datapath-performance claim from this topology.


## Hybrid two-node bootstrap readiness decision

Accepted: 2026-08-15.

- Do not treat kind's control-plane-oriented create-time Ready message as proof
  that the dedicated worker has completed its join.
- On fresh creation, wait explicitly for both exact Hybrid node identities to
  become Ready, then run the unchanged strict topology/isolation preflight.
- Retain the newly created dedicated cluster after a fail-closed post-create
  error; do not delete it implicitly. A subsequent normal run may reuse it
  after the inventory passes.
- This is lifecycle ordering only. Do not weaken worker-only scheduling or
  alter Hybrid/Exact behavior, resources, telemetry, or evidence claims.

- Treat an existing validated dedicated cluster with no Hybrid namespace as a
  resumable pristine bootstrap, not as a deployed cluster and not as grounds
  for implicit deletion. Once the namespace exists, retain all strict existing-
  state discovery and reconciliation requirements.


## Hybrid two-node confirmation-recording decision

Accepted: 2026-08-15.

- Record the user's successful corrected live test as functional confirmation.
- Do not invent or preserve unreported dimensions, placements, parity values,
  telemetry values, restart counts, resource measurements, or run artifacts.
- Treat this as sufficient closure for the requested functional topology work,
  but not as formal performance or datapath evidence.


## Deferred Hybrid robustness and footprint decisions

Accepted for future planning: 2026-08-15. Implementation is deferred until the
user explicitly resumes each workstream.

- Add a Hybrid opt-in `tc/netem` robustness mode while keeping Kernel as the
  only runtime path and ordinary runs unchanged. Start with controlled
  delay/jitter and matched no-impairment runs. Do not add packet loss, retries,
  imputation, or missing-observation semantics without a separate decision.
- Preserve the separation between transport impairment, physical processing
  jitter, and observation-only learning noise. Netem must not become an input
  to placement, learning, utility/SLA, or the declared pair formula.
- Verify the existing Hybrid CSV functions before deciding whether to retain,
  repair, wrap, or replace their production interface. Tests must use temporary
  outputs and must not rewrite historical CSV data.
- Prefer host-side, explicitly enabled CSV generation from completed structured
  Hybrid results. Do not restore import-time file writes or require Kubernetes
  persistent storage.
- Add a versioned, opt-in per-timeslot Hybrid control-plane footprint. Define
  payload categories, byte serialization, and message-count boundaries before
  implementation; distinguish application/logical bytes from network wire
  bytes and exclude selected-route forwarder RPCs.
- Preserve all accepted Hybrid algorithm, pruning/lookahead/MC, profile,
  separated-jitter learning, physical-only outcome, utility/SLA, telemetry,
  rollout, worker placement, and frozen Exact behavior across all three items.


## Hybrid persistent JSONL trace decisions

Accepted and implemented locally: 2026-08-15.

- Persist every successful production Hybrid run to a timestamped host-side
  JSONL trace under `runs/` by default; allow `--trace-dir` only to relocate the
  destination.
- Wrap the unchanged per-slot controller evidence in versioned `run_started`,
  `iteration_completed`, and `run_completed` lifecycle records rather than
  depending on ephemeral Job logs.
- Fail before file creation if slot coverage, configuration, observation count,
  or per-flow measured-pair evidence is incomplete or inconsistent.
- Do not require cgroup/solver-resource diagnostics for the experiment trace,
  and do not persist processor-private hidden-state allocation provenance.
- Keep trace persistence host-side and behavior-neutral. It must not change the
  Hybrid algorithm, MC/lookahead selection, learning, utility/SLA, telemetry,
  workload placement, Kernel route, or frozen Exact implementation.


## Hybrid 80-ms SLA decision

Accepted: 2026-08-15.

- Set only the Hybrid SLA threshold to 80 ms. Preserve Exact's 110-ms default.
- Keep `physical-only-v1` as the active Hybrid SLA basis: compare the sum of
  the two selected physical processing latencies with 80 ms.
- Continue recording measured pair and raw physical-plus-pair latency as
  references; do not include pair or observation-only noise in active SLA
  classification.
- Do not rewrite or reinterpret historical Hybrid traces. New traces carry the
  explicit 80-ms threshold in every slot.
- This threshold change affects classification only. It does not change
  placement, policy, pruning/lookahead/MC, learning, latency generation,
  utility, telemetry, routing, resources, or worker scheduling.


## Hybrid random-series decisions

Accepted and implemented locally: 2026-08-15.

- `--runs N` owns all seed selection. It must reject `--profile-seed` and
  `--refresh-runtime-profiles`; users provide no seed value in series mode.
- Draw one nonzero 63-bit profile seed from the operating system CSPRNG only
  when a fresh Hybrid environment needs one, then keep that environment fixed
  for the complete series. Reuse the recorded profile seed when an existing
  seeded Hybrid environment is present, and fail closed for an existing
  unseeded/legacy environment whose allocation cannot be proven.
- Draw a distinct nonzero 63-bit experiment seed for every run. Use it as both
  the policy root seed and first slot ID so all experiment-side randomized
  streams, including Kernel processor request sampling, vary automatically.
- Create a fresh finite controller Job with fresh uniform beliefs for each
  member while reusing the prepared workloads and image after the first run.
- Persist every member separately with a shared series ID, run index/count,
  and experiment-seed provenance. Do not merge results or add implicit CSV
  output.
- Preserve the explicit profile-seed contract for ordinary single runs. Do not
  alter Exact or any Hybrid algorithm, jitter, learning, utility/SLA,
  telemetry, scheduling, or route semantics.


## Hybrid interrupted scale-down recovery decision

Accepted and implemented locally: 2026-08-15.

- Treat a lower, consistent three-Stage StatefulSet count as a resumable
  interrupted scale-down only when the deployed runtime and controller
  documents remain exact deterministic versioned documents for a larger
  replica count.
- Reconcile from the actual retained low-ordinal prefix toward the newly
  requested target through the existing bounded rollout and profile ordering.
- Keep the recovery automatic because it completes a launcher-owned
  scale-before-ConfigMap sequence without inventing hidden-state data or
  restarting retained Pods under `--skip-build`.
- Continue failing closed when Pods exceed documented profiles, stage counts
  differ, ownership/templates drift, documents are malformed, or any retained
  runtime/admission/link value differs from the generation rule.
- Do not delete or recreate the dedicated cluster for this recoverable state,
  and do not alter Hybrid semantics or frozen Exact behavior.


## Hybrid CSV export decisions

Accepted and implemented locally: 2026-08-15.

- Keep CSV output opt-in through production `--csv 1`; default `--csv 0`
  writes only the existing JSONL trace.
- Export host-side only after a complete validated trace exists, under the
  ignored `figures/` directory. Do not add a controller volume or Pod-side
  persistence.
- Preserve the existing wide formats: run-hash columns and timeslot rows for
  time/SLA/utility/Jain, and replica-identity columns with belief-snapshot rows
  for `replica_results.csv`.
- Explicitly exclude `log_results` and `results.csv` from repair, integration,
  tests, and command output.
- Define `aggregate_utility.csv` as the requested end-to-end utility view:
  export `raw_end_to_end_reference_utility`. Do not substitute
  `aggregate_expected_utility` or `physical_realized_utility`.
- Export the active physical-only SLA count, Jain fairness, and elapsed seconds
  without recomputation. Append initial plus every post-timeslot belief
  snapshot without adding a run-marker column that would change the legacy
  belief format.
- Repair the public helpers to align rows by headers, tolerate empty files and
  unequal column lengths, write atomically, and fail on malformed structures or
  invalid values. Keep the ordinary direct-call append behavior.
- Reject duplicate metric run hashes before writing a trace export. Preserve
  JSONL as the complete provenance source and make no Exact edit.


## Hybrid CSV directory decision

Accepted: 2026-08-15. Keep every generated Hybrid CSV in
`figures/IBG_hybrid/`. Create that directory recursively on demand. Do not
change filenames or table layouts, move existing historical files implicitly,
or affect Exact's separate CSV destination.


## Hybrid control-plane data-footprint decisions

Accepted and implemented locally: 2026-08-15.

- Reuse Exact `control_plane_v1` category names and observed HTTP application-
  body boundary, but use `ibg-hybrid-control-plane-data-v1` because the user
  explicitly excluded Exact's timing and CPU portions. Do not record timing,
  CPU, memory, cgroups, headers, wire bytes, NIC traffic, or forwarding-path
  payloads in this feature.
- Use production `--csv 1` as the sole activation switch and propagate its
  enabled/disabled state into the controller Job. Add no second CLI flag.
- Require one accepted aggregate Kubernetes discovery request/response and one
  route-command/selected-telemetry exchange per completed slot. Count actual
  serialized request bodies and raw response bodies.
- Keep observed belief TX/RX bytes and messages at zero while beliefs remain
  controller-local. Do not model or fabricate distributed belief exchange.
- Validate grand payload and message totals as the exact sum of the six primary
  categories. Expose belief TX-plus-RX as a derived CSV view without adding it
  to either grand total again.
- Attach the footprint to Kernel controller result/evidence, not
  `HybridSlotMetrics`, and exclude it from Pure/Kernel semantic parity.
- Persist a footprint block only when enabled and reject missing, unexpected,
  mixed, malformed, negative, or arithmetically inconsistent completed-slot
  records before trace/CSV acceptance.
- Put all 16 footprint CSVs under `figures/IBG_hybrid/footprint/` using the
  existing run-column/timeslot-row, blank-padding, duplicate-rejection, and
  atomic-write rules. Preserve the existing five Hybrid CSVs unchanged.
- Keep summary support Hybrid-specific and data-only. Validate completed traces
  before reporting per-run median/p95 payload/message categories and totals;
  do not extend or modify Exact's full timing/CPU summary tool.


## Hybrid per-timeslot optimization decisions

Accepted for ordered implementation: 2026-08-16.

- Implement exactly four optimization phases in this order: persistent HTTP
  clients; bounded parallel focal-candidate evaluation; controller-lifetime
  reuse of that bounded process pool; and, only last, conditional soft
  controller CPU priority.
- Treat Phase 1 as medium difficulty. Reuse only the controller discovery,
  controller-to-flow-generator, and flow-generator ingress client pools across
  slots. Preserve exchange counts, payloads, timeouts, failure behavior,
  footprint totals, and every inherited Exact forwarder client/keep-alive
  boundary. Require explicit lifecycle cleanup.
- Treat Phase 2 as high difficulty. Parallelize only independent hypothetical
  candidates for the same focal flow. Never parallelize real flow commits or
  dependent projected future-flow decisions. Restore results by original
  candidate index before unchanged scoring and tie-breaking, and keep a serial
  oracle until complete decision/result parity is proven.
- Treat Phase 3 as medium-high difficulty. Use one controller-owned pool of two
  processes across the finite experiment instead of constructing pools per
  decision or slot. Pass current immutable inputs with every task; do not allow
  workers to retain beliefs, loads, random state, or mutable policy state.
  Require cleanup after success, failure, and termination.
- Treat Phase 4 as medium overall difficulty and keep it conditional on evidence
  from the preceding phases. Prefer a larger shared CPU request, initially
  considering `1` CPU with the existing `2`-CPU limit, over exclusive pinning.
  Do not reserve exclusive cores, add a node, change workload placement, or
  claim additional physical CPU capacity.
- Do not add timing or CPU fields to the data-only control-plane-footprint
  schema as part of this work. Use existing result parity, focused connection/
  process lifecycle checks, and controlled wall-time/resource validation.
- Require focused tests, full Hybrid regressions, relevant frozen Exact
  regressions, offline manifest rendering, compilation, and `git diff --check`
  in every applicable phase. Require separate approval before any live Job,
  workload, image, or cluster validation.


## Hybrid persistent HTTP-client decisions

Accepted and implemented locally: 2026-08-16.

- Let the finite `HybridKernelControllerAdapter` own and close the persistent
  Kubernetes discovery and controller-to-flow-generator clients. The CLI must
  close the controller after normal completion and exceptions; use-after-close
  is invalid, and repeated close is harmless.
- Close already-created clients if environment-driven controller construction
  fails before ownership transfer.
- Let the flow-generator ASGI lifespan own the persistent asynchronous ingress
  pool. Do not create an AsyncClient at import time. Preserve an ephemeral
  one-call fallback only for direct executor callers outside an ASGI lifespan.
- Reuse client instances without changing request counts, payloads, timeouts,
  validation, exception mapping, footprint arithmetic, or response conversion.
- Do not touch the inherited Exact public-forwarder local/downstream clients,
  their limits/windows, or selected-pair measurement.
- Treat the completed unit/regression gate as lifecycle and parity evidence,
  not as proof of reduced live timeslot duration.


## Hybrid process-safe focal-branch decisions

Accepted and implemented locally: 2026-08-16.

- Represent one deterministic lookahead focal branch with a frozen, picklable
  task containing all current inputs explicitly, including its complete scored
  candidate and canonical index. Do not send controller or shared policy state
  to a worker.
- Reconstruct private dictionaries and a private policy/cache per task. Apply
  the focal candidate once, and keep projected future flows sequential within
  that branch through the unchanged greedy boundary.
- Return one indexed success or deterministic dead-end. Correlate unexpected
  exceptions with the same index and focal action; never retry, drop,
  approximate, or substitute a branch.
- Restore and validate canonical candidate order before constructing the
  unchanged lookahead decision. Retain strict improvement and the first
  canonical completed candidate on exact score ties.
- Keep public production `select_lookahead` serial. Limit executor use to the
  private import-safe Phase 2 validation path until Phase 3 separately owns
  and activates a controller-lifetime bounded pool.
- Do not alter existing Monte Carlo pool behavior or any algorithm, flow,
  learning, metric, telemetry, footprint, resource, topology, or runtime
  boundary. Treat the passing parity gate as process-safety evidence, not a
  performance result.


## Hybrid controller-lifetime lookahead-pool decisions

Accepted and implemented locally: 2026-08-16.

- Give each finite deterministic-lookahead Kernel controller exactly one
  controller-owned two-process executor. Reuse it across every focal decision
  and completed slot; do not create a pool per decision or per slot.
- Use the multiprocessing `spawn` context so worker processes inherit no live
  Kubernetes client, flow-generator client, controller belief mapping, or
  other parent runtime state. Continue passing every branch input explicitly.
- Keep public pure policy and slot calls serial by default. Permit executor
  injection only through the internal runner/policy integration boundary; add
  no user-facing lookahead worker option.
- Shut down the executor before controller-owned HTTP clients, wait for worker
  exit, cancel pending futures, make repeated controller closure harmless, and
  propagate task/shutdown failures without serial fallback.
- Record two persistent lookahead children between slots and zero after the
  finite controller closes. Preserve historical zero-worker evidence and
  require manual MC evidence to contain no lookahead-pool provenance.
- Keep the existing manual-MC per-slot rollout pool entirely separate. Do not
  change MC worker arguments, roots, samples, seeds, tail, lifecycle, or
  evidence meaning.
- Treat local equality and process-lifecycle tests as correctness evidence
  only. Require separate approval for image construction and a live timing/
  non-regression comparison before considering Phase 4 CPU priority.


## Hybrid lookahead-pool live-gate decisions

Accepted from the 2026-08-16 live gate:

- Accept the three-slot 15-flow, 3-stage, 8-replica run at profile seed 50 and
  root seed 2050 as live lifecycle and semantic-parity evidence for the fixed
  two-process controller-lifetime lookahead pool.
- Accept PID 22/25 stability across the three slots, exact two-worker lifecycle
  fields per completed slot, successful controller exit, and absence of an
  active controller container afterward as the live pool-reuse/cleanup gate.
- Keep the 48 post-controller `spawn_main` processes classified as the expected
  two Uvicorn workers for each of 24 public-forwarder containers, not as
  controller children.
- Retain the user-authorized eight-replica topology. The scale-down removed only
  ordinals 8--14; retained serving Pods preserved UID and restart identity.
- Do not infer a speedup from the recorded times. No matched serial live run was
  performed. Phase 4 soft CPU priority therefore remains conditional and is
  not authorized or justified by this gate alone.
- Make no multi-host, cross-worker, NIC, line-rate, or exclusive-CPU claim.


## Hybrid soft controller CPU-priority decisions

Accepted and implemented locally: 2026-08-21.

- Set the CPU request in every retained production Hybrid controller Job to
  one CPU while keeping the controller CPU limit at two CPUs and keeping its
  256-MiB request and 1-GiB memory limit unchanged.
- Treat the one-CPU request only as shared Kubernetes admission/accounting and
  CPU weighting. Do not describe it as an exclusive core, pinning, cpuset,
  additional capacity, an added worker, or uninterrupted access to a physical
  CPU. Unused CPU remains available to other worker workloads.
- Make the finite-controller resource preflight add 1000 millicpus, preserve
  the existing Pod-request arithmetic, and compare against the worker's actual
  Kubernetes allocatable values. Do not impose an artificial host CPU cap.
- Keep deterministic lookahead and manual MC on consistent controller resource
  templates. Do not change either process-pool lifecycle, pool size, algorithm,
  service resources, node selector, topology, or any experiment semantics.
- Require a separately approved matched live A/B before judging runtime effect:
  100m and one-CPU requests must use the same two-CPU limit, image/code,
  serving-Pod identities, topology, seeds, first slot, flow order, and slot
  count, without a serving rollout between runs. Report variance and sample
  limitations and use the word speedup only if that comparison is valid.


## Hybrid end-to-end SLA decisions

Accepted plan: 2026-08-21.

- Change the active Hybrid SLA violation count from selected physical-only
  latency to the already-recorded raw end-to-end latency, which is selected
  physical processing plus measured consecutive-pair latency.
- Keep the threshold at 80 ms and retain strict violation semantics: count a
  flow only when raw end-to-end latency is greater than 80 ms.
- Name the active trace/metric field `end_to_end_sla_violations`; do not retain
  a physically labelled field with end-to-end semantics.
- Export the active count to `end_to_end_sla_violations.csv`. Leave historical
  `sla_violations.csv` files untouched rather than mixing physical-only and
  end-to-end columns in one unversioned CSV.
- Keep the count separate from physical-only realized utility and from raw
  end-to-end reference utility. Do not feed pair latency into placement,
  learning, beliefs, or the selected processing signal.
- Defer the quality metric `end_to_end_sla_excess_ms`, defined as the per-slot
  sum of positive raw end-to-end excess above 80 ms, and its separate CSV until
  the user gives a later explicit implementation instruction.

Implementation completion: 2026-08-21.

- Version active persisted Hybrid traces as
  `ibg-hybrid-experiment-jsonl-v2` because the SLA field name and latency basis
  changed. Reject an inconsistent count, malformed raw end-to-end coverage, a
  threshold other than 80 ms, or the retired physical-only field before saving
  a v2 trace.
- Keep strict boundary behavior: exactly 80 ms is not a violation; any finite
  positive excess is a violation.
- Keep historical `sla_violations.csv` and pre-v2 traces intact and outside the
  active exporter rather than relabelling or backfilling them.
- Confirm that this completion does not authorize or implement SLA excess
  magnitude, a quality CSV, utility changes, or any algorithm/runtime change.


## Hybrid end-to-end SLA excess decisions

Accepted and implemented locally: 2026-08-21.

- Define `end_to_end_sla_excess_ms` as the per-completed-timeslot sum of each
  flow's positive raw end-to-end latency difference above the unchanged 80-ms
  threshold. Preserve full floating-point precision and do not round individual
  excesses before summation.
- Derive both the existing strict violation count and the new quality sum from
  the same already-computed `raw_end_to_end_latency_ms_per_flow` map. Exactly
  80 ms contributes zero to both; do not independently rebuild latency or add
  a redundant per-flow excess field.
- Include the quality value in `HybridSlotMetrics`, complete Pure/Kernel metric
  parity, completed Kernel JSON evidence, and explicitly labelled console
  output. Do not use it for planning, admission, utility, learning, or belief
  updates.
- Advance active persisted evidence to `ibg-hybrid-experiment-jsonl-v3` and
  reject missing, negative, non-finite, threshold-drifted, incomplete, legacy,
  or arithmetically inconsistent evidence before persistence.
- Under the existing `--csv 1` switch, write
  `end_to_end_sla_excess_ms.csv` beside the retained Hybrid CSVs with the same
  wide atomic table contract. CSV-disabled runs create no quality file. Never
  create or modify `results.csv` or historical `sla_violations.csv`, and do not
  relabel or backfill v1/v2 traces.
- Keep the 80-ms threshold and `end_to_end_sla_violations` unchanged. Preserve
  physical-only realized utility, raw end-to-end reference utility, pair and
  observation telemetry separation, all algorithm/runtime semantics, Phase 4
  soft CPU priority, and frozen Exact behavior.


## Hybrid tc/netem transport-impairment decisions

Accepted, implemented, and locally verified: 2026-08-22.

- Keep transport impairment opt-in and off by default through `--netem 0|1`,
  with finite nonnegative delay and jitter arguments. An enabled configuration
  requires positive delay and jitter no greater than delay; disabled runs must
  not carry delay/jitter values.
- Apply delay and optional normally distributed jitter only to replica-Pod
  `eth0` egress through a short-lived init container. Grant only `NET_ADMIN`,
  drop all other capabilities, and do not use privileged mode, host networking,
  host namespaces, device mounts, CPU pinning, affinity, or additional nodes.
- Reuse Exact's validated `tc` syntax and already-local runtime image as the
  offline base for a separate Hybrid-owned init image. Do not modify Exact or
  introduce an unpinned online dependency.
- Treat any enabled/disabled/value change as an intentional replica template
  rollout. Require all three StatefulSets to agree exactly and reject malformed
  or silently stale templates. Preserve the flow generator during this rollout.
- Store `ibg-hybrid-netem-v1` as complete top-level provenance on every host
  lifecycle event, including explicit disabled state. Keep trace contract v3
  and `HybridSlotMetrics` unchanged because this additive provenance is outside
  the semantic metrics boundary.
- Keep physical jitter, observation-only noise, planning, learning, beliefs,
  placement, and physical-only utility unchanged. Permit netem to affect the
  already-authoritative measured-pair component of raw end-to-end latency and
  consequently the end-to-end SLA count, excess, and reference utility; never
  suppress, normalize, or double-count that observed effect.
- Do not add packet loss, retries, imputation, missing-observation handling, or
  partial-slot acceptance. Live experimentation remains user-owned and is not
  part of local implementation verification.


## Hybrid equilibrium threshold update

Accepted and implemented: 2026-08-22.

- Set the active Hybrid per-belief-entry equilibrium tolerance to strict
  `<0.04`, superseding Hybrid's preceding `<0.033` setting.
- Keep equality non-equilibrium: a maximum entry change of exactly `0.04`
  does not satisfy the stopping rule.
- Treat this exclusively as a stopping-time change. Do not alter the belief
  calculation, policy, placement, learning, latency, utility/SLA, telemetry,
  seeds, scheduling, or frozen Exact implementation.


## Hybrid performance wall-time measurement decisions

Accepted and implemented: 2026-08-22.

- Extend the opt-in `--csv 1` controller footprint with monotonic discovery,
  admission, feedback, active-control, and selected-route-wait wall times.
- End admission immediately before the one flow-generator POST and begin
  feedback immediately after its response returns. Keep request preparation in
  admission and keep response conversion, learning, metrics, and equilibrium
  handling in feedback.
- Require active time to equal admission plus feedback exactly and keep
  `data_plane_wait` separate. Reject missing, negative, non-finite,
  out-of-order, malformed, or inconsistent completed timing evidence.
- Version the footprint as `ibg-hybrid-control-plane-wall-time-v2` while
  retaining experiment JSONL v3 because the complete slot-metrics semantic
  boundary is unchanged. Do not reinterpret historical data-only footprints.
- Export one existing-format CSV for each timing category under the footprint
  directory. Preserve all payload/message CSVs and create no CPU CSV.
- Do not add process CPU, cgroup, memory, NIC, or wire measurements. Use these
  wall times first to decide whether a later matched CPU/pool experiment is
  warranted; do not claim CPU saturation or speedup from them alone.


## Hybrid four-process CPU candidate decisions

Accepted and implemented locally: 2026-08-22.

- Increase only deterministic lookahead's persistent controller-owned pool
  from two to four spawn-isolated processes. Preserve explicit task inputs,
  private branch state, canonical result ordering, serial real flows, serial
  projected flows within a branch, failure propagation, and shutdown waiting.
- Set every retained controller Job to a two-CPU soft request and four-CPU
  limit. Keep controller memory unchanged and make resource preflight account
  for 2000 millicpus before mutation.
- Keep manual MC at its existing maximum of two workers and do not add a
  user-facing lookahead-worker flag.
- Treat the request and limit as shared Kubernetes scheduling/cgroup controls,
  not exclusive CPU ownership. Do not add affinity, pinning, cpusets, topology
  changes, or an artificial host CPU ceiling.
- Preserve all policy parameters, `D`, `C`, pruning, candidate accounting,
  branch recurrence, flow order, tie-breaking, seeds, jitter, beliefs,
  learning, utility/SLA, telemetry, footprint, routing, and serving resources.
- Compare the candidate against the accepted five-slot current-envelope trace
  before making a speed claim. Use identical dimensions, profile seed, policy,
  netem state, slot count, and serving environment, and report the small sample
  limitation.


## Hybrid production parity-replay decision

Accepted and implemented locally: 2026-08-22.

- Default ordinary production runs to `--parity-replay 0`, avoiding a second
  serial scheduling calculation after every completed Kernel timeslot.
- Retain `--parity-replay 1` as an explicit correctness diagnostic. Enabled
  replay uses the existing serial semantic oracle and must pass; there is no
  fallback, approximation, or tolerance change.
- Record disabled replay as “not performed,” never as a successful or failed
  comparison. Persist explicit lifecycle/slot provenance and reject drift.
- Keep the historical `run-small` validation gate replay-enabled and preserve
  dedicated Pure/Kernel parity tests.
- Keep the feature outside slot metrics and retain trace v3. Do not rewrite or
  reinterpret historical evidence.
- Preserve traffic count, telemetry, learning, beliefs, placement, flow order,
  lookahead, MC, random streams, utility/SLA, fairness, equilibrium, CSV,
  footprint, resources, topology, and frozen Exact behavior.


## Hybrid netem image source correction

Accepted and validated: 2026-08-22.

- Remove the runtime dependency on the historical Exact image tag because a
  Hybrid-only host may legitimately lack that unrelated image.
- Use the existing digest-pinned kind node image only as a multi-stage source
  for `tc`, its shared libraries, and `normal.dist`; publish a minimal
  Hybrid-owned scratch image rather than the complete node image.
- Keep all image construction offline and retain `imagePullPolicy: Never`.
- Preserve the existing non-privileged, `NET_ADMIN`-only init-container
  security boundary and replica-Pod `eth0` egress scope.
- Do not change impairment values, rollout semantics, metrics, controller
  behavior, serving containers, topology, or frozen Exact code.

## MILP large-profile ConfigMap persistence

Accepted: 2026-08-23.

- Persist only the generated `milp-experiment-profile` ConfigMap with
  server-side apply and the stable `milp-kernel-launcher` field manager.
- This removes the client-side last-applied annotation duplication that
  prevents large synthetic planning-link profiles from being accepted.
- Preserve the profile bytes, field names, mounted controller input, MILP
  formulation, planning coefficients, runtime profiles, rollout, and traffic
  behavior exactly.

## MILP large-solve controller memory

Accepted: 2026-08-23.

- Raise only the finite MILP controller Job to an 8-GiB memory request and a
  16-GiB hard limit after the user-run 40x3x20 solver Pod was OOM-killed at
  its former 256-MiB request/1-GiB limit.
- Retain the 100m CPU request and 2-CPU limit.
- Do not change service resources, cluster topology, formulation, cutoff,
  traffic, planning links, or the generated experiment profile.

## MILP intentional scale-down profile validation

Accepted: 2026-08-23.

- For an intentional replica scale-down, validate runtime-profile equality only
  for retained ordinal Pods, not replicas scheduled for deletion.
- Keep the prior all-existing-Pod validation for scale-up and exact-count runs.
- Do not silently refresh a retained replica's hidden state or runtime profile.

## MILP synthetic planning-link range

Accepted: 2026-08-23.

- Default new `synthetic-scale` profiles to version v2 with deterministic
  65.000--74.999-ms directed planning-link coefficients.
- Treat these values as explicit MILP objective inputs, not measured or
  injected network latency.
- Retain the v1 0.500--5.499-ms generator for historical reproducibility;
  do not relabel or rewrite prior v1 profiles, traces, or fingerprints.

## Greedy final-baseline planning decisions

Accepted for planning: 2026-08-24. Phase 0 is complete; policy/runtime
implementation has not started.

- Make `Greedy/` the owned package for a final pure-Greedy baseline, but treat
  its current files as legacy characterization inputs rather than trusted
  runtime code or an oracle.
- Define the target as pure budgeted `L=2` myopic selection. Every flow chooses
  one joint action containing one replica from each of exactly two distinct
  configured stages; the remaining `K-2` stages are bypassed.
- Score every feasible canonical action by the sum of its two immediate
  belief-driven expected stage utilities at projected loads `current + 1`.
  Commit both selected load increments before evaluating the next real flow.
- Keep strict deterministic tie-breaking by lexicographically lowest
  `(stage, replica)` action. Preserve the no-rejection experiment contract by
  selecting the greatest feasible action even when every score is non-positive;
  never emit the legacy replica-zero sentinel or a partial action.
- Use the legacy budgeted path only as reference for its two-stage shape. Exclude
  its stochastic grids and stale formulas, plus all future-flow reasoning,
  pruning, lookahead, Monte Carlo, bandits, MILP, and planning-link cost from
  Greedy selection. Measured pair cost remains post-placement telemetry only.
- Require explicit positive `--flow`, `--stage`, and `--replica` dimensions on
  every run, with `--stage >=2`; there are no topology defaults. Use 10 flows,
  3 configured stages, and 5 replicas per stage only when explicitly supplying
  the canonical matched-comparison shape. Stage IDs must be the complete
  configured sequence `1..K`, while each action selects two of them in
  increasing order. Give every generated replica
  `ceil(flows / replicas)` admission capacity.
- Reuse current Hybrid-compatible learning/runtime/reporting semantics without
  importing Hybrid policy behavior: separated physical and observation jitter,
  exact convolved likelihood, selected-only belief updates, physical-only
  realized utility, raw consecutive-pair reference metrics, strict raw
  end-to-end SLA above 80 ms with excess, Jain fairness, and strict `<0.04`
  equilibrium stopping.
- Require compatibility tests around every reused or adapted policy-neutral
  component. Do not duplicate formulas merely to rename them, and do not move
  Greedy policy logic into Kubernetes, HTTP, or persistence code.
- Give Greedy exclusive infrastructure identities: kind cluster `greedy`,
  context `kind-greedy`, namespace `greedy-testbed`, worker label
  `greedy.workload-node=true`, Greedy-prefixed resources, and Greedy-owned
  service/controller images. Exact, Hybrid, and MILP clusters/namespaces are
  outside its mutation boundary.
- Use exactly one control-plane and one worker node, with replicas, flow
  generator, and finite controller Jobs scheduled worker-only. Retain the
  current accepted private-processor/public-forwarder split, resources,
  probes, and connection-lifetime settings during baseline construction.
- Require positive `--rollout-batch-size`, defaulting to one, for bounded
  replica scale-up; support intentional higher-ordinal replica removal and
  highest-contiguous-stage addition/removal with retained-Pod preservation and
  fail-closed profile validation.
- Require `--profile-seed` for a production run and limit it to the fixed hidden
  runtime-state map. Record the generated map/provenance; do not imply that the
  same numeric seed is cross-baseline parity until identical maps are proven.
- Require positive `--max-iterations`, stop earlier only on the accepted
  equilibrium rule, and keep one fresh finite controller Job per experiment.
  One launcher invocation is exactly one experiment run. Do not implement a
  `--runs` option or an internal repetition loop.
- Make JSONL host persistence mandatory for a successful production run and
  `--csv {0,1}` an opt-in host-side export. Use
  `GREEDY_SLOT_EVIDENCE=`, `runs/greedy-experiment-*.jsonl`, and
  `figures/Greedy/`; do not write experiment results inside controller Pods.
- Match Hybrid's human console structure and launcher progress grammar while
  using Greedy labels and policy provenance. Machine evidence remains the
  complete source of truth and never exposes processor hidden state to policy.
- Define `--skip-build` narrowly: it requires an existing validated Greedy
  cluster and matching node-local images, skips builds/loads/forced serving
  restart, but still performs safe reconciliation, Ready checks, and a fresh
  controller Job. It is invalid for first bootstrap.
- Keep this roadmap planning-only. No image build, cluster creation/deletion,
  namespace mutation, Pod rollout, controller Job, or live gate is authorized
  until the corresponding later phase receives explicit user approval.
- Exclude automatic repeated runs from the Greedy launcher contract; callers
  may invoke the one-run command again externally when they intentionally want
  another experiment. Also defer Greedy netem, retries, packet loss, DPDK/VPP,
  multi-host work, solver-resource instrumentation, and new Chart/report work.
  They are not implied by completing the baseline.

### Greedy execution-efficiency planning decisions

Accepted for planning: 2026-08-24. These refine the phase plan without
authorizing implementation or a live operation.

- Begin every Greedy implementation phase with a targeted preparation step
  whenever relevant material exists: reread the current handoff contract and
  inspect only the phase-related documentation, code, scripts, and focused
  tests listed in that phase. Record reuse/adaptation/exclusion findings before
  editing. Do not turn this into an unrestricted scan of result files or the
  user-controlled documentation and Chart areas.
- Precompute immutable Greedy replica identities grouped by stage and canonical
  `L=2` action ordering, then memoize deterministic expected stage utility by
  exact belief tuple and projected load within a finite controller. Require
  cached/uncached equality and bounded-lifetime tests. Do not copy Hybrid
  pruning/activation/lookahead/MC structures or the legacy Greedy
  Pandas/Monte-Carlo expectation path.
- Reuse persistent client lifecycles across all slots: one controller-owned
  Kubernetes client, one controller-owned flow-generator client, one flow-
  generator-lifespan route-dispatch pool, and the accepted separate local and
  downstream clients in each public forwarder. Close owned clients exactly
  once on success, construction failure, or runtime failure.
- Execute already-selected logical flows concurrently in the flow generator,
  with each flow's hops ordered. Keep flow placement, load mutation, belief
  update, and slot commit sequential. They are semantic dependencies, not
  parallel-work candidates.
- Add `--parity-replay {0,1}` with production default zero. Correctness gates
  and the small live gate require replay; ordinary production runs avoid the
  duplicate pure calculation unless explicitly enabled. JSONL must distinguish
  requested, performed, and result fields without inventing disabled parity.
- Include monotonic discovery, admission/placement, data-plane wait,
  feedback/validation, and total wall times in Greedy evidence. `--csv 1` also
  exports these phase timings and controller payload/message footprint. Timing
  identifies phase dominance; it is not CPU-saturation or speedup proof.
- Preserve Hybrid's deployment-efficiency measures: lean separate service and
  controller images, validated offline inputs, change-scoped build/load when
  provable, no-op equal reconciliation, append/remove-only topology changes,
  bounded Ready-gated batches, retained-Pod preservation, and narrow
  `--skip-build` behavior.
- Do not add Hybrid's focal-candidate worker boundary or persistent lookahead
  process pool to Greedy. There is no Greedy candidate tree, and parallel real-
  flow decisions would change load-dependent choices. Do give the Greedy
  controller the active Hybrid comparison cgroup envelope: request `2` CPU and
  `256Mi`, limit `4` CPU and `1Gi`. Cover it in worker-resource preflight and
  prohibit one-sided tuning; any alternative must be a versioned matched A/B.

### Greedy/Hybrid matched-comparison decisions

Accepted for planning: 2026-08-24.

- Define `greedy-hybrid-matched-comparison-v1` as same experimental inputs,
  infrastructure opportunity, runtime conditions, and measurement boundaries,
  with policy logic as the intentional difference.
- Before every implementation phase, read the current phase-relevant
  `IBG_Hybrid/` source, `deploy/hybrid-kubernetes/` manifests,
  `scripts/run_hybrid_kernel_phase4.py`, and smallest focused Hybrid tests when
  applicable. Extract and record exact values before editing Greedy. If current
  code differs from the recorded matrix, stop and version/review the matrix;
  do not silently follow stale documentation.
- Match 10 flows, 3 stages, 5 replicas per stage, `L=2`, one Job/run, the same
  maximum-iteration value, `ceil(N/M)` capacity, and Ready semantics for the
  intended comparison. Invoke Hybrid once with its repetition mode omitted;
  Greedy itself exposes no `--runs` option.
- Match the exact identity-aligned hidden-state and observation-seed map and
  its fingerprint. A matching numeric `--profile-seed` alone is insufficient.
- Match the root seed, flow-order derivation, and a deterministic keyed
  physical/observation input schedule. Key common draws by experiment, slot,
  flow, stage, replica, load, and component. Never expose those values to
  policy selection, and record route-dependent inapplicability honestly.
- Match active serving resources and lifecycles: private processor
  `50m/128Mi` request and `1 CPU/768Mi` limit; public forwarder `25m/128Mi`
  request and `1 CPU/256Mi` limit; flow generator `50m/128Mi` request and
  `1 CPU/768Mi` limit; one private worker, two public workers, ports 8081/8080,
  and the accepted 30-second downstream/server keep-alive.
- Match controller resources at `2 CPU/256Mi` requested and `4 CPU/1Gi`
  limited, node placement, HTTP/discovery settings, rollout batch, Ready gates,
  build/reuse state, instrumentation flags, and warm/cold conditions. Compare
  actual CPU, RSS, throttling, and wall time under that common envelope.
- Require a versioned field-by-field comparison matrix and fingerprints in
  local fixtures and final evidence. Any required mismatch fails the comparison
  rather than being buried in prose.
- Keep only algorithm-defining differences: Greedy remains sequential and has
  no pruning, activation, planning-link selection term, lookahead, Monte Carlo,
  candidate/depth arguments, `--policy`, `--mc-workers`, or process pool.

### Greedy phase intelligence-level recommendations

Accepted for planning: 2026-08-24.

- Treat the recorded level only as a recommendation to the user when choosing
  Codex reasoning effort. It is not an agent prerequisite, automated check,
  runtime dependency, or permission to perform live work.
- Do not pin a model ID in the repository. The agent does not inspect, verify,
  enforce, or change the user's selected model or reasoning level.
- Assign `high` to Phase 0 contract characterization, Phase 4 images/manifests,
  Phase 6 evidence/reporting, and the separately authorized Phase 8 small live
  gate. These are bounded by explicit contracts and focused acceptance checks.
- Assign `xhigh` to Phase 1 policy mathematics, Phase 2 stateful learning and
  metrics, Phase 3 concurrent Kernel lifecycles, Phase 5 fail-closed dynamic
  topology, Phase 7 full regression analysis, and Phase 9 scale/final evidence.
  These phases have greater semantic, state, lifecycle, or interpretation risk.
- The user may select a higher or lower level without explanation or a handoff
  update. The recorded value remains a convenience recommendation only.
- Intelligence recommendations do not alter phase preparation, tests, explicit
  live authorization, destructive-action review, or handoff discipline.

### Greedy Phase 0 contract decisions

Accepted and implemented locally: 2026-08-24.

- Freeze `Greedy/phase0_contract.py` as an executable fixture/oracle only. It
  resolves selection, capacity, load-mutation, route, observation, pair-count,
  public-input, and excluded-feature ambiguity without implementing the Phase 1
  policy or Phase 2 runner.
- Require explicit positive flow, stage, and per-stage replica dimensions in
  every future launcher invocation; there are no topology defaults. Freeze
  10 flows, 3 stages, and 5 replicas only as the explicitly supplied canonical
  matched-comparison shape. Freeze exactly one run per launcher invocation and
  no `--runs` option. Keep the legacy 29-execution loop only as retired
  characterization evidence.
- Keep `Greedy/legacy_characterization.py` completely import-free with respect
  to historical modules. Static AST inspection is the default safety boundary;
  bounded tests may load only individually verified definition-only files and
  must never import `Greedy/main.py` or execute the historical experiment.
- Classify all 38 top-level legacy callables and `Replica` methods explicitly:
  five reuse only equivalent active shared behavior with compatibility tests,
  fourteen are reference-only, and nineteen retire. No legacy source file is
  edited or treated as an oracle.
- Treat the legacy active budgeted selector as reference for the authorized
  two-stage shape and immediate-sum concept, even though its name says memoized
  and its file contains a separate link helper. Its stochastic per-stage grids,
  global randomness, and historical semantics remain excluded.
- Treat the dormant per-stage path's `0` result as a defect, not rejection
  semantics. Its embedding increments `current_state[-1]`; the new contract
  instead selects the best feasible non-positive score or fails explicitly
  only when feasibility is empty.
- Retain historical inverse-latency utility, global Python/NumPy/UUID random
  handling, truncated-normal likelihood, state-based SLA, 15-ms latency excess,
  `<0.06` equilibrium, direct CSV writes, and trend filling solely as recorded
  divergence evidence.
- Directly reuse only policy-neutral active behavior that already lives outside
  Hybrid policy: physical/observation latency laws and exact likelihood,
  selected-only learning, physical-only outcome selection, SLA count helper,
  and Jain fairness. Require compatibility tests for every use.
- Put belief-driven expected utility, Greedy-owned budgeted `L=2` schemas,
  raw-two-hop 80-ms SLA assembly/excess, explicit 0.04 equilibrium threshold,
  and flow-order isolation behind Greedy-owned adapters in later phases. These
  are adaptations because their current assembly or type location is
  Hybrid-specific.
- Adapt Hybrid's canonical two-stage action and bypass shape without importing
  its policy types. Exclude Hybrid pruning, activation, link-aware objectives,
  lookahead, Monte Carlo, process workers, and policy modules. Runtime/service
  lifecycle patterns remain later-phase adaptations and are not implemented by
  Phase 0.
- Controller policy input may contain only public identity, readiness,
  admission, belief, and current-load data. Hidden state and `--profile-seed`
  are runtime provenance and never policy inputs; measured pair data is
  post-selection telemetry only.
- Phase 0 authorizes no controller, policy implementation, container, manifest,
  launcher, cluster action, traffic, JSONL, or CSV output. Greedy Phase 1 is the
  next action and requires a new user request.

### Greedy Phase 1 policy decisions

Accepted and implemented locally: 2026-08-24.

- Make `GreedyConfiguration(N, K, M)` require all three positive dimensions;
  retain fixed `L=2` and `K>=2`, with no topology defaults or implicit 10x3x5
  construction. Keep 10x3x5 only in the explicitly named canonical
  matched-comparison fixture.
- Own immutable Greedy identity, public replica state, global load, admission,
  action, decision, and complete result types. Require public replica metadata
  to declare exactly `ceil(N/M)` capacity and cover every canonical identity.
- Precompute identities grouped by stage and all complete distinct-stage L=2
  actions once per policy instance. Sort the complete action tuple globally and
  retain its first member on exact score ties.
- Evaluate one stage once per real decision at `current_load+1`, then form every
  feasible action score with the exact sum of its two deterministic expected
  stage utilities. Commit both selected loads before evaluating the next real
  flow; no independent real-flow parallelism is allowed.
- Use a Greedy-owned expected-utility adapter that delegates state/load utility
  to `IBG.latency_model`. Do not import `IBG_Hybrid.expected_utility` or copy
  its implementation into the policy namespace.
- Bound controller-lifetime expected-utility memoization with a 4096-entry LRU
  keyed exactly by immutable `(belief tuple, projected load)`. Keep explicit
  clearing available and require cached/uncached result equality; eviction is
  an execution detail and cannot change a decision.
- Keep the complete policy input structurally limited to flow order, public
  identity/readiness/capacity/belief, and current loads. Hidden state, profile
  seed, physical/observation seeds, measured pair latency, and planning-link
  coefficients have no fields or call parameters at this boundary.
- Raise an explicit typed error only when no complete feasible action exists.
  Never add a rejection sentinel or partial action, and keep the greatest
  feasible action when all expected scores are non-positive.
- Freeze `greedy-hybrid-matched-comparison-v1` as typed required-match rows plus
  separately validated intentional policy differences. Phase 1 records current
  Hybrid resources and comparison requirements but does not create manifests,
  seed schedules, launcher behavior, or runtime evidence.
- Reuse only Hybrid's phase-neutral ideas of immutable identity/action
  construction, public readiness/capacity validation, exact-key utility
  memoization, and deterministic strict ties. Exclude its per-stage pruning,
  activation, directed planning-link term, future-flow lookahead, Monte Carlo,
  candidate/depth CLI, optional runs series, and policy process pools.
- Phase 1 changes no `IBG/`, `IBG_Hybrid/`, MILP, Kubernetes, generated result,
  or unrelated algorithm source. Phase 2 is the next action and requires a new
  user request.

### Greedy Phase 2 pure-loop decisions

Accepted and implemented locally: 2026-08-25.

- Keep one immutable `GreedySlotInput` split into public replica state and a
  simulation-only replica profile. Pass only public identity, Ready state,
  `ceil(N/M)` capacity, and belief to Phase 1 policy selection. Never pass
  hidden state, profile/component seeds, or pair telemetry.
- Fingerprint the complete sorted hidden-state/observation-seed profile map.
  Treat the materialized map plus fingerprint as environment identity;
  `profile_seed` is provenance only in Phase 2 and seeds neither flow order nor
  physical/observation sampling.
- Preserve an explicitly supplied flow order. Otherwise reproduce active
  Hybrid `blake2b-hybrid-flow-order-v1` exactly with a local RNG. Use
  component-separated deterministic local NumPy streams keyed by root,
  experiment, slot, flow, stage, replica, final assigned load, and component.
  Preserve active Hybrid component-seed bytes for the canonical one-experiment
  ID and namespace noncanonical pure fixture IDs explicitly.
- Execute Phase 1 policy once per ordinary slot and retain its returned
  decisions and load chain without recomputation. Perform physical/observation
  generation only after all placements complete, and reject incomplete,
  duplicate, unselected, wrong-load, or wrong-route simulation results before
  learning.
- Reuse `IBG.learning.apply_observations` for selected-only dispatch. Adapt the
  frozen Exact local posterior and `0.8` aggregate-retention behavior behind a
  minimal import-safe Greedy learning target, with direct compatibility tests.
  Idle and bypassed replicas receive no update.
- Compute predicted utility from beliefs before learning at each selected
  replica's final slot load. Exclude planning-link values. Compute physical
  realized utility from physical latency only; keep observation jitter out of
  utility/SLA; add measured pair latency only to raw end-to-end latency and raw
  reference utility.
- Keep strict raw end-to-end SLA violation above `80.0` ms, unrounded excess,
  active Jain fairness behavior, maximum per-entry belief change, and strict
  equilibrium `<0.04`.
- Expose injected monotonic placement and feedback/validation clock seams.
  Runtime values are measurements only and never policy inputs.
- Run exactly one experiment per `run_greedy_experiment` call. Retain beliefs
  and one policy/cache across slots, stop immediately on equilibrium, otherwise
  complete exactly the explicit positive `max_iterations`. Add no `--runs`,
  output, persistence, controller, or runtime boundary.
- Keep captured replay validation explicit. Its transparent serial reference
  enumerates all canonical immediate actions; its replay consumes already
  captured observations/pairs once with caching disabled. Ordinary execution
  neither imports nor calls the replay path and therefore does not double-solve
  by default.
- Reuse only policy-neutral latency/likelihood, learning dispatch, SLA count,
  and expected-utility behavior. Adapt Hybrid-shaped slot/metric/timing/replay
  contracts behind Greedy ownership. Exclude Hybrid activation, pruning,
  planning-link selection, lookahead, Monte Carlo, continuation oracle,
  candidate/depth/worker parameters, and process pools.
- Phase 2 changes no frozen `IBG/`, `IBG_Hybrid/`, MILP, Kubernetes, generated
  evidence, or unrelated variant. Greedy Phase 3 is the next action and
  requires a separate request.

### Greedy Phase 3 Kernel/controller decisions

Accepted and implemented locally: 2026-08-25.

- Own all Greedy discovery, route, HTTP, controller, lifecycle, timing, and
  replay contracts under `Greedy/`. Reuse the shared private processor and
  public forwarder only through Greedy wrappers; do not import Hybrid route or
  controller policy types.
- Require discovery to return the exact canonical configured identity set with
  public Running/Ready state, `ceil(N/M)` assigned-flow capacity, ownership,
  and endpoint metadata. Reject missing, duplicate, unexpected, foreign,
  malformed, or non-Ready Pods. Hidden state and runtime seeds remain absent.
- Complete the unchanged sequential Greedy placement once before traffic.
  Send one complete slot envelope to the flow generator, then exactly one
  first-forwarder request per logical flow. Run the `N` routes concurrently
  while each route's two selected hops remain ordered. Never request a bypassed
  or idle replica.
- Generalize the Hybrid two-hop route idea to arbitrary configured `K>=2`.
  Retain two increasing selected identities and a complete `K-2` bypass tuple;
  add explicit route-position and next-hop correlation. Do not reuse Hybrid's
  hard-coded three-stage bounds or scalar skipped-stage schema.
- Fail the whole slot on any request failure or missing, duplicate, partial, or
  mismatched flow/slot/stage/replica/load/position/next-hop/pair telemetry.
  Add no retry, imputation, partial learning, rejection sentinel, or route
  replacement. Commit learned beliefs only after the entire slot result
  validates.
- Keep exactly one synchronous discovery client and one synchronous
  controller-to-flow-generator client for the finite controller lifetime. Keep
  one asynchronous flow-generator-to-first-forwarder pool for the ASGI
  lifespan, with one-call ephemeral fallback only for direct executor tests.
  Preserve separate public-forwarder local-processor and downstream clients.
  Make all owners idempotently close their clients exactly once after normal
  finite completion, construction/startup failure, request/slot failure, or
  shutdown.
- Match active Hybrid timeout/runtime assumptions: 10-second discovery,
  30-second controller-to-flow-generator, 10-second selected-route/forwarder
  requests, processor port 8081, public forwarder port 8080, one private
  worker, two public workers, and 30-second downstream/server keep-alive. Keep
  the local processor client on its processor-compatible default idle behavior.
- Reuse Phase 2 selected-only learning and metric assembly unchanged. Physical
  latency alone defines realized utility; observation jitter stays
  learning-only; measured pair latency stays raw-reference/SLA-only; strict
  raw `>80.0` ms SLA, unrounded excess, Jain fairness, and strict `<0.04`
  equilibrium remain frozen.
- Add injected monotonic discovery, admission/placement, route-dispatch,
  data-plane-wait, feedback/validation, and total-slot boundaries. Timing is
  observational only.
- Keep captured Pure/Kernel replay explicit and HTTP/draw-free. Compare public
  input, placements, loads, captured observations/pairs, beliefs, metrics,
  SLA, fairness, and equilibrium while excluding runtime provenance and wall
  time. Ordinary controller execution never imports replay and solves once.
- Revalidate and extend `greedy-hybrid-matched-comparison-v1` with Phase 3
  timeout, client-ownership, request-count, payload-semantic, and telemetry
  count rows. The audit used HEAD
  `19229c274038db440f3cfdd62ed2102ea4c2c545`; exact locations and blobs are in
  `ARCHITECTURE.md` and `Greedy/comparison.py`, with no relevant drift.
- Exclude Hybrid pruning, activation, planning-link selection, lookahead,
  Monte Carlo, policy/depth/worker parameters, process pools, console/evidence
  output, and repetition. Phase 3 creates no image, manifest, namespace,
  launcher, JSONL, CSV, or cluster operation. Greedy Phase 4 is next and needs
  separate authorization.

### Greedy Phase 4 static infrastructure decisions

Accepted and implemented locally: 2026-08-25.

- Own the static deployment boundary under `Greedy/`,
  `deploy/greedy-kubernetes/`, and two import-safe helper scripts. Do not edit
  or alias active Hybrid manifests, images, namespaces, service accounts, or
  ConfigMaps.
- Require a complete explicitly supplied `N/K/M` deployment input and exact
  canonical processor-private profile map. Keep 10x3x5 only as the named
  matched-comparison example. Generate `ceil(N/M)` as the public Pod admission
  label and reject missing or noncontiguous identities.
- Use deterministic JSON documents as the dependency-free offline render
  format. JSON is valid Kubernetes YAML; render functions immediately support
  lossless local parse/validation without adding PyYAML to either runtime
  image. Treat any resource differing from the canonical render as drift.
- Keep the long-running base separate from the finite controller Job. Require
  an explicit exact Ready identity token plus Ready flow generator before a
  Job can be rendered. Phase 5 will own live readiness acquisition and apply
  ordering; Phase 4 performs neither.
- Use `greedy-testbed`, Greedy-prefixed names/labels/images, one control-plane
  and one `greedy.workload-node=true` worker, and worker-only scheduling for
  all workloads. Permit controller discovery only through a namespace Role
  granting Pod `get/list`.
- Disable service-account token mounting for replica and flow-generator Pods.
  Enable it only for the controller Job. Run all Pods as UID/GID 10001 with
  runtime-default seccomp; drop all capabilities, forbid privilege escalation,
  and use read-only container roots.
- Preserve the accepted two-container replica: one private processor on 8081
  and two-worker public forwarder on 8080 with 30-second server/downstream
  keep-alive. Preserve the active Hybrid-matched probes and all four resource
  envelopes exactly. Include the simultaneous serving and controller requests
  in worker allocatable preflight.
- Give the processor a Greedy-owned runtime-profile document and environment
  variable. Runtime profiles contain hidden state and observation seed and are
  mounted only into processors. Controller ConfigMaps contain dimensions,
  seeds, profile fingerprint, and finite-run inputs but no hidden state,
  observation seed, or beliefs.
- Maintain separate offline Python 3.12/Linux AMD64 wheel locks/manifests and
  Greedy cache paths for service and controller images. The service source
  inventory excludes policy/controller/oracle and legacy files; the controller
  inventory excludes service entry points and all Hybrid/MILP sources.
- Reuse only policy-neutral processor/forwarder runtime behavior and exact
  resource/port/worker/keep-alive values. Adapt image ownership, profile
  parsing, resources, security, and rendering behind Greedy boundaries.
  Exclude Hybrid policy, pruning, activation, planning links, lookahead,
  Monte Carlo, four-process pools, launcher, reconciliation, and output code.
- Phase 4 invokes no Docker, kind, kubectl, network, cluster, traffic, JSONL,
  or CSV operation. Greedy Phase 5 is the next separately scoped action.

### Greedy Phase 5 lifecycle and reconciliation decisions

Accepted and implemented locally: 2026-08-25.

- Own the persistent lifecycle in `Greedy/kernel_lifecycle.py` and the thin
  `scripts/run_greedy_kernel.py` entry point. Require explicit dimensions,
  maximum iterations, and profile seed. Keep rollout batch default 1, one Job
  per invocation, no topology defaults, and no `--runs` or Hybrid solver knobs.
- Keep `--csv` and `--parity-replay` as validated behavior-neutral launch
  fields through Phase 5. Phase 6 alone may define evidence, replay reporting,
  JSONL, or CSV effects.
- Resolve the positive experiment-root seed independently of profile seed.
  Use profile seed only to materialize the versioned hidden-state and
  observation-seed environment. Environment equality is the validated map and
  fingerprint, never equal seed spelling alone.
- Adapt the active Hybrid 3/3/2/2 keyed hidden-state allocation and canonical
  observation-seed prefix behind a Greedy-owned module. Generalize it
  append-only for arbitrary stages/replicas and reject any retained-identity
  drift. Never reveal the private map to controller input or launcher output.
- Represent lifecycle progress with an owned versioned stable/target transition
  marker. Continue only an unambiguous prefix-shaped interrupted transition.
  Refuse unmarked partial state, ordinal holes, inconsistent stage widths,
  malformed ownership, or unrelated namespaces/workloads rather than guessing.
- Reconcile only high suffixes: add/remove highest replica ordinals across all
  retained stages and add/remove highest contiguous stages. Require exact
  Running/Ready coverage after every bounded mutation and before controller
  traffic. Never contract below two stages.
- Treat equal topology/profile as a serving no-op. For flow-only changes, patch
  only public capacity labels and controller configuration so retained Pods are
  not replaced. When no service-image restart is authorized, require retained
  Pod UIDs and restart counts to remain unchanged.
- Run worker allocatable-versus-request preflight before topology mutation or
  Job creation, counting every requested replica Pod, the flow generator, and
  one `2 CPU/256Mi` controller. Keep all Phase 4 requests, limits, probes,
  ports, workers, security contexts, and keep-alive values frozen.
- Validate complete source provenance and exact local/node image identities.
  Bootstrap builds both roles offline only after both wheelhouses validate.
  Later maintenance rebuilds only a proven changed role. `--skip-build` cannot
  bootstrap, skips wheel/build/load, validates retained identities, and does
  not force a serving restart.
- Reuse only cluster-independent validation and offline wheel checks. Adapt
  Hybrid ordering, rollout, profile, and kind lifecycle under the Greedy
  cluster/context/namespace/label boundary. Exclude Hybrid policy, pruning,
  lookahead, Monte Carlo, process pools, repetitions, netem, and evidence paths.
- Make preflight read-only. Make cleanup explicit and Greedy-only: validate
  exact ownership first, then delete only kind cluster `greedy`; refuse an
  ambiguous or foreign inventory.
- Phase 5 testing uses injected fake executors only. No Docker, kind, kubectl,
  network, cluster, traffic, experimental result, JSONL, or CSV action is
  authorized by this decision. Phase 6 was separately scoped and is recorded
  below.

### Greedy Phase 6 evidence and reporting decisions

Accepted and implemented locally: 2026-08-26.

- Keep human presentation and machine evidence separate. The controller prints
  Greedy-labeled Hybrid-compatible belief and completed-slot blocks, then emits
  exactly one validated `GREEDY_SLOT_EVIDENCE=` line after each committed slot.
  Hidden processor state and stochastic seeds are never printed or persisted.
- Make a host JSONL lifecycle mandatory after every successful launcher run.
  Use one `run_started`, contiguous `iteration_completed` records, and one
  `run_completed` under `runs/greedy-experiment-<UTC>.jsonl`. Validate the
  entire lifecycle and atomic temporary-file round trip before replacing the
  destination. Keep controller Pods free of result volumes.
- Preserve production replay default zero. Disabled replay records requested
  and performed false and omits a result. Enabled replay recomputes policy,
  selected-only learning, and metrics from captured public inputs and captured
  telemetry only, performs no HTTP or redraw, and fails closed on mismatch.
- Validate complete placement/load chains, selected observation and pair
  coverage, separated physical/observation values, exact likelihood vectors,
  all predicted/physical/raw utility aggregates, strict raw latency above
  80 ms, unrounded excess, Jain fairness, belief change, and strict `<0.04`
  equilibrium before persistence.
- Record all matched-comparison rows, seed/schedule versions, dimensions,
  runtime-profile fingerprint, lifecycle warm/build state, full role-owned
  source fingerprints and image IDs, worker allocatable, and actual Pod
  requests/limits. Record per-slot controller CPU, current RSS, and cgroup CPU
  throttling. Enable application-body/message footprint only when CSV is
  requested; belief exchange remains zero because beliefs stay controller-local.
- Make `--csv 0` JSONL-only. `--csv 1` exports the validated trace host-side to
  `figures/Greedy/` using the accepted six quality/belief files plus phase,
  payload, message, CPU, RSS, and throttling footprint files. Preserve raw
  end-to-end reference utility in `aggregate_utility.csv`, identity-align
  belief rows, blank-pad unequal metric runs, reject malformed retained files,
  and refuse duplicate run hashes before the first replacement.
- Treat output as behavior-neutral. Instrumentation cannot enter selection,
  telemetry correlation, learning, utility, SLA, fairness, equilibrium, or
  stop decisions. The real-flow solve remains once per slot unless replay is
  explicitly enabled.
- Refuse `--skip-build` whenever current controller/service source fingerprints
  differ from retained image provenance. A no-build invocation may never claim
  that an older node-local image represents newly changed source.
- Reuse only policy-neutral presentation/layout concepts. Adapt Hybrid output,
  lifecycle, replay, CSV, and footprint schemas under Greedy ownership, and
  exclude Hybrid policy controls, pruning, lookahead, Monte Carlo, process
  pools, repetition, netem, and unrelated diagnostic boundaries.
- Phase 6 is local-only. Tests write only temporary JSONL/CSV fixtures; no
  Docker, kind, kubectl, network, live cluster, traffic, or production result
  operation is authorized or performed. Greedy Phase 7 local integration is
  next.

### Greedy Phase 7 local-integration decisions

Accepted and completed locally: 2026-08-27.

- Treat Phase 7 as a verification layer, not a feature phase. Add no new
  policy, runtime, manifest, lifecycle, diagnostic, persistence, or reporting
  behavior.
- Bind the comparison envelope to repository HEAD
  `8e5114e6e9101057da48255962afa65900c6c8d0`. Hash every active source or
  manifest represented by the Phase 3--7 audits and fail when any recorded
  blob drifts. Preserve the 52 equal required rows and exactly 11 declared
  policy-only differences.
- Classify reusable behavior only at policy-neutral boundaries; keep
  Greedy-owned identity, arbitrary-stage route, lifecycle, and evidence
  adaptations; continue excluding Hybrid pruning, activation, planning-link
  selection, lookahead, Monte Carlo, process pools, policy CLI, and repeated
  runs.
- Exercise multiple small explicit shapes, including `K=2`, `K>2`, one and
  multiple replicas, and nontrivial `ceil(N/M)` capacity. Render and parse the
  long-running resources, finite controller Job, and kind shape entirely in
  memory.
- Make controller CPU/RSS/cgroup-throttling instrumentation explicitly
  semantics-neutral by comparing complete finite pure experiment results with
  and without injected samples. Instrumentation may change only its optional
  evidence field.
- Extend retained-CSV refusal to duplicate headers and over-wide rows. Keep all
  persistence fixtures under pytest temporary directories and create no
  repository experiment output.
- Aggregate-import every new Greedy-owned Phase 0--6 module in a clean
  directory while preserving global Python and NumPy RNG state. Never import
  unsafe legacy `Greedy/main.py` or the historical CSV/report modules.
- Preserve pre-existing unrelated worktree changes. Phase 7 may modify only
  the Greedy comparison audit, its focused integration test, and the four
  handoff documents.
- Keep Phase 7 offline-only. Do not invoke Docker, kind, kubectl, Kubernetes,
  a registry, network traffic, live controller execution, or performance
  measurement. Phase 8 remains a separately authorized live gate.

## Greedy Phase 8 decisions

Accepted on 2026-08-27 after explicit live authorization.

- Accept `3 flows x 3 stages x 2 replicas`, fixed `L=2`, profile seed 17,
  rollout batch 1, `--parity-replay 1`, and `--csv 1` as the small live gate.
  This is an explicit test shape, not a runtime default or final scale.
- Accept mechanically copied, manifest-validated local Hybrid wheel caches as
  the Greedy offline wheelhouses because the Greedy cache was absent and both
  versioned service/controller wheel manifests matched exactly.  No network
  download or registry pull was authorized or performed.
- Parse Kubernetes `Ki` allocatable quantities by conservatively flooring to
  whole MiB.  Refuse malformed, negative, or unsupported units as before.
- Compare node-local images using the selected linux/amd64 OCI config digest,
  not Docker's possibly different local manifest/list ID.  Keep the local tag
  existence check and reject missing or ambiguous OCI descriptors.
- Preserve frozen three-decimal learning output in evidence.  Permit only
  `abs(sum(belief)-1) <= 0.0020000001`, the rounding bound for four entries;
  do not renormalize evidence and continue rejecting greater drift.
- Produce 256-bit/64-hex lifecycle source fingerprints, matching the already
  frozen Phase 6 persistence validator.  Do not weaken provenance validation.
- Accept both completed runs: the normal bootstrap reached equilibrium after
  14 slots and the unchanged skip-build repeat after 10.  Every slot passed
  forced captured replay and exact `N`, `2N`, `N` placement/observation/pair
  cardinalities.
- Accept the skip-build preservation proof: all retained serving Pod UIDs,
  image IDs, and restart counts were unchanged; only the finite controller Job
  UID changed.  Leave the dedicated Greedy cluster running for the separately
  authorized Phase 9 transition gate.
- Treat recorded timing and CPU/RSS/throttling values as configuration and
  operability evidence only.  Phase 8 authorizes no Greedy-versus-Hybrid
  performance conclusion, larger scale, resource retuning, or new diagnostic.

## Greedy admission-capacity correction decisions

Accepted for planning and completed offline in Phase 8.1 on 2026-08-27.

- Supersede topology-derived `ceil(N/M)` admission for the next Greedy policy
  contract. The formula was introduced during implementation planning and is
  absent from the paper's Greedy definition. Phase 8 traces remain valid only
  as historical v1 evidence and must not be rewritten.
- Preserve the precise myopic distinction from `misc/vesal_tex.tex`: Greedy
  observes earlier assignments and evaluates immediate utility at
  `current_load+1`, but never adds predicted future selections. Describe this
  as current-congestion-aware and future-congestion-blind, not as completely
  congestion-blind.
- Do not replace the removed formula with another inferred capacity or a new
  default. V2 policy feasibility is canonical identity plus public Ready
  state. A future real admission limit requires an explicit, separately
  approved input calibrated identically for every compared policy.
- Keep Kubernetes node allocatable-versus-Pod-request preflight. It protects
  cluster scheduling and is not a per-replica flow admission rule. Keep the
  state-conditioned processing congestion model unchanged.
- Preserve the user's deliberate exact `L=2` action even though the paper's
  baseline prose describes one independent choice per stage and its
  SFC-specific budget remark uses `L=K`. Preserve mandatory complete actions
  and best-feasible non-positive selection for this correction; those are
  explicit container-baseline decisions outside the capacity defect.
- Version the corrected contract as `pure-greedy-budgeted-l2-v2`. Remove the
  capacity field/label from policy, discovery, controller input, rendered
  resources, and evidence assumptions rather than setting it to a large
  topology-derived number.
- Update the matched-comparison contract honestly: active Hybrid still carries
  its recorded synthetic capacity behavior. Until a separately authorized
  matched-capacity correction is executed for the comparison target, do not
  claim that Greedy v2 and current Hybrid have identical admission semantics.
  Do not modify frozen `IBG_Hybrid/` during the Greedy correction.
- Split acceptance into Phase 8.1 offline contract migration and Phase 8.2
  separately authorized live validation. Phase 9 scale/final-baseline work
  remains blocked until both corrective phases pass.
- Retain unchanged expected-utility, learning, metrics, stochastic schedules,
  runtime profiles, processor congestion, Kubernetes Pod-resource preflight,
  and all serving resource/security contracts. Adapt policy state, discovery,
  rendering, rollout/lifecycle, comparison, and new evidence only behind the
  v2 Greedy boundary. Preserve the removed capacity shape only in explicit v1
  trace validation; exclude synthetic capacity and Hybrid policy machinery
  from active Greedy v2.
- Version only affected contracts: policy, Ready discovery, static deployment,
  rollout/launch, matched comparison, slot evidence, and JSONL trace. Keep
  unaffected learning, utility, SLA, fairness, equilibrium, profile, timing,
  resource, and route contracts at their existing versions.
- Separate v2 CSV output under `figures/Greedy/v2` and require an atomic
  policy-version marker. Refuse unversioned retained CSV and mixed v1/v2
  columns rather than inventing an implicit migration.
- Record active Hybrid's `ReplicaAdmission.max_assigned_flows` and
  `assigned_flow_capacity=ceil(N/M)` as an unresolved comparison mismatch.
  A final same-input performance claim requires a separately accepted common
  physical/admission rule; frozen `IBG_Hybrid/` remains unchanged.

## Greedy end-to-end fairness correction decisions

Accepted for planning and completed offline in Phase 8.3 on 2026-09-01.

- Score Greedy's Jain index over the paper's end-to-end per-flow utility. Eq.
  (e2e_utility) in `misc/vesal_tex.tex` defines per-flow utility as the
  selected stage utilities minus the inter-stage link costs, and the metric
  list scores fairness over that same quantity. The retired Greedy input
  summed only the stage utilities and dropped the link term entirely, so it was
  not the paper's `U_i` under any reading.
- Treat the previous behavior as a defect, not a preference. With the link term
  absent the index is a function of belief and final load alone; a slot with
  uniform slot-start beliefs and near-uniform loads yields one identical
  predicted value per flow and a near-perfect index no matter what the flows
  experienced. The observed `40x3x20` slot reported `0.999994` while its
  realized end-to-end values ranged 59.69 to 159.15 and its per-flow measured
  pair cost ranged 8.74 to 66.98 ms.
- Use the realized series rather than a belief-weighted reconstruction. Greedy
  is deliberately forbidden from reading link costs at selection time, so it
  owns no planning link cost to subtract and cannot reproduce Hybrid's
  predicted form. Realized physical utility minus measured pair latency is the
  quantity Greedy can compute honestly, and it is what a testbed results
  section should report.
- Floor each per-flow end-to-end utility at zero before scoring. Jain is only
  meaningful on nonnegative values: on mixed signs it reported a slot with
  three healthy flows and one ruined flow as `0.075`, and a slot with every
  flow ruined as a fair-looking `0.67`. A flow that loses more to latency than
  it earns gained no utility. This is a deliberate, documented deviation from
  the paper's raw expression, made because the paper never bounds `U_i` below.
- Record `fairness_domain_valid` beside the index, true only when every
  unclamped per-flow value was strictly positive. Do not silently bake the
  floor in, and do not fail the slot closed: aborting a live multi-slot run
  over a reporting-domain condition would destroy operable evidence.
- Report `0.0` with the flag false when no flow gained anything. That case is a
  genuine 0/0 and any value is a convention; record it as an explicit
  convention rather than a computed number.
- Version only the affected contracts. The policy is unchanged and stays
  `pure-greedy-budgeted-l2-v2`. Bump metric assembly to
  `greedy-active-slot-metrics-v2`, slot evidence to
  `greedy-kernel-slot-evidence-v3`, and the trace to
  `greedy-experiment-jsonl-v3`. Keep v1 and v2 documents immutable, readable,
  and validated against the retired predicted formula; new writers must not
  backfill `fairness_domain_valid` into them.
- Pin the retained CSV generation on both the policy and trace contract, and
  move the default output to `figures/Greedy/v3`. The policy version alone no
  longer separates generations, so a pre-Phase-8.3 marker or a foreign trace
  version must fail closed rather than append a predicted-fairness column
  beside an end-to-end one.
- Record the resulting Greedy/Hybrid fairness divergence as an unresolved
  comparison mismatch. Active Hybrid scores predicted stage utility at final
  loads minus its planning link cost and applies no zero floor; frozen
  `IBG_Hybrid/` and `IBG/` are not edited by this correction. `Greedy/
  comparison.py` still lists `learning_and_metric_semantics` as a matched row;
  that row is now stale by explicit user decision and no same-metric fairness
  claim is permitted until a separately authorized matched correction is made.
- Change reporting only. Placement, expected-utility scoring, selected-only
  learning, separated jitter, physical/raw utilities, the SLA count and excess,
  and the equilibrium rule are untouched, and no historical trace is rewritten.

## Greedy rebuilt-service rollout classification decisions

Accepted and implemented on 2026-09-01 after Phase 8.3's first authorized
rebuild failed closed on a legitimate service-image change.

- Treat `exact(old) -> exact(new)` as a supported rollout state. The classifier
  previously admitted only absent or exact provenance, which meant no service
  source change could ever be applied to existing serving workloads. This was
  a latent gap, not a Phase 8.3 regression; earlier rebuilds passed only
  because the annotations were introduced in the same change and read absent.
- Gate the relaxation on a declared pending rebuild, not on matching the
  recorded pair. Comparing against `greedy-launcher-state` was tried first and
  is wrong: the transition marker is persisted before the canonical apply, so a
  run interrupted between those steps leaves the record already advanced to the
  target while the templates hold the superseded pair. That pair is then
  unrecoverable from the record and no equality test can identify it. The
  launcher can always assert that it rebuilt the service, which makes any
  non-target template stale by construction.
- Keep the fail-closed default for everything else. All four serving resources
  must agree on one mode, a mixed set stays `partial or ambiguous`, a
  half-written annotation pair still raises, and with no pending rebuild any
  non-target pair remains foreign mutation. An unrebuilt service still reports
  `converged` because its templates already match the target exactly.
- Accept that a declared rebuild will overwrite an unexpected uniform pair.
  The launcher already asserts exclusive ownership of the Greedy namespace, the
  canonical apply is the corrective action, and refusing instead would force a
  cluster teardown to recover.
- Scope the declaration to the two reconciliation call sites.
  `_reconcile_existing` passes the run's `service_restart_required`; the
  pending-rollout check passes it unconditionally because it only runs when a
  restart is already recorded. The final post-apply gate omits it, so a settled
  rollout must show exact provenance and cannot pass on a stale template.
- Reject full-cluster `cleanup` as the standing answer. It works, but forcing a
  kind teardown for every service-source change would make Phase 8.2 and all
  later rebuilds needlessly destructive.
- Accept that `Greedy/slot_contracts.py` sits in both `SERVICE_SOURCE_FILES`
  and `CONTROLLER_SOURCE_FILES`, so a controller-only metrics field still
  churns the service fingerprint. Splitting `GreedySlotMetrics` out to avoid
  that would introduce a circular import and worse layering; the correct fix
  was the rollout classifier, not the file layout.

## Planned Hybrid posterior-transmission measurement decisions

Accepted for phased implementation: 2026-08-31.

- Keep the controller-local belief state authoritative. The new receiver is a
  measurement sink for duplicate posterior updates, not a distributed learner,
  belief store, synchronization service, or decision input.
- Make the feature explicit and default-off through one production option.
  Disabled runs create no receiver, send no posterior copy, and retain the
  current zero observed belief TX/RX footprint.
- In enabled runs, use a separate worker-only receiver Pod and ClusterIP
  Service so the mirrored application body genuinely crosses a Pod boundary.
  The receiver validates and discards it; it must not return a belief vector or
  affect the next timeslot.
- Freeze one deterministic, versioned serialization contract before claiming
  exact byte values. Report separately: canonical posterior-vector bytes,
  complete mirrored application-body bytes, message count, and their sums per
  completed timeslot. Do not combine them with Kubernetes discovery, route
  commands, telemetry, protocol headers, or selected-route traffic.
- Label the result as an instrumented posterior-transmission mirror. It is real
  HTTP application-payload traffic, but it is not evidence that the operational
  Hybrid algorithm requires distributed belief exchange.
- Keep the existing observed control-plane observations and CSVs intact. Do
  not replace their zero belief TX/RX fields with modeled or mirrored values
  and do not rewrite historical traces.
- Fail enabled measurement evidence closed on missing, rejected, duplicated,
  malformed, or byte-inconsistent mirror messages. Never silently estimate a
  missing transmission or allow receiver output to influence the algorithm.
- Implement in three gates: source/manifests and focused contract tests; full
  local verification and documentation; then a separately authorized live
  enabled/disabled validation. No live mutation is authorized by this plan.

## Hybrid posterior-mirror Phase 2 decisions completed

Accepted and locally verified: 2026-08-31.

- Retain local controller beliefs as authoritative; the receiver validates and
  discards real HTTP copies and never participates in decisions.
- Keep mirror accounting separate from the existing control-plane footprint.
  In particular, observed `belief_tx`/`belief_rx` remain zero rather than being
  overwritten with mirror measurements.
- Export mirror CSVs only for the joint condition `--posterior-mirror 1` and
  `--csv 1`, under `figures/IBG_hybrid/posterior_mirror/`, using the retained
  six-character run-column layout and atomic file replacement.
- Report canonical vector bytes and complete JSON application-body bytes as
  distinct quantities. The latter includes the measurement envelope; neither
  quantity includes protocol headers or other wire overhead.
- Use the Hybrid-only `scripts/hybrid_posterior_mirror_summary.py` boundary for
  per-timeslot values, totals, median, and p95. It fails closed on inconsistent
  provenance, coverage, digests, byte totals, or receiver-run identity.
- Make no NIC, line-rate, multi-host, wire-byte, or operational distributed-
  learning claim. Phase 3 remains a separately authorized live gate.
- IBG-Exact remained untouched and was not inspected or tested for this work.
- Run the receiver from the existing Hybrid service image because that image
  owns the pinned Uvicorn dependency. Do not add an ASGI-server dependency to
  the finite controller image merely to host the separate measurement sink.
- Preserve existing non-netem StatefulSet Pod-template annotations during
  reconciliation. Do not merely ignore them in drift comparison, because
  removing one during apply could cause an unintended additional rollout.

## Greedy rollout timeout correction

Accepted: 2026-09-01.

- Treat 120 seconds as an inactivity/stall timeout, not the total allowance for
  updating every replica in a topology. Reset it only when resource generation,
  updated/Ready coverage, revision convergence, or a newly observed/Ready owned
  Pod UID proves forward progress.
- Retain an independent topology-bounded total deadline so repeated Pod churn
  cannot reset the wait forever.
- Continue to require exact StatefulSet and Deployment convergence plus exact
  Running/Ready identity coverage before creating the finite controller Job.
  Do not weaken readiness, add retries to experiment traffic, or accept partial
  serving state.

## Greedy pending service-rollout recovery

Accepted: 2026-09-01.

- Persist exact public service image/source provenance on serving Pod templates
  rather than using a mutable image tag or an unrecorded restart timestamp as
  proof of rollout completion.
- Classify an exact retained target as template-update-required, progressing,
  or converged. Resume a proven progressing rollout and reuse a proven
  converged rollout; reject partial, mixed, foreign, or mismatched provenance.
- Apply a required canonical template correction once and never follow that
  apply with an unconditional `kubectl rollout restart`.
- Remove historical `greedy.max-assigned-flows` from canonical retained
  templates as part of that same necessary revision. Do not replace it with a
  different capacity field or inferred value.
- Validate exact Ready/revision/identity coverage and running node-local OCI
  config image IDs before clearing the transition marker or creating the one
  finite controller Job.
- Keep the 120-second inactivity timer and independent topology-bounded total
  deadline. Normal readiness observations are not progress, and repeated UID
  churn cannot keep a rollout alive forever.

## Greedy belief unit-mass tolerance and live launcher output decisions

Accepted and applied on 2026-09-01, after a user `40x3x20`, 50-iteration run
failed on iteration 12 with `beliefs_after belief vectors exceed the rounded
unit-mass tolerance`.

- Correct the validator bound, not the learner. The frozen selected-only
  learner rounds each of the four posterior entries to three decimals
  independently and never renormalizes, so a single slot can miss unit mass by
  4 * 0.0005. Because every slot re-rounds a retained belief at
  `GREEDY_BELIEF_RETENTION` 0.8, that per-slot error accumulates geometrically
  toward `4 * 0.0005 / (1 - 0.8)` = 0.01. The former `0.0020000001` bound was
  derived for one rounding pass and therefore rejected legitimate learner
  output on any sufficiently long run. Set
  `GREEDY_ROUNDED_BELIEF_SUM_TOLERANCE` to `0.0100001`.
- Do not renormalize in `aggregation()`. That would change actual belief values
  and diverge the Greedy learner from the frozen Exact learner it mirrors, to
  repair what is only a validation bound. The drift is already inert:
  `expected_stage_utility_from_belief` divides by the belief sum, so placement,
  learning, utility, SLA, fairness, and equilibrium never see it.
- Bump no contract. The evidence, trace, metric, and policy semantics are
  unchanged; only a malformed-input bound moved. Historical traces stay
  readable and are not rewritten.
- Treat completed-slot console output as display only. The launcher now follows
  the finite controller Job with `kubectl logs --follow` and prints each
  non-evidence line as it arrives, so a long run reports progress instead of
  emitting everything after completion. Machine-readable
  `GREEDY_SLOT_EVIDENCE=` lines stay hidden from that stream.
- Keep the follow strictly separate from evidence. Job completion is still
  decided by the `kubectl wait` condition, and the authoritative log text is
  still re-read from the finished Job, so a dropped, truncated, or reordered
  follow cannot shorten or alter a persisted trace. The lifecycle hook defaults
  to absent, so every non-launcher caller keeps the previous behavior.

## End-to-end SLA threshold raised to 130 ms

Accepted: 2026-09-02.

The end-to-end reporting SLA threshold moved from 80 ms to 130 ms at the user's
direction, for **both** Greedy and Hybrid together. It passed briefly through
100 ms, which trace evidence showed was too tight (see the calibration below);
100 ms therefore also became version-bounded history rather than an active
value. Changing only one policy
would have made their `end_to_end_sla_violations` and `end_to_end_sla_excess_ms`
series incomparable, which the cross-policy comparison honesty rule forbids
stating as a same-input result.

- `Greedy/phase0_contract.py` — `GREEDY_SLA_LATENCY_THRESHOLD_MS = 130.0`
- `IBG_Hybrid/runner.py` — `HYBRID_SLA_LATENCY_THRESHOLD_MS = 130.0`

This threshold is the raw end-to-end reporting metric only. It is distinct from
`IBG/latency_model.py`'s `DEFAULT_SLA_LATENCY_MS = 110.0`, which remains the
selected-processing SLA under `physical-only-v1` and continues to drive realized
utility. Neither the 110-ms SLA, the physical `half-normal-additive-v1` scales,
nor the `half-normal-observation-v1` observation scales were touched.

Historical traces stay readable rather than being migrated or rewritten. Both
validators accept the active value or any version-bounded historical one, held
newest-first in `HISTORICAL_GREEDY_SLA_LATENCY_THRESHOLDS_MS` and
`HISTORICAL_HYBRID_SLA_LATENCY_THRESHOLDS_MS`, currently `(100.0, 80.0)`. New
writers never emit a historical value:

- `Greedy/evidence.py` — `validate_greedy_slot_evidence`
- `scripts/run_hybrid_kernel_phase4.py` — Hybrid trace slot-metric validation

No evidence contract version was bumped. The recorded metric field
`sla_latency_threshold_ms` does not change shape, and both validators already
recompute violations and excess from each trace's own recorded threshold, so a
trace is always checked for internal consistency against the value it declares.
Any third value is still rejected as drift, preserving the original intent of
the check. Mixed-generation CSV remains refused rather than implicitly migrated.

Greedy Phase 2 and Phase 3 boundary tests now derive the boundary from the
constant instead of pinning 80 ms, so a future threshold change does not silently
invalidate the strict-inequality coverage.

### 130 ms calibration evidence

Chosen from `runs/ibg-hybrid-experiment-20260902T123510.217103Z.jsonl` — a
50x3x10 deterministic-lookahead run, `netem` disabled, 11 slots to equilibrium,
550 flow samples, `profile-seed=50`.

Steady state (last 5 slots, n=250): p50 94.9 ms, p90 123.2 ms, p95 130.2 ms,
max 161.9 ms. Latency decomposes as physical processing p50 71.5 ms and measured
pair p50 26.5 ms, so roughly three-quarters of end-to-end is processing.

Violation rate by candidate threshold:

| Threshold | All 11 slots | Last 5 slots |
|---|---|---|
| 80 ms | 79.1% | — |
| 100 ms | 53.6% | 43.2% |
| 110 ms | 41.8% | 29.2% |
| 120 ms | 29.6% | 13.2% |
| 130 ms | 19.5% | 5.6% |
| 150 ms | 8.4% | 1.2% |

100 ms sat at the steady-state median, so it failed ~43% of flows after beliefs
converged. A threshold at the median reports the centre of the distribution
rather than its tail and compresses any Greedy-versus-Hybrid difference toward a
coin flip. 130 ms sits just past the steady-state p90/p95, giving 5.6% steady
violations while still exposing the learning transient at 19.5% across all
slots.

Caveats recorded rather than resolved: this is a single run at one profile seed,
and the choice is conditioned on `netem` being disabled. Enabling replica-Pod
egress delay grows the pair component and invalidates this calibration.
