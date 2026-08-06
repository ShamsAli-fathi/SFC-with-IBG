# IBG Testbed Expansion Roadmap

Work proceeds in order. A phase starts only after the previous phase's checks pass and `STATUS.md` records the result. This roadmap replaces the completed lightweight-migration roadmap as the active plan; it does not invalidate its Phase 6 simulation/Kubernetes parity evidence.

## Scope and terminology

The frozen baseline is the decoupled exact IBG testbed: the Python solver, utility grid, learning rule, equilibrium rule, FastAPI replica contract, flow-generator contract, and the supported three-flow/three-stage/five-replica validation remain the behavioral reference.

`Kernel` means the ordinary Linux socket/TCP/IP path already used by the HTTP workloads. The later comparison target is `dpdk-vpp`: VPP running in Linux user space with its approved DPDK I/O backend. VPP can also integrate with the Linux control plane or use non-DPDK interfaces, but that is not a third comparison arm in this roadmap. The immediate work is to make the Kernel baseline explicit; DPDK/VPP is a later target, not an implemented capability or a current validation claim.

In every mode, FastAPI remains responsible for `/health`, `/process`, replica identity, physical processing, the selected-hop noisy learning signal and likelihood, and application-level latency/concurrency telemetry. A datapath may forward traffic and contribute transport telemetry, but it must not generate observations, update beliefs, alter the solver's final assigned load, or cause unselected replicas to emit samples. This preserves the paper's asymmetric and partial-observation requirement.

## Completed foundation

Status: complete.

- The decoupled exact `BR_EIBG` solver and its mathematical characterization are protected by tests.
- Simulation and lightweight Kubernetes/HTTP runs match for the supported configuration over seeds 2050, 2051, and 2052.
- The controller selects already-running Ready Pod endpoints; FastAPI replicas and the flow generator exercise only the selected complete routes.
- Legacy observations are kept separate from measured HTTP latency and actual admission concurrency.

Gate: retained as the regression baseline for every expansion phase.

## Phase 0: Freeze the expansion contract

Status: complete.

Suggested Codex reasoning: `high` — new datapath components must not silently change the IBG experiment or its asymmetric-observation semantics.

- Record FastAPI/Kubernetes as the known-good Kernel baseline and preserve its controlled parity fixtures and JSONL event schema.
- Define `kernel` and future `dpdk-vpp` as explicit datapath modes behind traffic/telemetry adapters; do not add datapath branches to `IBG/claude.py`, replica utility functions, or learning code.
- Require each selected hop to retain slot, flow, stage, replica, endpoint, Pod, and node correlation. The implemented baseline retains exactly one legacy sample per selected hop; Phase 1 deliberately migrates that sample to processing latency without expanding observation access.
- Keep the current report factual: DPDK/VPP must remain labelled planned until its corresponding gate is verified.

Gate: architecture, decision, status, and roadmap handoffs describe the frozen mathematical baseline, the Kernel-versus-DPDK/VPP comparison, and coupled IBG as separate scopes.

## Phase 1: Introduce the latency-based state, signal, and utility model

Status: complete.

Suggested Codex reasoning: `xhigh` — changes to the IBG mathematics, stochastic assumptions, utility/observation parameters, or equilibrium behavior can invalidate the established behavioral baseline.

- Keep each replica's true state hidden from flows and the controller. Use deterministic state assignments for parity/characterization and seeded draws from a declared prior for experiments; keep a controlled state fixed for the full run unless a later state-transition model explicitly replaces the stationary-state assumption.
- Treat datapath mode as known context, not a hidden state. Order the four performance states from state 1 (bad) to state 4 (good), with monotonically decreasing baseline latency and jitter, increasing effective capacity, and weakening congestion penalties.
- Make selected-hop processing latency both the continuous private signal and the latency variable: $s=q$. Generate it from $Q_\theta(n)=\mu_\theta+a_\theta\max(0,n-1)+b_\theta\max(0,n-\kappa_\theta)^2+\epsilon_\theta$, where $n$ and $\kappa_\theta$ use concurrent-flow units, $a_\theta$ models ordinary congestion, $b_\theta$ creates a post-capacity knee, and state-dependent Gaussian jitter is truncated only as needed to keep total latency positive.
- Compute the four likelihood values from the load-aware law $f(q\mid\theta,n,\text{datapath})$. The optional categorical signal is only $\arg\max_\theta f(q\mid\theta,n,\text{datapath})$ for reporting; the likelihood vector drives the existing posterior and aggregation path.
- Replace the inverse kernel with the linear latency utility $u_k(q)=R_k-\alpha_kq-c_k$, with $\alpha_k>0$. Congestion already affects $q$, so do not apply an additional $(1+\gamma n)$ multiplier.
- Define end-to-end utility as the sum of expected stage utilities minus weighted inter-stage link latency. In the decoupled solver, a link term may affect placement only when it is constant or stage-separable; replica-pair link costs create cross-stage coupling and remain deferred. Always report realized end-to-end utility after routing.
- Replace state-ID-based SLA violations with per-flow latency-threshold checks over observed end-to-end processing plus link latency. Preserve processing latency, client request latency, link/transport contribution, assigned load, and admitted concurrency as distinct fields.
- Make FastAPI behavior state-conditioned using the same baseline, congestion, capacity, and jitter model. Only selected replicas emit latency signals. Kernel scheduler/network variation is real telemetry and must not be mislabeled as deterministic model output.
- Add deterministic tests with injected/seeded latency sources, likelihood/posterior fixtures, monotonic state and congestion checks, utility/end-to-end/SLA fixtures, and selected-only observation checks. Validate exact simulation/Kubernetes controller parity by replaying identical captured signals; validate live latency statistically through state ordering, congestion response, and likelihood calibration rather than requiring bit-for-bit timing equality.
- Remove or explicitly migrate obsolete parameters (`gamma`, unused replica `delay`, synthetic legacy signal fields, and the old state-based SLA rule) only when their replacements are covered by tests and trace/schema compatibility is addressed.

Gate: complete. The pure latency model, provisional ordered profiles, load-aware likelihoods, selected-only observation adapters, linear utility, end-to-end processing/transport metrics, latency SLA, compatibility schema, and replay validation are covered by 82 passing tests. Python sources compile successfully. Final experimental values and live state/congestion calibration belong to Phase 2.

## Phase 2: Calibrate latency and utility parameters

Status: complete.

Suggested Codex reasoning: `xhigh` — parameter fitting must produce interpretable state separation and congestion thresholds without tuning results opportunistically or confusing model capacity with measured datapath capacity.

- Declare a calibration load horizon $N_{\mathrm{cal}}$ and target zero-crossing bands before fitting. For each true state define $n_\theta^*=\min\{n\ge1:\mathbb{E}[u_k(Q_\theta(n))]<0\}$ and require $n_1^*<n_2^*<n_3^*<n_4^*$: bad replicas become unattractive early, while perfect-state replicas remain positive until high congestion.
- Calibrate the latency law first. Fit or select $\mu_\theta$, $a_\theta$, $b_\theta$, $\kappa_\theta$, and $\sigma_\theta$ from declared state semantics and measured FastAPI behavior, preserving monotone state ordering and realistic latency distributions.
- Calibrate policy values separately. Choose $R_k$, $\alpha_k$, and $c_k$ to express the desired latency valuation and zero-utility threshold $(R_k-c_k)/\alpha_k$ rather than using them to conceal a poor latency fit. Calibrate $\alpha_{\mathrm{link}}$ and per-flow SLA threshold $\tau_i$ in compatible milliseconds/utility units.
- Use a committed calibration script or focused tests to perform deterministic grid/constraint search, curve generation, seeded jitter Monte Carlo, and sensitivity analysis. Manual trial runs may inform bounds, but every accepted value must be reproducible from recorded inputs.
- Evaluate utility curves beyond the three-flow exact-solver validation size without claiming solver scalability: direct kernel evaluation may sweep $n=1,\ldots,N_{\mathrm{cal}}$, while full equilibrium/parity tests remain at supported size.
- Validate low-load positivity, target zero crossings, state ordering, congestion knees, overlap/noise robustness, SLA probabilities, and sensitivity to nearby values. Then confirm representative points against live Kernel/FastAPI telemetry.
- Explicitly decide what a negative utility means before treating it as flow rejection. The current exact one-of-M solver always assigns one replica per stage; calibration alone does not add skip/reject behavior. Until a separate admission policy is approved, require at least one feasible replica per stage in the supported operating range and report negative utility as infeasibility outside it.
- Record the final parameter table, units, target bands, calibration evidence, seeds, and supported operating range in the handoffs and deterministic profiles.

Gate: complete. `scripts/phase2_calibrate.py` records a 12-flow horizon, accepted state/policy tables, crossing bands, seeded Monte Carlo classification/SLA evidence, and sensitivity scenarios. A 5,000-sample-per-state/load run reached 94.42% minimum model classification accuracy and preserved crossings 3, 5, 7, and 11 under every declared sensitivity. Forty repeated localhost Uvicorn observations across all states passed correlation, signal, likelihood, positivity, timing-tolerance, and at-least-80%-per-point live classification checks. The supported load-3 range retains a positive state-4 option; negative utility does not reject a flow. Kubernetes Kernel-mode tolerances remain Phase 3 work.

## Deferred conditional work: extend utility calibration to 50 loads

Status: required before any study uses accepted utility values above 12 assigned flows per replica; not scheduled now.

This is independent of any future heuristic approximation for the recursive solver. It evaluates the existing latency and utility formulas directly; it must not modify `BR_EIBG`, placement behavior, or claim exact-solver scalability at 50 total flows.

- Set $N_{\mathrm{cal}}=50$ and select state parameters that preserve ordered behavior with target first-negative-load bands: state 1 at 3--6, state 2 at 12--20, state 3 at 25--35, and state 4 at 45--50.
- Keep $Q_\theta(n)=\mu_\theta+a_\theta\max(0,n-1)+b_\theta\max(0,n-\kappa_\theta)^2+\epsilon_\theta$ and $u(q)=R-\alpha q-c$ unless separately authorized to change the model.
- Generate expected utility tables for loads 1--50; rerun ordered-curve, zero-crossing, Monte Carlo, and sensitivity checks; then update code, tests, and handoffs.
- Record that this horizon refers to one replica's assigned load. A future total-flow count may be higher or lower depending on route placement.

Gate: reproducible 1--50 utility evidence meets the declared bands and documents the accepted parameters, while keeping solver/heuristic scope explicitly separate.

## Phase 3: Establish an explicit Kernel datapath baseline

Status: complete.

Suggested Codex reasoning: `high` — the existing HTTP path is functionally valid, but it needs a stable mode contract and evidence suitable for a later comparison.

- Expose the existing Kubernetes HTTP route as the named `kernel` datapath mode without changing route selection, FastAPI request semantics, or solver inputs.
- Add mode-aware traffic/telemetry adapter contracts and trace metadata so each completed slot records the active datapath and its mode-specific transport measurements.
- Verify that all traffic remains limited to controller-selected routes and that only the approved selected-hop processing latency is converted into a belief observation.
- Capture reproducible Kernel baseline runs at the supported configuration, including host, image, Kubernetes, and mode configuration needed for later comparison.

Gate: complete. `kernel` is explicit from adapters through traces, while the FastAPI replica request and all solver/learning inputs remain unchanged. A supported seed-2050 run reached equilibrium in nine iterations with 81 complete selected hops over loads 1--3. All hop modes, selected-only correlations, signals, likelihoods, and non-negative request-overhead fields were complete. Load-1 state means remained ordered, observed state-3/state-4 congestion groups were non-decreasing, categorical accuracy was 83.95%, and 98.77% of hops met the accepted $\max(10\text{ ms},10\%)$ server-overshoot tolerance. Replaying all nine slots produced zero mathematical drift in placements, grids, observations, beliefs, utility, SLA, fairness, and equilibrium. `scripts/phase3_kernel_baseline.py` reproduces the gate from the ignored JSONL trace.

## Phase 4: Curate evidence and user-directed reports

Status: in progress. The completed control-plane/learning-signal branch and locally implemented separated-jitter side branch below are part of Phase 4; reporting curation remains active and does not authorize Phase 5 or later work.

Suggested Codex reasoning: `high` — evidence must remain traceable to a reproducible run and must not silently turn synthetic testbed results into hardware or datapath claims.

- Help the user gather, inspect, summarize, and explain existing simulation and `kernel` evidence, including structured JSONL traces, host-side CSV exports, validation summaries, calibration results, and focused test outcomes.
- Preserve provenance for every reported figure or claim: record the source command/trace, seed, dimensions, image/mode, and whether a result is mathematical replay, modeled calibration, localhost FastAPI conformance, or live Kubernetes telemetry.
- Keep claims bounded: the HTTP/Kubernetes route is the validated `kernel` baseline; do not imply DPDK/VPP, SR-IOV, hugepages, hardware offload, line-rate, or real CNF validation.
- Treat report content as user-directed work. Do not read or edit `Tutorial.md`, `Report.md`, or `EVIDENCE_SUMMARY.md` unless the user explicitly requests that file in the current task. Do not rewrite generated evidence files; derive new summaries or figures only when requested.
- Refresh user-directed legacy `Chart/*.py` scripts one at a time for current reporting artifacts. Each authorized `Chart/<plot>/` folder must be self-contained: its script defaults to the primary current CSV and optional baseline CSVs beside it, never shared `figures/`. Preserve each original script's visual design/theme and embedded text unless the user explicitly requests a change. Once a script is authorized, iterative visual tuning (range, title, label, or styling) is local work; do not reread or update handoffs for it unless the user explicitly asks to record a final decision. The Jain-fairness refresh is finalized. SLA-small version 2 is also finalized: `Chart/sla-small/2/sla-small.py` discovers one same-folder `*_IBG.csv`, applies its original five-slot moving average over the first 50 timeslots, handles MILP as an optional legacy baseline, and is scoped to the small-scale experiment. Utility-small is finalized: `Chart/util-small/util-small.py` reads its local `realized_end_to_end_utility_IBG.csv`, applies a trailing five-timeslot moving average, uses discrete timeslots and a 2,500--3,500 y-axis, and omits the optional local MILP reference when absent. Each future refresh must identify the current metric source and preserve its semantics; do not inspect or change other Chart content without a separate request.
- Answer user questions and add narrowly scoped reproducibility aids when needed, without changing the decoupled solver, the current separated physical/learning observation contract, or one-of-M no-rejection behavior. The former 110-ms physical-plus-pair SLA calibration remains historical. Because the unresolved public-forwarder pair residual made its outcome series unstable, the user authorized the reversible `physical-only-v1` outcome contract: 110-ms SLA and realized utility use observed selected physical processing only, while raw pair and end-to-end latency/utility remain recorded. `physical-plus-pair-v1` is available to restore the historical outcome basis without changing selection. This may be temporary or permanent and needs fresh normal-build/replay evidence; it does not authorize pair-dependent selection. The user set the unchanged equilibrium check to strictly below 0.033 per belief entry after brief 0.03, 0.037, and 0.04 settings; this changes only when an experiment stops. The user also authorized `--runs N` repeated launcher execution: it runs N independent Jobs after one deployment preparation and preserves a separate trace/CSV column for each.

### Phase 4 side branch: nonnegative observation jitter

Status: complete. Overall Phase 4 reporting curation remains active.

The active physical `half-normal-additive-v1` model uses $J_\theta=|Z_\theta|$, $Z_\theta\sim\mathcal N(0,\sigma_\theta^2)$, with state-1-through-state-4 scales 6, 5.25, 4, and 3.25 ms. The user-authorized selected learning signal adds an independent $E_\theta=|W_\theta|$ under `half-normal-observation-v1`, with scales 7.2, 6.3, 4.8, and 3.9 ms. Both terms are nonnegative, but only physical processing latency enters the active `physical-only-v1` outcome utility and 110-ms SLA. This branch does not change the exact decoupled solver, placement, selected-only boundary, posterior aggregation/retention 0.8, utility form, no-rejection policy, raw pair-cost measurement, strict `<0.033` equilibrium rule, or datapath implementation.

- Physical sampling/expectation retains its half-normal law. Learning likelihood uses the exact convolution of independent physical and observation half-normal densities, with zero support below each state's deterministic state/load baseline.
- Runtime and trace boundaries separately record modeled/measured physical processing, observation jitter, and noisy signal; validation requires `signal = measured processing + observation jitter`. Seeded observation jitter uses an independent request-stable stream so it does not alter seeded physical samples.
- The official 5,000-sample seed-2050 calibration passes: minimum classification is 81.38%, mean load-1 accuracy is 87.74%, and crossings remain 3/5/7/11. Its former physical-only 110-ms SLA gate is historical; the active outcome threshold is now also 110 ms but applies to the current `physical-only-v1` reporting contract and needs fresh live/replay evidence. The classification gate now requires at least 80% minimum accuracy and at most 90% mean load-1 accuracy.
- Deterministic sampler/PDF/likelihood, separation, correlation, utility/SLA-boundary, calibration, replay, and selected-only tests pass locally. After a successful normal image build/deploy, current-image supported trace `runs/ibg-experiment-20260721T145856Z.jsonl` reached equilibrium in 16 slots, passed the Kernel gate with 86.11% classification and 97.22% server-overshoot compliance, and exact-replayed with zero drift. It was launched with `--skip-build` only after the normal build/deploy had completed. Trace `runs/ibg-experiment-20260719T125810Z.jsonl` remains tied to the superseded 8/7/5.5/4.5-ms physical profile and must not be claimed as current-head evidence.
- Earlier traces and calibration results remain tied to their symmetric-jitter code version and are not reinterpreted as validation of the replacement model.

Gate: complete. The separated distributions and parameters are recorded; sampling, convolved likelihood, calibration, current-image supported live evidence, and exact replay agree. Solver, placement, selected-only scope, physical utility/SLA inputs, pair-cost, and equilibrium invariants remain unchanged.

### Phase 4 side branch: opt-in solver-resource footprint

Status: complete. Phase 4 reporting curation remains active for user-directed report writing.

- The opt-in `--memory 1` launcher mode records `solver_resource_v1` only for completed slots. It captures controller-process RSS baseline, sampled active-slot peak, post-feedback residual, and peak incremental bytes without using Kubernetes requests/limits or cumulative process-lifetime peak as a proxy.
- The exact policy exposes memo-table entries immediately before and after every existing stage embedding/cache disposal, retaining per-stage attribution. This establishes the exact baseline for a later heuristic without approximating, altering, or extending the solver.
- Keep memory bytes/MiB and cache entries as distinct units. A future payload-style stacked memory bar may show baseline RSS plus incremental working memory, but cache entries must remain a separately labelled value or series. This measures internal computational footprint, not selected-route telemetry or wire traffic.
- Trace/replay validation, `scripts/solver_resource_summary.py`, deterministic RSS/cache fixtures, and handoff documentation are implemented. Old traces remain ineligible because the samples were never recorded. The mode is off by default and leaves solver behavior, placement, learning, utility, SLA, raw pair cost, and runtime resources unchanged. The complete non-Chart suite passes with 171 tests. User-run normal-build trace `runs/ibg-experiment-20260722T112356Z.jsonl` records 13 completed 15-flow/3-stage/8-replica slots with valid resource data: 490,314 peak exact memo entries per stage, zero residual entries after every clear, 255.5 MiB maximum controller RSS, and 97.44 MiB maximum within-slot incremental memory. It is exploratory 15x8 memory evidence, not a formal supported-size Kernel gate.

Gate: complete for the current Exact reporting baseline. Local validation and the user-run normal-build 15x8 trace demonstrate complete, nonnegative, internally consistent samples with zero cache residual. A future heuristic must use this same schema under matched dimensions; the existing 15x8 evidence remains exploratory and does not extend the supported Kernel gate.

### Phase 4 side branch: opt-in Kernel network impairment

Status: implemented and validated as `netem_v1` on the user-selected exploratory topology of 10 flows, three stages, and six replicas per stage.

- Keep ordinary runs unchanged. `--netem 1` applies configured normal-distribution delay and jitter to replica-Pod `eth0` egress; the default remains `--netem 0`.
- Apply the qdisc through a bounded init container with only `NET_ADMIN`, record the complete configuration in every JSONL event, and remove the impairment naturally when the StatefulSet Pods are replaced.
- Keep network impairment outside the physical-processing and observation-only jitter laws. It must not alter the exact solver, placement, selected-only learning, utility/SLA inputs, equilibrium, or raw pair-cost formula.
- Use `scripts/network_impairment_summary.py` for matched trace validation and reports of convergence, true-state posterior, selected-state mix, prediction accuracy, utility, and SLA.
- Defer packet loss until a separate complete-slot failure/retry/missing-observation policy is authorized.

Acceptance evidence: normal-build impaired trace `runs/ibg-experiment-20260727T122310Z.jsonl` used 10-ms delay and 3-ms jitter and reached equilibrium in 18 slots. Its mean true-state posterior rose from 0.362 to 0.833, and its Good/Excellent selection share rose from 80.67% over the first five slots to 100% over the final five. Matched no-netem trace `runs/ibg-experiment-20260727T122446Z.jsonl` reached equilibrium in 12 slots and likewise ended with 100% Good/Excellent selection over its final five slots. Both traces replay the unchanged mathematics with zero drift; they are exploratory robustness evidence, not a replacement supported-size Kernel gate.

### Phase 4 follow-up: exploratory 15x8 runtime regression

Status: controller-memory diagnosis and repair complete. Phase 4.1 reduced an independently diagnosed pair-route residual but remains in progress because later diagnostic evidence still shows intermittent forwarding-path spikes. The user has temporarily-or-permanently moved reported outcomes to the reversible physical-only basis rather than treating that residual as solved. This does not authorize coupled IBG, an approximate solver, or a jitter retune.

- The two historical 15-flow/8-replica Kernel traces, `runs/ibg-experiment-20260721T130536Z-run001.jsonl` and `runs/ibg-experiment-20260721T130912Z-run002.jsonl`, reached equilibrium but ended with 10/15 and 13/15 violations under their then-110-ms physical-plus-pair threshold. Their final physical processing means were 67.01 and 70.74 ms, pair-cost means 50.95 and 60.36 ms, and end-to-end means 117.96 and 131.10 ms. No final flow exceeded 110 ms from physical processing alone; every historical violation crossed it only after post-placement pair cost.
- This is not proven to be caused by the separated observation model. The new likelihood adds roughly 0.0035 ms per call in a local microbenchmark and is excluded from SLA/utility. A pre-observation-jitter 15x8 trace, `runs/ibg-experiment-20260719T131303Z-run002.jsonl`, already ended with 14/15 violations and 74.39 ms mean pair cost. The observation model can still affect routes indirectly through beliefs, so a same-environment A/B comparison is required before accepting or rejecting that contribution.
- The prolonged slot time had a concrete controller-memory cause. Each 15x8 exact stage visits 490,314 memoized load states; the recursive `lru_cache` wrapper retains its complete table through a self-cycle after placement. The repair preserves exact behavior by using a compact state key and clearing the memo table in a `finally` block immediately after stage embedding. Normal-build trace `runs/ibg-experiment-20260721T144252Z.jsonl` completed 19 slots without OOM, replayed with zero drift, and reduced median elapsed/admission/controller-CPU time to 10.41/10.06/9.91 s. Do not replace or approximate the exact solver.
- The initial public-forwarder CPU-throttling hypothesis was tested and not confirmed for the original one-worker runtime. Per-slot selected-forwarder cgroup deltas in the separated-mode diagnostic run were zero across 299 samples; the physical-only A/B had one 6.104 ms event that did not align with high pair cost. This correctly blocked a speculative resource change at that stage. Later `forwarding_path_v1` evidence and no-controller fixed-route probes localized the residual to concurrent single-worker public-forwarder HTTP queueing. The pair formula and raw measurement remain unchanged.
- `forwarding_path_v1` is an opt-in shared-clock diagnostic only, not a cross-host/wire-latency claim. Fresh trace `runs/ibg-experiment-20260721T180604Z.jsonl` and the fixed-route probes established the Phase 4.1 comparison point: source-to-target-handler averaged 18.18 ms (p95 40.11), six-request waves reached 9.46/21.07/24.50 ms, and fifteen-request first waves reached 23--38 ms.

### Phase 4.1: Kernel forwarder concurrency remediation

Status: in progress. The normal-build live `forwarding_path_v3` diagnosis, worker-identity correlation, warmed fixed-route waves, and bounded read-only host/runtime observations are complete to the current diagnostic boundary. The matched downstream 30-second keep-alive A/B confirmed substantial connection reuse but did not establish stable pair cost. Reconnects explain first-wave tails, while source public-forwarder event-loop scheduling delay is a supported proximal contributor to part of the reused-connection residual. It did not identify a single Uvicorn worker or a root cause, so it does not justify a runtime change. Overall Phase 4 reporting curation remains active.

This bounded runtime branch runs two Uvicorn workers in each public-forwarder container while leaving every private processor single-worker. It changes neither the exact decoupled solver nor the processing/learning path. The measured one-worker forwarder peak was 52.4 MiB inside a 256 MiB limit. The two-worker configuration raises only the memory request from 64 to 128 MiB and retains the 256 MiB limit. An initial 500m CPU-limit probe exposed correlated quota stalls, so a controlled A/B justified a 1-CPU limit while retaining the 25m CPU request. Repeated same-/cross-worker probes at the accepted resources recorded zero throttle deltas, five-wave six-request means of 6.57/5.75 ms, and fifteen-request means of 7.73/8.01 ms. Maximum observed forwarder memory was about 141 MiB with no OOM, pressure event, or Pod restart.

Normal-build exploratory trace `runs/ibg-experiment-20260721T191126Z.jsonl` combined forwarding-path and cgroup diagnostics, completed 17 slots, and recorded zero selected-forwarder throttling deltas. Its extra snapshot traffic is kept separate from the clean comparison. Same-image clean trace `runs/ibg-experiment-20260721T191634Z.jsonl` used only forwarding-path diagnostics, reached equilibrium in 12 slots, and reduced all-slot per-flow pair mean/p95 from 45.78/80.09 ms in the one-worker diagnostic trace to 36.81/63.22 ms. Source-to-target-handler mean/p95 fell from 18.18/40.11 to 13.65/31.72 ms. Its final physical/pair/end-to-end means were 67.71/27.58/95.29 ms, with 0/15 SLA violations and realized utility 3025.72. All Pods remained restart-free, and exact replay matched all 12 slots with zero mathematical drift. The general validator remains false as expected because 15x8 is outside the supported configuration and one exploratory congestion group was non-monotonic; classification, scheduling tolerance, pair integrity, equilibrium, and replay passed.

Later diagnostic trace `runs/ibg-experiment-20260721T193017Z.jsonl` demonstrates why this phase cannot yet close. It finished at 0/15 SLA violations but had an all-slot pair mean/p95 of 31.18/70.59 ms, including slot 6 at 67.81 ms per flow and 15/15 SLA violations. That slot's source-to-target-handler mean was 25.19 ms and target-handler mean was 88.87 ms, versus normal-slot ranges of roughly 7--10 ms and 55--65 ms. Every selected-forwarder cgroup delta remained zero, and target concentration was no greater than four flows, so neither CPU quota throttling nor concentration alone explains the spike. The present timestamps cannot separate source-forwarder scheduling, destination-forwarder scheduling, and destination private-processor waiting. The next bounded diagnostic is additional per-request boundary timing only; it must leave all IBG logic and reported pair semantics unchanged.

That diagnostic-only split is implemented as `forwarding_path_v2`. It retains every v1 aggregate and the unchanged pair-cost formula, while adding target ingress/handler dispatch, local private-processor request/ingress/handler/work/response, optional downstream-route wait, completion, and the source local-response-to-request gap. Current flow-generator and Kubernetes adapters require complete v2 telemetry when the existing diagnostic flag is enabled; ordinary runs omit it. The summary utility accepts both historical v1 and current v2 traces. Focused processor, forwarder, summary, flow-generator, adapter, and validation checks pass (76 tests), and the complete non-Chart suite passes (173 tests).

Normal-build trace `runs/ibg-experiment-20260721T202043Z.jsonl` completed 15 slots with both forwarding-path and cgroup diagnostics. Its 450 links are all `forwarding_path_v2`, all selected-forwarder slot deltas report zero throttling, all 24 replica Pods remained restart-free, and exact replay matches all 15 slots with zero belief or mathematical drift. All-slot per-flow pair cost is 44.24 ms mean and 73.80 ms p95. The final physical/pair/end-to-end means are 65.41/33.37/98.78 ms, with 2/15 SLA violations and realized utility 2973.26. Source local-response-to-outbound-request time is negligible at 0.10 ms mean. The dominant residual is source request start to target ASGI ingress at 13.48 ms/link mean (p95 34.55), followed by target ingress-to-handler dispatch at 2.97 ms (p95 9.45) and response return at 5.68 ms (p95 15.07). Same-worker and cross-worker link costs are 22.06 and 22.18 ms, so worker locality does not explain the variance. Private-processor request/admission/response delays show the same burst-time runtime variability but are inside the callee handler and are not deducted as pair cost.

`forwarding_path_v3` is implemented and retains every earlier aggregate while adding opt-in HTTP Core pool/connect/send/receive milestones. The summary accepts historical v1/v2 and the initial v3 `http_client_path_v1` naming, while the current runtime requires the clarified `http_client_path_v2` fields. Normal-build trace `runs/ibg-experiment-20260721T205120Z.jsonl` completed 14 slots and 420 complete v3 links. Exactly 418 links opened a TCP connection; pool wait averaged 2.63 ms (p95 7.80), connect 7.31 ms (p95 19.14), and request-to-target-ingress 13.23 ms (p95 30.29). Every inter-slot idle interval was 7.74--8.08 seconds, exceeding the then-default 5-second HTTPX and Uvicorn keep-alive windows. All-slot per-flow pair mean/p95 was 43.22/69.88 ms; final physical/pair/end-to-end means were 66.61/39.81/106.42 ms, with 6/15 violations and realized utility 2858.73. All cgroup throttle deltas were zero, and exact replay matched 14 slots with zero drift. Same- and cross-worker links both showed near-universal reconnects. The controlled matched 30-second A/B trace `runs/ibg-experiment-20260721T210935Z.jsonl` also completed 14 slots and 420 v3 links. It reduced new TCP connections to 243 and source-request-to-target-ingress mean to 11.38 ms, but its all-slot pair mean was still 42.19 ms/flow with an unstable upper tail. It ended at 0/15 final SLA violations with final physical/pair/end-to-end means 68.82/28.26/97.08 ms and realized utility 2998.76; cgroup deltas were zero, all Pods were restart-free, and exact replay had zero drift. This confirms the reconnect mechanism and partial benefit, not closure.

The next controlled no-controller probe warmed a fixed `stage-1-0 -> stage-2-0` public-forwarder route with 12 discarded requests, then issued three six-request and three fifteen-request simultaneous waves while retaining v3 telemetry. It is transient diagnostic evidence rather than a controller trace. Warmup reused 11/12 downstream connections and averaged 6.27 ms pair cost. All three six-request waves reused every connection; their means were 6.70, 9.82, and 5.38 ms (maximum 14.82 ms). The first fifteen-request wave still created 8/15 connections and averaged 13.54 ms (maximum 33.44 ms), with 4.29-ms mean connect time. The next two fifteen-request waves reused all 15 connections and fell to 9.44/7.59-ms means (16.87/11.41-ms maxima). Thus repeated reconnects explain the first-wave tail, but a smaller reused-connection residual remains across source pool wait, source-to-target ingress, target admission, and response return; no single boundary or resource mechanism is yet established.

A four-route placement matrix then repeated the discarded warmup and three six-/fifteen-request waves for same-worker `stage-1-0 -> stage-2-2` and `stage-1-1 -> stage-2-0`, and cross-worker `stage-1-0 -> stage-2-0` and `stage-1-1 -> stage-2-2`. Every second and third fifteen-request wave reused all 15 downstream connections. Their respective pair means were 9.43/8.36, 7.47/6.15, 8.52/11.21, and 7.83/13.05 ms. The largest fully reused sample was 29.07 ms on the last cross-worker wave, accompanied by pool/ingress/return means of 3.38/6.02/5.11 ms. Because both same- and cross-worker routes can be low or elevated, locality is not an explanatory variable.

The completed next diagnostic added correlated source/target public-forwarder PIDs and additive `forwarder_runtime_v1` data: active diagnostic handler/request counts, 5-ms event-loop scheduling-lag samples, and best-effort source socket identity. No single worker or socket was responsible: the earlier tail sample spread over 25 of 32 source identities, 25 of 32 target identities, and 62 of 211 worker pairs. The fresh normal-build exploratory controller trace `runs/ibg-experiment-20260727T105911Z.jsonl` completed 18 slots, reached equilibrium, and exact-replayed with zero drift; its 540 selected links all had complete runtime data. Link cost correlated 0.705 with source loop maximum lag, and p90-tail links averaged 40.41 ms source maximum lag versus 7.95 ms in the lower half. The correlation persists within fully reused connections, whereas active request counts, cgroup throttling, global host CPU/IO-pressure/load, Docker/kind indicators, and conntrack snapshots did not isolate a cause. This supports intermittent source public-forwarder scheduling/descheduling as a contributor, but not whether it originates in event-loop work or lower-level host/runtime scheduling. No mitigation was selected.

Gate: pending. The two-worker/1-CPU configuration and matched 30-second keep-alive setting have no OOM/restart, cgroup-throttling, or replay regression, but they have not established stable 15x8 forwarding behavior. The current diagnostics distinguish reconnect tails from an intermittent reused-connection scheduling contribution, but not source event-loop occupancy from OS/runtime descheduling. Do not select a runtime change until separately authorized, read-only per-worker scheduler evidence (for example, scheduler and context-switch deltas) clarifies that distinction. This does not authorize normalization, resource retuning, a different SLA/pair formula, coupled placement, host preflight, or another datapath.

### Phase 4 branch: control-plane metric and measurement

Status: complete. Overall Phase 4 is active for the remaining reporting curation.

The versioned `control_plane_v1` block records monotonic-wall and controller-CPU timing for discovery, admission/planning through route dispatch, and feedback processing after telemetry arrives. It reports their sum as active control time and records selected-route wait separately as data-plane execution time. HTTP application-payload bytes and message counts cover controller boundaries only: Kubernetes discovery, route command, selected telemetry, and reserved future belief exchange. Forwarder-to-forwarder route RPCs are excluded, and no wire-byte claim is made.

The separate `learning_signal_v1` block reports the selected-only logical learning footprint rather than the full telemetry envelope. Its canonical JSON projection contains only stage, flow, selected replica, assigned load, noisy learning signal, and likelihood vector. Physical processing and observation jitter remain diagnostic fields outside the projection. Exactly `flows * stages` records are required, so unselected replica count cannot inflate the metric. Logical payload bytes and mean bytes per selected hop are reported independently from the actual `selected_telemetry_rx` application-body bytes. This is not a wire-byte claim or a comparison with hypothetical raw telemetry.

Gate: complete. Deterministic tests prove component sums, byte/message accounting, monotonic timing, one route-command/telemetry exchange regardless of route hop count, exact selected-signal scaling, canonical footprint consistency, exclusion of diagnostic telemetry, and one-column-per-run `logical_learning_footprint.csv` export when the schema is complete. `scripts/control_plane_summary.py` validates both schemas and reports per-run median/p95 values while retaining compatibility with older `control_plane_v1` traces. Fresh final-code normal-build supported trace `runs/ibg-experiment-20260718T123226Z.jsonl` passed every Kernel live gate with 98.99% classification, 100% server-overshoot compliance, and exact 11-slot zero-drift replay. Every slot recorded nine selected learning signals; median logical footprint was 1,861 bytes, or 206.78 bytes per selected hop. The full suite passes with 138 tests. The implementation leaves solver, selection, selected-only signal, learning, pairwise deduction, SLA, equilibrium, and datapath behavior unchanged. Earlier supported control-plane trace `runs/ibg-experiment-20260718T115336Z.jsonl` and its five matching repeats remain valid `control_plane_v1` evidence but predate `learning_signal_v1`.

Gate: the requested evidence is traceable to committed code and identified run artifacts, its scope/units/limitations are clear, the authorized forwarding/reporting correction is validated and version-bounded, and no solver, learning, admission, or unapproved datapath behavior has changed.

Initial curation result: `EVIDENCE_SUMMARY.md` identifies the accepted calibration command and supported Kernel traces, separates modeled, localhost, live-cluster, and replay claims, and is opt-in-only. The Phase 2 synthetic calibration reproduces under current code. The historical Phase 3 trace still passes its live telemetry gate but predates the belief-retention change from 0.6 to 0.8. Three fresh supported-size retention-0.8 Kernel runs (seeds 2050--2052) replayed exactly across 31 slots and 279 placements/observations under the then-active 0.04 equilibrium threshold. Their live server-overshoot results vary: seed 2050 records 89.90%, while seeds 2051 and 2052 each record 100%; the 96.42% pooled rate is descriptive and does not replace the existing per-trace 95% scheduling gate. Exploratory 10- and 12-flow/5-replica runs reached equilibrium and replayed exactly, but do not extend the formal three-flow gate. The 12-flow CSV run exposes an unresolved user concern: the exported aggregate-utility series subtracts volatile live transport overhead and can decline despite improved learned selections and processing utility. Five additional live repeats of the same 12-flow command at seed 2050 reached equilibrium in 7--11 slots; first-to-final realized end-to-end utility increased in four traces and fell 5.78% in one because its transport penalty increased more than its realized processing utility. Thus Total Realized End-to-End Utility is an actual-outcome metric, but it is not a per-run monotonic-learning metric. Phase 4 now adds `realized_end_to_end_utility.csv` as a backward-compatible export of the existing trace metric while retaining `aggregate_utility.csv` unchanged, and—under explicit user authorization—recalibrates the active SLA threshold from 250 ms to 175 ms using the exploratory 12-flow latency distribution and restores the equilibrium stopping threshold to 0.04 after brief 0.03 and 0.037 settings. The paper/implementation audit found that the former request-overhead deduction was not the paper-defined consecutive-replica cost. The user authorized the narrow correction described below; historical traces keep their former semantics, and fresh live/replay evidence is required before making current-implementation empirical claims. Transport-inclusive outcome claims must remain distinct from learning-only claims.

Implemented Phase 4 reporting correction: preserve the exact decoupled solver and all selection mathematics, but replace generator-mediated independent hop execution with forwarding along the already-selected stage route. Record one correlated communication/RPC-cost measurement for each consecutive selected pair, deduct only those `K-1` edge costs in reported end-to-end latency and utility, and keep broad flow-generator ingress overhead as separate telemetry. This is post-placement execution/reporting work only; pairwise costs do not influence placement, and coupled IBG remains out of scope. The four post-audit hardening fixes are now implemented: current pair/ingress fields are required, pair Pod/endpoint metadata is correlated, pair sums must equal the deducted per-flow metric, and mixed historical/pairwise runs are rejected. The full suite passes with 114 tests. Fresh supported-size seed-2050 trace `runs/ibg-experiment-20260715T171429Z.jsonl`, collected from `./scripts/run_experiment.py --flow 3 --stage 3 --replica 5 --max-iterations 100`, reached strict-0.03 equilibrium in 23 slots; all 138 pair records passed the hardened reporting checks and all 23 slots replayed with zero mathematical drift. Under the restored strict-0.04 threshold, rerun `runs/ibg-experiment-20260715T173555Z.jsonl` ran all 100 permitted slots without equilibrium; its 600 pair records and 100-slot replay pass reporting/replay checks, but live classification was 79.11% versus the required 80% and server-overshoot tolerance was 82.56% versus the required 95%. Keep reporting/replay success separate from failed live statistical evidence. Phase 4 therefore remains in progress and neither new-schema trace is an accepted replacement for the historical live Kernel baseline.

Targeted diagnosis of `runs/ibg-experiment-20260715T173555Z.jsonl` localizes the failed live statistics and non-convergence to runtime timing added around early route-forwarding stages, not the solver, pair-cost deduction, or modeled state law. Reclassifying the 900 selected hops from their seeded modeled latencies yields 99.89% correct states, while classification from the measured processing signal is 79.11%. Of 157 server-overshoot failures, only 3 remained correctly classified; classification was 95.42% among the 743 hops that passed the overshoot check. The failure is route-position and concurrency dependent: stage 1/2/3 overshoot pass rates are 69.33%/80.00%/98.33%, and concurrency 1/2/3 rates are 92.68%/54.63%/33.33%. The first slot is cold and fails all nine overshoot checks, but failures persist through later slots, the two worker-node rates are close, Pods did not restart, and sampled cgroup counters show only isolated CPU-throttled periods with no stage correlation. In code, processing latency spans an `asyncio.sleep` and therefore includes coroutine wake-up delay; stage 1 and 2 Pods now also perform downstream HTTP client/forwarding work on the same Uvicorn event loop, whereas terminal stage 3 does not. This scheduling/event-loop delay shifts otherwise correct state-4 samples toward states 3 or 2 and keeps the selected good-replica beliefs oscillating. In 94 of 100 slots, one of stage 1 replicas 1/5 or stage 2 replica 3 was the largest belief mover; the run's smallest maximum per-entry change was 0.041, so no slot met strict `<0.04`. This is an evidence-backed localization, not authorization to tune the runtime or measurement model.

Keep the apparent late-iteration SLA concern tied to the correct run. The latest three-flow trace has zero violations at iteration 100 and zero in 97 of 100 slots. The current-schema 12-flow trace `runs/ibg-experiment-20260715T172332Z.jsonl` has five of twelve flows above 175 ms at iteration 100; each crosses only after adding 61--139 ms of pairwise link cost to processing. CSV column `212f1e` instead belongs to `runs/ibg-experiment-20260715T172851Z.jsonl`, which reached equilibrium at iteration 49 and ended with six violations; its CSV has 49 data rows, not 100. The 175 ms threshold was selected from historical request-overhead traces before the pairwise forwarding schema, so it is not yet a calibrated current-schema SLA acceptance boundary. Do not reinterpret the historical calibration or change the threshold without explicit authorization.

A like-for-like late-window comparison confirms that the forwarding architecture causes an SLA regression through processing-timer contamination, not higher link cost. In the final five slots of the two available pre-forwarding 12-flow/5-replica traces collected under the 175 ms rule, mean violations were 1.0 and 3.0, mean per-flow processing was 68.80 and 65.11 ms, and mean per-hop measured-minus-modeled overshoot was 0.87 and 1.20 ms. The two current pairwise traces record 5.4 and 5.0 mean violations, 87.84 and 88.06 ms processing, and 7.84 and 7.89 ms overshoot. Their link-cost means are lower, not higher, than the historical pair: 83.31/82.57 ms versus 89.33/103.02 ms. Current overshoot is concentrated at forwarding stages 1 and 2 (about 13 and 9 ms per hop) while terminal stage 3 remains about 1.2 ms. One historical run still ended with six violations, so the old behavior was not uniformly below four, but the late-window distribution shift is real. Treat the current forwarding implementation as reporting/replay-correct but not an accepted live processing/SLA implementation until a separately authorized correction isolates forwarding activity from the local processing measurement.

The authorized narrow forwarding-runtime correction is now implemented in the uncommitted Phase 4 worktree. Each replica Pod has a private processor (port 8081) and public forwarder (port 8080); the forwarder owns route I/O and pair telemetry, while the processor alone creates the selected signal and likelihood. Processor readiness warms the exact deterministic sampling path with a discarded sample, avoiding first-use runtime initialization in the measured signal without changing experiment samples. Focused isolation, pair-record, metadata, ingress, and schema tests plus the full suite pass (120 tests); Compose configuration and the local container smoke test also pass.

Fresh supported-size evidence from that worktree is `runs/ibg-experiment-20260715T182717Z.jsonl`, collected with `./scripts/run_experiment.py --flow 3 --stage 3 --replica 5 --max-iterations 100` in `kernel` mode at seed 2050. It reached strict `<0.04` equilibrium in 10 slots, has 90 selected hops and 60 pair records, passes the baseline validator with 98.89% categorical accuracy and 100% server-overshoot tolerance pass rate, and replays all ten slots with zero mathematical drift. This accepts the corrected route-forwarding runtime at the formal three-flow boundary. Earlier current-schema traces `171429`, `173555`, `181957`, and `182457` remain diagnostic historical evidence of reporting hardening, forwarding contamination, or incomplete warm-up; they must not be aggregated with this accepted run.

Phase 4 evidence/report curation remains in progress. The initial post-correction 12-flow attempt was deliberately interrupted and remains unusable. Its fresh replacement is `runs/ibg-experiment-20260715T183453Z.jsonl`, collected with `./scripts/run_experiment.py --flow 12 --stage 3 --replica 5 --max-iterations 100 --skip-build` in `kernel` mode at seed 2050. It reached equilibrium in eight slots; all 288 selected hops and 192 pair records replay with zero mathematical drift. Across its final five slots, mean processing latency is 69.99 ms/flow, pair cost 22.60 ms/flow, SLA violations 0.0/slot, mean processing overshoot 1.39 ms/hop, and categorical accuracy 98.89% (180 hops). This is a favorable exploratory comparison with the recorded pre-forwarding late-window values (65.11--68.80 ms/flow processing, 89.33--103.02 ms/flow link cost, 1.0--3.0 SLA violations/slot, and 0.87--1.20 ms/hop overshoot), but it does not extend the formal three-flow gate or authorize a threshold, likelihood, solver, or behavior change. The general validator reports `gate_passed=false` solely because 12 flows is outside the supported configuration and its incomplete load-one groups cannot satisfy that formal ordering check; classification, overshoot, pairwise integrity, schema consistency, equilibrium, and replay checks pass.

## Phase 5: Design and prove the DPDK/VPP integration boundary

Status: deferred by user until further notice. Do not work on this phase, run its preflight, or advance its gate without a new explicit authorization.

Suggested Codex reasoning: `xhigh` — DPDK resource ownership plus VPP topology, interfaces, lifecycle, routing, and failure handling must be specified before changing runtime workloads.

- Audit and reserve the required DPDK resources on the target host: NIC ownership, IOMMU/VFIO, hugepages, CPU/NUMA placement, container privileges, and Kubernetes device resources. Define a safe rollback procedure.
- Select and document the DPDK/VPP topology, its DPDK I/O backend, and the Linux-facing interfaces for this host (for example, VPP forwarding between the flow generator and selected FastAPI replicas). Keep Kubernetes Service discovery and FastAPI application endpoints intact.
- Define lifecycle, readiness, configuration, cleanup, and failure behavior for DPDK/VPP components and their Kubernetes resources. `kernel` mode must remain independently runnable.
- Specify how DPDK/VPP counters and per-hop transport timing are correlated to the existing slot/flow/stage/replica route identity without expanding the observation set. Add focused control-boundary tests before requiring a cluster deployment.

Current historical result: `dpdk_vpp_preflight_v1` is implemented through `scripts/dpdk_vpp_preflight.py` and `./scripts/run_experiment.py --datapath dpdk-vpp --dpdk-preflight-only`. It runs before cluster mutation, performs no host changes, and conservatively fails when resource ownership is ambiguous. On the current four-vCPU VMware host it reports missing VPP/DPDK tools, zero hugepages, no IOMMU groups, no VFIO device, and no separate safe PCI dataplane interface. `dpdk-vpp` is known to the launcher but deliberately excluded from the deployable runtime allow-list; Kernel remains the unchanged default. This dormant reference must be ignored until the user reopens DPDK/VPP work.

Gate: pending. A suitable target host must pass the preflight, and the DPDK/VPP topology, dedicated resource ownership, rollback, Kubernetes device exposure, readiness/failure behavior, and selected-route correlation must be approved before Phase 6. Do not use unsafe no-IOMMU VFIO, detach the sole management NIC, or present a Linux/VPP software fallback as the DPDK comparison.

## Phase 6: Implement the DPDK/VPP-backed FastAPI route

Status: deferred by user until further notice.

Suggested Codex reasoning: `xhigh` — this joins privileged DPDK resources, Kubernetes networking, VPP lifecycle, selected-route enforcement, and controller telemetry without authorization to alter IBG behavior.

- Add deployable DPDK/VPP resources and a `dpdk-vpp` traffic/telemetry adapter behind the existing complete-slot traffic port.
- Route each selected logical hop through the configured DPDK/VPP path and then to the same FastAPI `/process` contract. Do not replace FastAPI replicas with synthetic datapath observations.
- Preserve concurrent flows, sequential hops within a flow, route/identity validation, cleanup, and explicit failure rather than partial-success reporting.
- Emit DPDK/VPP-specific metadata only as supplemental telemetry, clearly separating it from FastAPI physical processing, noisy learning signal/likelihood, client latency, and concurrency fields.

Gate: a local and a small-cluster DPDK/VPP-mode run complete selected multi-hop routes, reject a DPDK/VPP or downstream failure cleanly, and retain complete per-hop correlation with no observations from idle replicas.

## Phase 7: Validate Kernel and DPDK/VPP modes against the IBG baseline

Status: deferred by user until further notice.

Status: planned.

Suggested Codex reasoning: `xhigh` — comparison must separate mathematical equivalence from genuine datapath timing and counter differences.

- Run controlled seeds at the supported three-flow/three-stage/five-replica configuration for simulation, `kernel`, and `dpdk-vpp` modes.
- Require replay parity for placements, utility grids, latency likelihoods, beliefs, utility, SLA, fairness, and equilibrium. Live runtime and datapath telemetry may differ and must be compared statistically rather than normalized away.
- Verify asymmetric/partial observation behavior directly: only selected replicas provide noisy learning observations in every mode.
- Publish a reproducible comparison command and a bounded evidence report; make no line-rate, hardware-offload, or DPDK claim from these results.

Gate: Kernel and DPDK/VPP modes are mathematically equivalent to the controlled simulation for the supported seeds, with explained and complete mode-specific telemetry and only the measured comparison claims supported by the hardware configuration.

## Next user-defined chapter: IBG-Hybrid

Status: not started; IBG-Exact is temporarily frozen as the reference baseline.

Do not infer an algorithm or begin implementation from the name alone. The user must first define the intended Hybrid policy, its relation to the exact solver, the required telemetry/information boundary, experiment dimensions, comparison metrics, and acceptance criteria. Until then, preserve the current exact solver, replay/evidence contracts, Kernel runtime, and all outcome/learning semantics unchanged.

The preceding status records the earlier handoff and is superseded by the
authorized roadmap below. IBG-Exact remains frozen.

## IBG-Hybrid Phase 0: Freeze the paper-aligned contract

Status: planned.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- Characterize the old `IBG_Hybrid/` revision without accepting it as target
  behavior.
- Record a paper/old-code/target matrix covering action shape, budget,
  feasibility, utility, link coupling, pruning, lookahead, Monte Carlo,
  learning, output, and infrastructure.
- Resolve the open Hybrid decisions recorded in `DECISIONS.md`.
- Add fixtures demonstrating each material mismatch.
- Define deterministic tie-breaking, seed ownership, and trace provenance.

Gate: every Hybrid formula, constraint, state transition, and algorithm knob
has one testable definition.

## IBG-Hybrid Phase 1: Establish the package and shared Exact boundary

Status: pending Phase 0.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- Make Hybrid modules import-safe and remove import-time experiments.
- Add complete-route, global-load, feasibility, configuration, and solver
  result types.
- Reuse Exact latency, learning, outcome, adapter, and measurement
  implementations instead of maintaining divergent copies.
- Add a tiny exhaustive coupled oracle for tests only.
- Run the Exact regression suite unchanged.

Gate: pure Hybrid models and small exhaustive fixtures pass with no Exact
regression.

## IBG-Hybrid Phase 2: Coupled feasibility and candidate pruning

Status: pending Phase 1.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- Enumerate complete routes with exactly one replica from every stage.
- Enforce Ready availability and approved budget/node-capacity constraints.
- Score routes from beliefs, expected processing utility, and known
  consecutive-link metadata without reading hidden states.
- Implement deterministic greedy base selection and paper-aligned pruning
  inside one `IBGHybridPolicy`.
- Record pre-pruning, post-pruning, feasible, and rejected candidate counts.

Gate: pruning returns only complete feasible routes and retains the expected
best routes in controlled exhaustive fixtures.

## IBG-Hybrid Phase 3: Deterministic limited lookahead

Status: pending Phase 2; this is the critical algorithm phase.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- Use one slot-wide sequential flow order.
- For each focal route, copy the global load state and simulate the next `D`
  flows with the accepted base policy.
- Score the route using the Phase 0 continuation-value definition.
- Prevent branch-state leakage, off-by-one depth, and immediate-value double
  counting.
- Start with paper-oriented `D=2` after its exact meaning is fixed.
- Compare tractable cases with the exhaustive coupled oracle.
- Benchmark the pure solver at 20 flows, 3 stages, and 10 replicas without
  turning observed runtime into a real-time claim.

Gate: lookahead is deterministic, strategically non-myopic in a targeted
congestion fixture, and completes the initial configuration within a measured
and recorded resource envelope.

## IBG-Hybrid Phase 4: Seeded Monte Carlo in the unified policy

Status: pending Phase 3.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- Add Monte Carlo as an internal Hybrid rollout path, not a separate public
  algorithm.
- Use the accepted continuation kernel and request/run-stable seeds.
- Start with `S=50` as a paper-derived configuration, not an accuracy claim.
- Support deterministic forcing of every internal path for tests.
- Record sample count, seed provenance, candidate evaluations, and activation
  reason.

Gate: fixed seeds reproduce actions and rollout values, controlled
sample-count checks stabilize, and selected-only learning is preserved.

## IBG-Hybrid Phase 5: Complete simulation slot

Status: pending Phase 4.

Suggested model: GPT-5 Codex. Suggested reasoning level: high.

- Add a Hybrid slot runner over shared adapter and result contracts.
- Select routes sequentially and execute all committed routes concurrently
  after placement.
- Apply shared physical/observation separation and belief updates.
- Preserve physical, pair, end-to-end, outcome, SLA, fairness, control,
  learning-footprint, and equilibrium metrics.
- Print only compact metrics per slot and retain complete structured traces.
- Run seeded multi-slot 20x3x10 simulations.

Gate: each slot has 20 complete routes and 60 selected observations, and the
run is reproducible without schema or Exact regression.

## IBG-Hybrid Phase 6: Reuse Kernel Kubernetes/container architecture

Status: pending Phase 5.

Suggested model: GPT-5 Codex. Suggested reasoning level: high.

- Add a Hybrid controller/solver selection boundary.
- Package Hybrid without replacing the Exact entry point.
- Reuse the existing private processor, public forwarder, flow generator,
  discovery, RBAC, profiles, resources, and keep-alive settings.
- Deploy 3 stages with 10 replicas each and run 20 complete routes per slot.
- Add Hybrid simulation/replay validation from captured selected signals and
  pair telemetry.

Gate: controlled Hybrid simulation and Kernel replay agree on placements,
beliefs, utility, SLA, fairness, and equilibrium; Kubernetes-only telemetry
remains separately reported.

## IBG-Hybrid Phase 7: Audit diagnosis-script compatibility

Status: pending the main lookahead and baseline Kernel implementation.

Suggested model: GPT-5 Codex. Suggested reasoning level: high.

- Verify algorithm-neutral forwarding-path, forwarder-cgroup, control-plane,
  and learning-footprint diagnostics.
- Extend replay validators for coupled complete routes.
- Extend solver-resource reporting with Hybrid candidate, rollout, and sample
  counts while keeping memory bytes separate from algorithmic counts.
- Reject Exact-specific assumptions explicitly where sharing would mislead.
- Keep diagnostic instrumentation opt-in and behavior-neutral.

Gate: every relevant diagnostic is proven reusable, deliberately extended, or
rejected with a focused test and documented reason.

## IBG-Hybrid Phase 8: Validate the initial target

Status: pending Phase 7.

Suggested model: GPT-5 Codex. Suggested reasoning level: high.

- Run controlled seeds at 20x3x10.
- Measure candidate reduction, decision runtime, CPU/RSS, rollout work,
  utility, SLA, fairness, convergence, and Good/Excellent selection share.
- Compare matched internal ablations: pruning/greedy, deterministic lookahead,
  and Monte-Carlo-assisted Hybrid.
- Use the exhaustive coupled oracle only at tractable sizes.
- Record trace, seed, image, configuration, and schema provenance.

Gate: the initial target has reproducible correctness and resource evidence
without unsupported MILP-proximity, 100-ms, or datapath claims.

## IBG-Hybrid Phase 9: Deferred robustness additions

Status: deferred.

Suggested model: GPT-5 Codex. Suggested reasoning level: high.

- Reuse `netem_v1` only after the baseline Hybrid Kernel trace and replay are
  stable.
- Later assess availability churn and uncertainty-trigger behavior.
- Keep packet loss, retries, missing observations, DPDK/VPP, and new
  rejection/admission policies outside scope until explicitly authorized.

## IBG-Hybrid Phase 10: Optional bandit-based adaptation

Status: optional and deferred until the core Hybrid policy is validated.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- Evaluate the paper's contextual-bandit adaptation separately from the
  required pruning/lookahead/Monte-Carlo pipeline.
- Define whether UCB or Thompson Sampling is a low-overhead fallback, a
  rollout policy, or both; do not infer either role from the paper alone.
- Preserve the same selected-only observation, latency/learning, action,
  utility, SLA, and trace contracts.
- Compare against the validated core Hybrid policy under matched seeds,
  dimensions, resource limits, and information boundaries.

Gate: deterministic fixtures, matched evidence, and complete telemetry show
the bandit role is compatible with the Hybrid contract without redefining the
core policy or its learning signal.

## IBG-Hybrid budget-action correction

The preceding Hybrid phases initially described a complete route containing
all three stages. The user has clarified the active intended budget model:
each flow has `L=2`, chooses exactly two replicas from two distinct stages out
of three, and bypasses the unselected stage entirely. This correction takes
precedence for every Hybrid phase.

`IBG_Hybrid/budgeted.py` records this as
`HYBRID_STAGE_BUDGET = 2`. Changing the budget later is intentionally a code
change and requires generalizing the current two-stage planner, embedding,
traffic, replay, and test contracts.

Accordingly, Phase 0 must define two-stage action ordering, utility, pair
cost, SLA interpretation, and feasibility. Phases 2--5 must select exactly
two stage/replica pairs per flow and expect 40 selected observations per
20-flow slot, not 60. Phase 6 must add a versioned Hybrid traffic-route
contract for selected two-stage chains that can be noncontiguous or begin at
a stage other than stage 1; it may reuse the processor/forwarder runtime but
cannot reuse the Exact contiguous-stage validation unchanged. Phase 7 must
audit affected replay and diagnostic schemas under this action shape.

## Future coupled-IBG track

Status: awaiting user requirements; not scheduled.

Coupled IBG is a separate mathematical and experimental scope. It must begin with an explicit problem definition, state/action and utility changes, observation and learning semantics, baselines, and acceptance fixtures. It must not be introduced as a datapath-mode option or silently alter the validated decoupled solver.

## IBG-Hybrid Phase 1 implementation result

Status: complete as the explicitly authorized package foundation. The
unresolved Phase 0 production-formula decisions still gate Phase 2.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- `IBG_Hybrid/` is now an import-safe package; importing all Hybrid modules
  produces no output or result files and no longer executes the old
  experiment loop.
- Pure contracts cover canonical two-stage actions, the 20x3x10 default
  configuration, immutable global loads, explicit feasibility, and solver
  results.
- Every active boundary validates the single `L=2` source constant. A skipped
  stage receives no load increment.
- A hard-bounded exhaustive coupled oracle supports only tiny fixtures,
  caller-injected objective/feasibility semantics, and deterministic
  canonical ties. It refuses the production target.
- Ten focused Hybrid tests pass. Twenty-three unchanged Exact
  characterization, latency-model, and runner regression tests also pass.

Gate result: the Phase 1 package/models/oracle gate passes without changing
any file under `IBG/`. Before Phase 2 starts, close the Phase 0 meanings for
production feasibility, route scoring/link cost, pruning, continuation value,
lookahead depth, Monte Carlo activation/kernel, and seed ownership.

## IBG-Hybrid Phase 0 completion result

Status: complete. Phase 1 remains complete and was not repeated.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

The accepted versioned contract is implemented as pure constants,
validation, and characterization helpers in
`IBG_Hybrid/phase0_contract.py`:

- Cardinality is exactly `L=2`; feasibility means canonical action shape,
  Ready selected replicas, declared assigned-flow capacity, and available
  known pair-link metadata.
- `C=5` counts replicas per stage. The active 3-stage/2-selected-stage target
  has at most 75 complete actions after pruning.
- Pruning rank is belief/load-aware expected stage utility at the projected
  immediate load, with lowest-replica-ID ties.
- Complete route score includes two selected stage values and one configured
  directed pair cost.
- `D=2` counts future arrivals after the focal action. Deterministic rollout
  simulates joint greedy continuation and evaluates focal utility once at
  projected loads.
- MC uses `S=50`, epsilon `0.10`, the same focal objective, local
  candidate/sample seeds, and no bandit kernel.
- Internal activation is total and ordered: normalized entropy `>=0.75`
  selects MC; otherwise contention `>=0.70` or high priority selects
  lookahead; all other decisions use pruned greedy.
- Flow-order and MC seed ownership/provenance are independently versioned.
- Existing Pod scheduling resource requests are not per-flow admission
  charges. A future CPU/memory/bandwidth-per-flow model requires a new
  contract and is not silently enabled.

Nine Phase 0 characterization tests cover the parameter/units contract,
per-stage `C`, action-count bound, deterministic pruning ties, `D`, activation
precedence and inputs, feasibility, focal-only projected-load scoring, and
seed stability/isolation.

Gate result: every previously listed Phase 0 ambiguity now has one accepted
testable meaning. Phase 2 may implement coupled feasibility, per-stage
candidate scoring/pruning, and complete `L=2` action enumeration against this
contract. Production lookahead and Monte Carlo remain Phases 3 and 4.

## IBG-Hybrid Phase 2 implementation result

Status: complete. Phase 0 and Phase 1 remain complete and were not repeated.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- `IBGHybridPolicy` now supplies the pure production-facing feasibility,
  per-stage pruning, complete-action enumeration/scoring, and deterministic
  joint-greedy boundary.
- The policy accepts global loads, `ReplicaAdmission`, belief vectors, and
  configured directed link metadata only. True state, legacy replica cost,
  and measured post-placement pair residuals are not policy inputs.
- Hybrid belief expectation reuses
  `IBG.latency_model.expected_state_utility`; no Exact implementation or file
  was copied or changed.
- Replica-local Phase 0 admission feasibility is reused before pruning.
  Complete Phase 0 feasibility is reused for canonical action shape,
  Ready/capacity, and directed pair-link validation.
- `C=5` retains replicas independently per stage by belief/load-aware score
  at `current_load + 1`. All retained `L=2` combinations are enumerated, with
  a hard assertion against exceeding the Phase 0 75-action bound.
- Every feasible pruned action carries its two stage utilities, configured
  planning link cost, and final objective. Strict improvement over canonical
  enumeration implements deterministic complete-action ties.
- Candidate accounting includes available/local-feasible replicas,
  structural and pre-pruning-feasible actions, retained identities,
  total/feasible pruned actions, and rejection-reason counts.
- Seven focused Phase 2 fixtures cover Ready/capacity/link rejection,
  belief-only/no-hidden-state access, per-stage ranking and ties, the 75-action
  target bound, link-aware joint choice, canonical joint ties, and agreement
  with the tiny oracle on a tractable one-flow case.

Gate result: the Phase 2 pruning boundary returns only complete feasible
`L=2` actions, retains the controlled expected candidates, and selects the
same immediate optimum as the tiny exhaustive oracle when `C` does not bind.
The combined Phase 0/1/2 Hybrid suite and relevant unchanged Exact
characterization/latency/runner regressions pass with 49 tests. Hybrid
byte-compilation and `git diff --check` also pass. Phase 3 is next:
deterministic `D=2` focal-value lookahead over this unchanged greedy base.

## IBG-Hybrid Phase 3 implementation result

Status: complete. Phases 0, 1, and 2 remain complete and were not repeated.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- `IBGHybridPolicy.select_lookahead` evaluates every root-feasible pruned
  focal action on an independent immutable branch.
- Each branch commits its focal action once, clamps `D=2` to the actual later
  flows in the configured slot, and reuses unchanged `select_greedy` at every
  updated continuation state.
- Branch value is exactly the focal two-stage expected utility at projected
  final loads minus its configured directed link cost once. Immediate value
  and continuation-player welfare are not added.
- Canonical Phase 2 ordering plus strict improvement provides deterministic
  continuation and focal ties. Dead-end continuation branches are recorded
  and excluded without leaking state into another branch.
- Lookahead detail retains the focal action, state after focal, projected
  final state, continuation actions, requested/effective depth, focal value,
  root accounting, and complete Phase 2 decision/accounting per continuation.
  The returned solver state commits only the selected focal action.
- Thirteen focused Phase 3 tests cover `D=0/1/2`, end-of-slot clamping,
  commit-once behavior, no immediate double count, no social-welfare term,
  projected-load valuation, branch/input isolation, updated-state Phase 2
  reuse, canonical ties, a deliberately non-myopic congestion choice,
  tractable D=0 oracle agreement, continuation dead ends, and deterministic
  completion at 20x3x10.

Local pure-solver evidence on 2026-07-29 used the default 20-flow, 3-stage,
10-replica configuration, uniform state-4 beliefs, zero configured planning
link costs, Ready replicas, assigned-flow capacity 20, `C=5`, and `D=2`.
Five same-process local calls evaluated 75 focal candidates and two greedy
continuations per completed branch in 1.356--1.558 seconds, mean 1.433
seconds. All five returned the identical canonical
`(stage 1, replica 1) -> (stage 2, replica 1)` focal action and objective
172.813750354781. This is local solver evidence only, not a real-time,
Kubernetes, or end-to-end guarantee.

Gate result: the combined Phase 0/1/2/3 Hybrid tests plus the relevant
unchanged Exact characterization, latency-model, and runner tests pass with
62 tests. Hybrid compilation, `git diff --check`, the empty `IBG/` diff
check, and the no-Hybrid-Markdown check pass. Phase 4 is next: seeded Monte
Carlo inside this same public policy. Slot orchestration and infrastructure
remain later phases.

## IBG-Hybrid Phase 4 implementation result

Status: complete. Phases 0--3 remain complete and were not repeated.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- `IBGHybridPolicy.select_monte_carlo` now evaluates every root-feasible
  pruned focal candidate using exactly `S=50` independently derived local
  rollout streams by default.
- Each sample commits its focal action once, clamps `D=2` to remaining flows,
  and recomputes Phase 2 feasibility, pruning, scoring, and accounting at
  every continuation state.
- Each continuation is canonical Phase 2 greedy with probability `0.90` or a
  seeded uniform draw over the same current feasible-pruned action tuple with
  probability `0.10`.
- Every completed sample evaluates the focal route once at its projected
  final loads and deducts its planning link once. Candidate means include
  completed focal values only; sample and all-candidate dead ends have
  explicit deterministic failure records.
- Result detail retains decision-level seed provenance, root accounting,
  per-candidate sample counts/means, per-sample seeds/states/values, and
  per-step greedy/exploration mode, current feasible actions, Phase 2
  accounting, selected action, and resulting state.
- Eighteen focused Phase 4 tests cover authoritative `S=50`, `D=0/1/2` and
  clamping, commit-once/focal-only/link-once valuation, epsilon-zero greedy,
  epsilon-one seeded uniform exploration, feasible-pruned membership, seed
  stability/isolation, repeated-call determinism, state/input isolation,
  updated-state Phase 2 reuse, canonical ties, partial/all rollout failures,
  Phase 3 agreement at epsilon zero, D=0 oracle agreement, and the production
  20x3x10 boundary.

Local pure-solver evidence on 2026-07-29 used 20 flows, 3 stages, 10 replicas
per stage, `C=5`, `D=2`, `S=50`, epsilon `0.10`, root seed 2050, slot 4,
decision position 2, flow 17, uniform state-4 beliefs, zero planning-link
costs, Ready replicas, and assigned-flow capacity 20. The quiet production
test completed in 68.03 seconds. A second instrumented call completed in
68.556997 seconds and returned the identical canonical
`(stage 1, replica 1) -> (stage 2, replica 1)` action with mean focal objective
172.813750354781. It evaluated 75 focal candidates and 3,750 completed
samples with zero failures; 702 of 7,500 continuation steps were seeded
exploration draws. These timings are local pure-solver evidence, not a
real-time, Kubernetes, or end-to-end guarantee.

Gate result: the Phase 0/1/2/3/4 Hybrid tests plus relevant unchanged Exact
characterization, latency-model, and runner regressions pass with 80 tests.
Hybrid compilation, `git diff --check`, the empty `IBG/` diff check, and the
no-Hybrid-Markdown check pass. Phase 5 is next: complete Hybrid simulation
slot orchestration, learning, metrics, and compact per-slot output. Automatic
policy-path activation can be integrated there; infrastructure remains Phase
6.

## IBG-Hybrid Phase 5 implementation result

Status: complete as a pure simulation-slot boundary. Phases 0--4 remain
unchanged.

Suggested model: GPT-5 Codex. Suggested reasoning level: high.

- Immutable Hybrid-only contracts now cover slot input, flows/priorities,
  simulation replica profiles, planning and measured pair values, committed
  placements, selected observations, metrics, and complete slot results.
- `run_hybrid_slot` derives one slot-wide flow permutation, evaluates
  activation from the current feasible pruned pool, applies the authoritative
  Monte-Carlo/lookahead/greedy precedence, calls the corresponding completed
  policy method, and commits only its focal action.
- The pure in-process adapter runs only after every placement. It uses
  independent physical and observation seeds, delegates both jitter laws and
  the exact convolved likelihood to frozen Exact code, conditions every
  selected sample on final assigned load, and returns exactly two
  observations plus one measured selected-pair outcome per flow.
- Complete selected observations are validated before one batch call to the
  unchanged Exact selected-only learner. Retention remains `0.8`; unselected
  and skipped replicas remain unchanged.
- Metrics retain expected utility, physical-only realized utility, physical
  and measured-pair latency, raw end-to-end latency/reference utility,
  physical-only `110`-ms SLA, Jain fairness, monotonic slot runtime, maximum
  belief change, and strict `<0.033` equilibrium. Planning and measured pair
  values remain separate.
- The public runner is silent and in-memory. The explicit wrapper and module
  entry point emit exactly one metrics line after success and write no
  CSV/pickle or other result file.
- Twenty-two focused Phase 5 tests cover seed/order isolation, all activation
  paths and precedence, real focal-only load changes, bypass semantics,
  final-load selected observations, exact physical/observation separation,
  Exact learning/retention/utility/SLA/fairness/equilibrium reuse, planning
  versus measured pairs, repeatability, multi-slot belief retention, explicit
  failures, import/output safety, and the 20x3x10 boundary.

Local pure-slot evidence on 2026-07-29 used root seed 2050, slot 1, 20 flows,
3 stages, 10 replicas per stage, `L=2`, `C=5`, `D=2`, `S=50`, epsilon `0.10`,
Ready capacity 20, and an explicit common low-entropy belief
`(0.01,0.01,0.01,0.97)`. All 20 decisions correctly activated greedy and the
slot completed in 0.857269 seconds with 20 actions, 40 observations, 20
measured pairs, and 40 final assignments. Aggregate expected utility was
3382.319661; physical-only realized utility was 2701.635551; total physical,
measured-pair, and raw end-to-end latency were 1258.364449, 30.8, and
1289.164449 ms. Raw physical-plus-pair reference utility was 2670.835551,
physical-only SLA violations were zero, Jain fairness was
0.9999997995824625, maximum belief change was 0.198, and the first slot was
not at equilibrium. This is local pure-Python evidence, not a real-time or
Kubernetes guarantee.

The separate uniform-initial-belief default attempt correctly activated full
Monte Carlo and remained non-terminal when the local command session reached
its 1,000-second execution lifetime. It is not reported as a completed
runtime result. No sample/depth/candidate reduction, shared RNG, stale
candidate pool, or cache was introduced.

Gate result: the final combined command passed 116 tests in 78.02 seconds:
79 Phase 0--5 Hybrid tests and 37 relevant unchanged Exact characterization,
latency, runner, adapter/learning, and learning-footprint regressions. Hybrid
and Phase 5 test compilation, silent import, `git diff --check`, the empty
`IBG/` diff, and the no-Hybrid-Markdown check pass. Phase 6 is next:
Kubernetes/container reuse and the versioned two-selected-stage traffic
extension. Diagnostics, netem, DPDK/VPP, and bandit work remain deferred.

## IBG-Hybrid activation-correction interlude (next)

Before Phase 6, correct Phase 5 automatic policy activation to match the
paper-validated intended operating mode. Add immutable slot-level
uncertainty-event metadata, default false. A normal uniform-belief startup
must not activate Monte Carlo solely because entropy is high. MC remains
`S=50` and is selected only when an explicit uncertainty event and entropy
`>= 0.75` coexist; lookahead remains the contention/high-priority path and
greedy remains normal default placement.

Acceptance requires focused tests for no-event uniform startup, event-driven
high-entropy MC precedence, event-driven low-entropy fallback, unchanged
lookahead/greedy conditions, deterministic provenance, and a completed
default 20x3x10 slot runtime. Existing pruning, lookahead, Monte Carlo, and
slot execution mathematics must not be altered. Then continue to Phase 6.

### Revised acceptance for the activation-correction interlude

The interlude must also correct the normal path: a default 20x3x10
IBG-Hybrid slot must run the existing pruned `D=2` lookahead method for every
feasible focal flow, rather than greedy selection. Its future-flow simulation
continues to use the unchanged Phase 2 joint-greedy boundary. Only the last
one or two flows may have their effective depth clamped by the number of
remaining arrivals. The low-contention greedy commit described by the paper
is deferred as a separately selected fast-path variant.

Update focused tests and slot provenance to establish default-lookahead
behavior, while retaining event-driven high-entropy Monte Carlo and all
existing `L/C/D/S/epsilon` policy-method semantics. This revised interlude
must complete before Phase 6.

## IBG-Hybrid core-lookahead correction (immediate next task)

Complete the normal Hybrid algorithm before any further Monte Carlo work.
Make the slot runner select the existing pruned `D=2` lookahead method for
every feasible focal flow by default; greedy remains only the continuation
policy inside those lookahead branches. Preserve `L=2`, `C=5`, existing
lookahead semantics, final-load focal valuation, selected-only learning, and
all Exact reuse. Establish completed default 20x3x10 slot evidence without
calling Monte Carlo.

## IBG-Hybrid Monte-Carlo redesign (later, separate phase)

After the core-lookahead correction is accepted, assess and redesign the MC
path as a production-scalable optional fallback. The current exhaustive
per-focal `75 x 50` rollout implementation is retained as historical
correctness work but is not automatically reachable. Define the scalable MC
budget/selection/parallelism semantics explicitly, implement them only after
approval, and measure the resulting 20x3x10 behavior. Do not quietly weaken
the current method or present its existing multi-minute behavior as adequate.

## IBG-Hybrid core-lookahead correction result

Status: complete.

The runner now uses `C=5` pruning followed by the existing `D=2`
deterministic lookahead for all 20 focal decisions. Automatic greedy and MC
selection are removed. The final two decisions clamp to depths 1 and 0;
projected continuations never enter real loads. The policy reuses immutable
structural actions and memoizes the pure belief/load expected-utility law
without changing Phase 2--4 results or accounting.

The uniform-belief default 20x3x10 slot completed three deterministic local
runs in 4.670068, 3.950284, and 4.080329 seconds (mean 4.233560 seconds).
Every run used 20 lookahead decisions, produced 20 focal actions and 40
selected observations, and committed 40 replica assignments. This is local
pure-Python evidence, not the paper's claimed millisecond runtime or a
real-time/Kubernetes guarantee.

All 80 Phase 0--5 Hybrid tests pass in 18.61 seconds, including the retained
explicit MC correctness tests. The 37 relevant unchanged Exact
characterization, latency, runner, adapter, and learning-signal regressions
pass separately. The next algorithm task is the explicitly separate
Monte-Carlo redesign; Phase 6 infrastructure remains after that decision.

### User-selected `D=3` check

The active default depth is currently `D=3` for manual Hybrid inspection.
Revalidate the core 20x3x10 path at this depth before treating the earlier
`D=2` measurement as representative. MC remains disabled from automatic
execution.

## Professor-authorized MC redesign gate

Replace the historical exhaustive-root MC production intent with the
MCTS-inspired pipeline directed by the user's professor: after feasible
`C=5` pruning, select canonical top `Q=10` complete root candidates by their
current joint score; for each, run `S=50` seeded simulations; approximate all
future flows with greedy rather than lookahead; use active `D=3` only as the
number of future greedy placements per simulation. Compare the bounded
top-`Q` result to the historical exhaustive method on small fixtures, retain
full seed/accounting provenance, and benchmark the 20x3x10 one-decision
boundary. Bandit is explicitly excluded. Automatic MC activation remains
deferred after this gate.

### Depth restoration

The temporary `D=3` manual check is complete. The active default is restored
to `D=2` under contract v4 before the professor-authorized top-`Q` MC redesign
proceeds.

## Active workstream: coupled/budgeted MILP baseline

IBG-Hybrid and its Monte Carlo redesign are temporarily paused. Their code,
tests, contracts, and preceding roadmap history remain preserved. The phases
below are the active ordered plan; they do not authorize changes to `IBG/` or
`IBG_Hybrid/`.

The initial default MILP profile is 15 flows, 3 stages, 10 replicas per stage (30 total),
and exactly `L=2` selected stages per flow. The initial three-stage profile
bypasses its third stage; a `K`-stage run bypasses `K-2` stages. MILP
is the centralized perfect-state whole-slot social-welfare baseline for this
same coupled/budgeted problem.

## MILP Phase 0: Freeze the formulation and characterize the prototype

Status: next.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- Turn the paper, the user-selected `L=2` action, and the old `MILP/` code
  into one versioned formulation contract.
- Write deterministic characterization tests that expose import-time side
  effects, the inactive budgeted path, 30-per-stage versus 30-total mismatch,
  ignored caller budget/hard-coded `B=20`, arbitrary skipping, missing link
  and admission constraints, obsolete utility/learning, global RNG mutation,
  and incomplete solver-status reporting.
- Fix the runtime-configurable mathematical indices and units: variable `N`,
  `K`, and `M_k`, with initial default `N=15`, `K=3`, `M_k=10`, total
  `M=30`; exact cardinality `L=2`; assigned-flow capacity; milliseconds; and
  utility units.
- Specify the centralized final-load welfare objective, exact selected-pair
  link deduction, deterministic symmetry/tie expectations, infeasibility
  behavior, and perfect-state information boundary.
- Decide and record solver backends/dependencies. Keep the model
  backend-neutral; record that paper-runtime replication requires Gurobi 10.0
  while an available open solver may support local correctness tests.

Gate: the complete MILP variable set, objective, constraints, information
boundary, status semantics, and every old-code mismatch have deterministic,
reviewable definitions before solver replacement begins.

## MILP Phase 1: Establish an import-safe package and test oracle

Status: pending MILP Phase 0.

Suggested model: GPT-5 Codex. Suggested reasoning level: high.

- Remove import-time experiments, prints, global seeding, and file writes from
  `MILP/`; add package-relative imports and a guarded executable entry point.
- Expose validated runtime dimensions through `--flow`, `--stage`, and
  `--replica`; keep the initial `15x3x10` values as defaults, not limits.
- Expose the independently validated `--cutoff SECONDS` option on that entry
  point without changing or silently clamping the requested duration.
- Add immutable MILP configuration, replica/admission, directed-link, action,
  placement, solver-status, objective-breakdown, and result contracts.
- Add explicit `L=2` validation and reject unsupported budgets rather than
  silently changing the action shape.
- Add a tiny exhaustive centralized social-welfare oracle for tractable
  fixtures only; it must not be used at 15x3x10.
- Pin or clearly gate the chosen solver dependency and fail with a helpful
  import/configuration error when it is unavailable.

Gate: imports are silent and side-effect free; tiny valid/infeasible cases,
canonical actions, skipped-stage behavior, and solver-result contracts pass
without modifying Exact or Hybrid.

## MILP Phase 2: Implement the correct pure coupled MILP

Status: pending MILP Phase 1; this is the critical baseline phase.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- Build binary per-flow stage/replica placement variables, selected-stage
  variables, final replica-load/count selectors, and linearized directed
  selected-pair variables.
- Enforce exactly two stages and one replica per selected stage for every
  flow, with no bypassed-stage load.
- Enforce Ready availability, replica assigned-flow capacity, valid identity,
  and complete planning-link metadata.
- Precompute known-state expected stage utility for every replica/final-load
  pair using the frozen physical latency and linear utility concepts.
- Maximize total final-load stage welfare minus one configured link cost per
  flow. Preserve stage and link objective components separately.
- Validate the linearization, final loads, objective reconstruction,
  deterministic extraction, infeasibility, and optimum against the tiny
  exhaustive oracle.
- Return proven-optimal, time-limit, feasible-incumbent, infeasible, and
  solver-error states explicitly with bound/gap/runtime provenance.

Gate: controlled tractable fixtures agree exactly with exhaustive centralized
welfare, every placement is valid `L=2`, and no result is called optimal
without proof.

## MILP Phase 3: Add a pure simulation-slot and common metrics

Status: pending MILP Phase 2.

Suggested model: GPT-5 Codex. Suggested reasoning level: high.

- Add an import-safe in-memory slot runner that calls the pure MILP solver and
  then executes only its committed two-hop routes through an adapter.
- Reuse Exact physical and observation jitter generation, final-load
  conditioning, outcome/SLA, Jain fairness, timing, and result concepts
  without modifying `IBG/`.
- Keep perfect true state confined to MILP input and the simulation generator.
  Selected observations may be recorded for matched telemetry but must not
  update or steer MILP placement.
- Require exactly 15 actions, 30 selected observations, and 15 measured-pair
  outcomes at the initial 15x3x10 target; skipped and unselected replicas emit
  nothing.
- Print at most one compact metrics line per completed slot and retain the
  complete solver/objective/status/result structure in memory. Do not write
  CSV/pickle files in this phase.

Gate: a seeded pure slot reconstructs the solver objective, preserves
planning-versus-measured latency separation, and reports common physical-only
110-ms SLA and fairness metrics with no belief-equilibrium loop.

## MILP Phase 4: Validate optimality and scale

Status: pending MILP Phase 3.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- Run deterministic small cases against the exhaustive oracle and establish
  solver-backend parity where more than one backend is available.
- Measure build time, solve time, total slot time, variable/constraint counts,
  incumbent, best bound, gap, status, and memory at increasing small sizes.
- Run the paper-scale 15x3x10, `L=2` boundary with an explicit time limit and
  report whether optimality was proven. Do not turn a feasible incumbent into
  an “optimal” result.

Gate: the supported baseline size, backend/version, optimality evidence, and
scalability limitations are reproducible and honestly bounded.

## MILP Phase 5: Reuse the Kernel container/Kubernetes architecture

Status: pending MILP Phase 4.

Suggested model: GPT-5 Codex. Suggested reasoning level: high.

- Add a MILP controller entry point without replacing the frozen Exact or
  paused Hybrid entry points.
- Reuse the existing Ready discovery, profiles, RBAC, private processor,
  public route forwarder, flow generator, resource settings, and keep-alive
  configuration through adapters.
- Add a MILP-side versioned two-selected-stage route contract compatible with
  Hybrid's action shape, including noncontiguous selected stages and one
  correlated selected pair per flow. The frozen Exact flow generator does not
  already support this route shape and must not be silently reinterpreted.
- Solve all placements before traffic, execute the 15 selected two-hop routes
  concurrently, and retain final-load/identity validation.
- Keep true-state oracle inputs controller-private and clearly mark the MILP
  baseline as centralized/clairvoyant.

Gate: simulation and Kernel execution use identical MILP inputs/placements
and agree on deterministic solver outputs and replayed mathematical metrics;
runtime-only telemetry remains separate.

## MILP Phase 6: Replay and diagnostic compatibility

Status: pending MILP Phase 5.

Suggested model: GPT-5 Codex. Suggested reasoning level: high.

- Add MILP trace/replay validation without importing Exact memo-cache or
  Hybrid candidate/rollout assumptions.
- Audit forwarding-path, cgroup, control-plane, learning-footprint, and
  resource summaries as algorithm-neutral, extendable, or inapplicable.
- Record MILP-specific model-build/solve counts, incumbent/bound/gap, backend,
  termination, and memory separately from HTTP/controller metrics.
- Keep all diagnostics opt-in and behavior-neutral.

Gate: every reused diagnostic is proven compatible or explicitly rejected,
and replay catches placement, coefficient, status, objective, or metric drift.

### MILP configurable-cutoff requirement

MILP Phase 1 must expose a validated per-run `--cutoff SECONDS` option and
carry it unchanged through configuration into result provenance. MILP Phase 2
must apply that value through the backend's native time-limit mechanism rather
than hiding a different hard-coded solver limit. Tests must cover invalid
nonpositive/nonfinite values, propagation, optimal completion before cutoff,
timeout with an incumbent, and timeout without an incumbent.

## MILP Phase 0 implementation result

Status: complete. MILP Phase 1 is next.

Suggested model: GPT-5 Codex. Suggested reasoning level: xhigh.

- Added pure `MILP/phase0_contract.py` with version
  `milp-coupled-phase0-contract-v1`; importing it cannot run an experiment,
  print, seed a global RNG, or create a result file.
- Froze one-based runtime-configurable `N`, `K`, and `(M_1,...,M_K)`
  dimensions, with initial default `N=15`, `K=3`, `(10,10,10)` and 30 total
  replicas; also froze exact `L=2`, canonical two-stage actions, and the
  one-stage bypass for the default three-stage profile.
- Froze complete Ready/assigned-flow capacity and directed-link metadata,
  final-load reconstruction, centralized known-state welfare, one planning
  link per flow, and the exclusion of learning/observation telemetry from the
  planner.
- Defined the future binary `x/y/z/p` variable families and all action,
  availability, capacity, load-indicator, pair-linearization, and link-input
  constraints. No production model or solver adapter was added.
- Defined deterministic extraction/tie expectations without assuming a
  backend canonically resolves symmetric optima.
- Defined finite-positive per-run cutoff validation and six solver outcomes
  with build/solve timing, backend/version, termination, incumbent, bound,
  normalized absolute/relative gaps, and optional model counts.
- Added 27 focused tests. They cover the positive contract and all twelve
  legacy mismatches: import-time execution/output risk, decoupled default,
  90-versus-30 topology, ignored budget/hard-coded `B=20`, random-cost
  budget, arbitrary skipping, missing admission/link constraints, obsolete
  utility/learning, global RNG mutation, incomplete status provenance, broken
  budgeted result/update shape, and undeclared OR-Tools.
- Inspected local backends without installing packages. SciPy 1.18.0 with
  embedded HiGHS 1.12.0 is available and passed a trivial binary MILP smoke;
  Gurobi/gurobipy, OR-Tools/CBC, PuLP, python-mip, highspy, Pyomo, GLPK, and
  standalone HiGHS are absent.

Gate result: the Phase 0 mathematical and information boundary is explicit
and reviewable, focused tests pass, and no file under `IBG/` or
`IBG_Hybrid/` changed. Phase 1 may now establish the replacement package,
immutable solver/result contracts, tiny exhaustive oracle, declared backend
adapter, and user-facing `--cutoff SECONDS` option. Production formulation,
15x3x10 solving, simulation, Kubernetes, replay, and diagnostics remain
Phases 2--6.

## MILP Phase 1 implementation result

Status: complete. MILP Phase 2 is next.

Suggested next model: GPT-5 Codex. Suggested next reasoning level: xhigh.

- Added the import-safe `MILP` package boundary and immutable Phase 1
  configuration, complete perfect-state input, canonical placement,
  objective, normalized solver-result, and backend-availability contracts.
  These extend the Phase 0 types and do not replace its mathematics.
- Added guarded `python -m MILP` configuration parsing for `--flow`,
  `--stage`, `--replica`, and required `--cutoff SECONDS`. Defaults remain
  15x3x10; non-default positive dimensions are accepted; `K>=2`; `L=2`
  remains fixed; a `K`-stage action bypasses `K-2` stages.
- Added read-only SciPy/HiGHS availability discovery. The local gate reports
  SciPy 1.18.0 and embedded HiGHS 1.12.0, and the missing-backend path raises
  a helpful Phase 2 configuration error. No solver invocation or dependency
  installation occurs in Phase 1.
- Added a deterministic tiny exhaustive centralized-welfare oracle that uses
  Phase 0 feasibility and final-load objective reconstruction. It refuses
  more than four flows, more than 100,000 placements, and therefore the
  default 15x3x10 production boundary.
- Removed the old entry point's import-time fifty-experiment loop, output,
  and absolute imports. The old invalid budgeted solver now fails explicitly
  as retired, and importing the remaining legacy header no longer requires
  unavailable OR-Tools.
- Updated the Phase 0 characterization tests to retain the twelve historical
  mismatch records after the unsafe source behavior was isolated, and added
  focused Phase 1 tests for imports, CLI validation, immutable contracts,
  backend gating, exact `L=2`/`K-2` behavior, oracle correctness/ties/scope,
  result reuse, and retired legacy behavior.

Gate result: 55 combined MILP Phase 0/1 tests pass. All supported MILP
modules and both focused test modules compile. Supported imports are silent,
RNG-neutral, and file-safe. The executable prints only one configuration
acceptance/deferred-solver line. No file under `IBG/` or `IBG_Hybrid/`
changed, and no Markdown file exists below `MILP/`.

MILP Phase 2 remains the critical next phase: construct the backend-neutral
`x/y/z/p` model, adapt it to SciPy/HiGHS with the requested cutoff, extract
canonical feasible incumbents and full status/bound/gap provenance, and
prove small cases against the test-only oracle. Production simulation,
15x3x10 scale evidence, Kernel/Kubernetes reuse, and replay/diagnostics remain
Phases 3--6.

## MILP Phase 2 implementation result

Status: complete. MILP Phase 3 is next.

Suggested next model: GPT-5 Codex. Suggested next reasoning level: high.

- Added a pure backend-neutral model containing all canonical `x/y/z/p`
  binaries and the complete Phase 0 equality/inequality families for exact
  two-stage placement, admission, final loads, and directed pairs.
- Reused unchanged Exact known-state expected physical utility for every
  replica/load coefficient. The minimized SciPy objective is the exact sign-
  converted Phase 0 final-load social welfare with one configured link per
  flow.
- Added the SciPy 1.18.0/embedded HiGHS 1.12.0 sparse adapter. It passes the
  exact requested cutoff to the primary native `time_limit`, requires zero
  relative MIP gap for proof, and records separate model-build/solve time,
  backend/version, termination, incumbent, bound, normalized gaps, and model
  counts.
- Added objective-preserving deterministic secondary canonicalization and
  explicit validation of backend bounds, integrality, constraints, action
  shape, feasibility, final loads, and reconstructed objective.
- Added focused Phase 2 tests for exact model families/counts, default
  15x3x10 construction without solving, Exact-helper equivalence, oracle
  agreement, link-aware joint choices, Ready/capacity infeasibility, general
  `K-2` bypass, native cutoff propagation, optimal/time-limit/infeasible/
  unbounded/error normalization, invalid backend output, and deterministic
  repeated symmetric solves.

Gate result: 73 combined MILP Phase 0/1/2 tests pass. The controlled tiny
centralized solve agrees with the exhaustive oracle in objective and
canonical placement. The default model boundary constructs 5,475 variables
and 14,115 constraints but is deliberately not solved or timed. Imports stay
silent and no file under `IBG/` or `IBG_Hybrid/` changed.

MILP Phase 3 is next: add the pure in-memory slot runner, execute only the
selected two-hop routes through an in-process adapter, reuse Exact physical
and observation-jitter separation plus common physical-only SLA/fairness
metrics, record matched observations without learning, and print at most one
compact metrics line. Phase 4 retains scale/15x3x10 cutoff evidence; Phases
5--6 retain Kernel/Kubernetes and replay/diagnostic work.

## MILP Phase 3 implementation result

Status: complete. MILP Phase 4 is next.

Suggested next model: GPT-5 Codex. Suggested next reasoning level: high.

- Added immutable Phase 3 slot, selected-observation, measured-pair,
  simulation-result, metric, and complete slot-result contracts with Phase
  0--3 version and solver provenance retention.
- Added a pure runner that calls the public Phase 2 solver, validates a proven
  or timed feasible incumbent, and fails every non-incumbent status before
  simulation without a heuristic fallback.
- Added an in-process adapter that executes exactly the selected two-stage
  actions after whole-slot placement, conditions physical samples and exact
  likelihoods on final loads, and produces two observations and one pair
  outcome per flow.
- Added separate deterministic BLAKE2b seed schemes and local RNGs for
  physical jitter, observation-only jitter, and measured pair outcomes.
- Reused unchanged Exact physical latency, separated observation jitter,
  convolved likelihood/state estimate, physical-only utility and 110-ms SLA,
  raw physical-plus-pair reference, and Jain comparison behavior. No belief
  update or equilibrium path exists in MILP.
- Kept planning-link coefficients separate from explicit outcome-only
  measured-pair profiles and retained all expected/realized/timing fields in
  memory. The pure runner prints nothing; its explicit wrapper prints one
  compact completed-slot line.
- Covered the default 15x3x10 orchestration boundary with a supplied validated
  incumbent: 15 actions, 30 assignments/observations, and 15 pair outcomes.
  This is structural runner evidence, not an actual default solver runtime or
  optimality/scale claim.

Gate result: 89 combined MILP Phase 0/1/2/3 tests pass, including a real tiny
SciPy/HiGHS slot solve and deterministic default-shape adapter coverage. The
27 relevant unchanged Exact characterization, latency, learning-signal, and
runner tests also pass. Imports remain silent, file-safe, and global-RNG
neutral; no file under `IBG/` or `IBG_Hybrid/` changed.

MILP Phase 4 is next: establish controlled cutoff, incumbent, bound, gap, and
runtime evidence at increasing dimensions through the default 15x3x10
boundary. Do not call a timed incumbent optimal, compare local HiGHS timing
to Gurobi/paper timing, or hide a missing incumbent behind a fallback.
Kernel/Kubernetes integration and replay/diagnostic compatibility remain
Phases 5 and 6.

## MILP Phase 4 implementation result

Status: complete. MILP Phase 5 is next.

Suggested next model: GPT-5 Codex. Suggested next reasoning level: high.

- Added immutable Phase 4 case, evidence, and run-result contracts plus a
  deterministic synthetic scale-profile builder that consumes no global RNG.
- Added an increasing scale ladder through 15x3x10 and a guarded
  `python -m MILP.benchmark` entry point with required `--cutoff SECONDS`.
- Retained complete status/proof, incumbent, bound, gap, backend, model-count,
  build/solve/simulation/total-time, and process-peak-RSS evidence in memory.
- Added tiny-case oracle verification and explicitly recorded that backend
  parity is unavailable with only SciPy 1.18.0/HiGHS 1.12.0 installed.
- Added focused tests for deterministic complete profiles, cutoff/dimension/
  seed validation, oracle parity, no-incumbent handling, memory units,
  import/file/RNG safety, one-line output, and the real cutoff-bound 15x3x10
  model.

The isolated-process one-second ladder produced proven optima through 5x3x4,
a timed feasible 10x3x6 incumbent with relative gap 0.0194227, and a timed
feasible 15x3x10 incumbent of 1628.29 against bound 2281.98 with relative gap
0.401463. The default model used 5,475 variables and 14,115 constraints,
reported 0.140502-second build, 1.210599-second solve-call duration,
2.458909-second total wall time including simulation/runtime overhead, and
182.141 MiB process peak RSS. A repeat reproduced status/incumbent/bound/gap,
not identical timing or memory. This is bounded local HiGHS evidence, not an
optimality proof, hard real-time guarantee, Gurobi result, or paper-runtime
replication.

Gate result: all Phase 4 evidence fields are reproducible from declared seeds
and dimensions, small cases match the oracle, and the supported default size
is honestly labelled time-limited and unproven. MILP Phase 5 may now add the
separate Kernel/container/Kubernetes controller and two-selected-stage route
contract without changing the solver or scale evidence. Replay and diagnostic
compatibility remain Phase 6.

### MILP Phase 4 verbose-output addendum

The completed Phase 4 benchmark now supports optional `--verbose` native
HiGHS progress. Default output remains one compact final line. Focused tests
cover both `disp=False` and `disp=True`, the immediate start banner, and the
final structured summary; no solver or evidence semantics changed.

## MILP Phase 5 implementation result

Status: complete. MILP Phase 6 is next only when explicitly authorized.

- Added immutable Phase 5 Kernel, Ready-endpoint, selected-observation,
  measured-pair, metric, and result contracts under `MILP/`.
- Added `milp-two-selected-stage-route-v1`, which supports routes such as
  1 to 3 and 2 to 3 without weakening Exact's separate contiguous route.
- Added a MILP-specific flow generator that validates complete-slot final
  loads, runs flows concurrently, reuses the unchanged public forwarder, and
  requires two correlated hop observations plus one pair per flow.
- Added Ready-only StatefulSet ordinal discovery and a Kubernetes traffic
  adapter with complete identity/load/likelihood/pair validation.
- Added a controller-side profile/link adapter, solve-once Kernel runner, and
  guarded controller CLI with runtime flow/stage/replica dimensions,
  mandatory cutoff, and optional native HiGHS verbosity.
- Added an isolated MILP image/namespace/RBAC/flow-generator Kustomization and
  a guarded launcher. Dynamic Services, StatefulSets, deterministic profiles,
  processor/forwarder resources, and keep-alive settings reuse the unchanged
  Exact resource builder. The planning coefficient is an explicit launcher
  input rather than a new implicit calibration.
- Reused the Phase 3 incumbent gate and metric policy so Kernel results retain
  solver objective/provenance, physical-only realized utility and SLA,
  configured-versus-measured pair separation, raw reference utility, Jain
  fairness, and separate build/solve/traffic/total timing.
- Completed the read-only Hybrid Phase 5 parity audit. No missing pure MILP
  latency or utility policy was found, and no Hybrid algorithm import was
  introduced.

Gate result: 129 combined MILP Phase 0--5 tests pass. A separate 109-test
Exact/runtime regression selection passes. Compilation, import/RNG/file
safety, Kustomize rendering, and frozen-tree checks pass. The live kind
cluster was inspected read-only and has three Ready nodes but no
`milp-testbed` namespace or Phase 5 image; no image was built and no resource
was deployed, so there is no live Kernel result in this phase handoff. The
default 15x3x10 Kernel result shape was validated with a supplied complete
incumbent (15 routes, 30 observations/assignments, 15 pairs), but deploying
30 two-container replica Pods was not assumed safe or claimed as live
evidence.

Phase 6 remains replay and diagnostic compatibility. It may be opened only by
explicit user direction and must not silently add netem, forwarding/cgroup
diagnostics, DPDK/VPP, bandits, learning, Gurobi claims, or reporting changes.

## MILP Phase 6 implementation result

Status: complete. The bounded MILP Phase 0--6 implementation roadmap is
complete; no MILP Phase 7 is implied.

- Added an immutable JSON-safe trace for pure and Kernel slot results with
  complete dimensions, versions, solver provenance, placement/bypasses,
  final loads, selected configured links, objective, identities, observations,
  measured pairs, outcome metrics, and timing.
- Confined true state to the explicitly private planner-input/replay section;
  observation records remain true-state-free.
- Added solver-independent mathematical and outcome replay with categorized
  drift failures. Replay revalidates feasibility and reconstructs both the
  configured-link social-welfare objective and physical/measured outcome
  views without calling the solver.
- Added optional solver replay. Proven canonical optima require objective and
  placement equality; timed incumbents retain their unproven status and do
  not require identical rerun placements.
- Added an explicit diagnostic audit and opt-in collector. Controller timing,
  HTTP route timing, logical payload counts, and MILP model/process resource
  values are retained only when requested. Forwarding/cgroup concepts are
  compatible but were not newly instrumented. Exact memo cache, learning
  footprint, beliefs/equilibrium, and Hybrid candidate/rollout/sample counts
  are explicitly inapplicable.
- Added a guarded compatibility-audit script that prints one JSON-safe line
  and writes no file.

Gate result: 144 combined MILP Phase 0--6 tests pass, including 15 focused
Phase 6 tests for pure/Kernel replay, corruption, optional solver replay,
diagnostic opt-in behavior, JSON safety, true-state privacy, RNG neutrality,
and controlled in-process pure-versus-Kernel parity. A separate 108-test
unchanged Exact/runtime regression selection passes. No live MILP workload
was present or deployed; the cluster still has no `milp-testbed` namespace.
The 15x3x10 live topology therefore remains unreviewed for local capacity and
is not claimed safely runnable. Netem, new forwarding/cgroup instrumentation,
DPDK/VPP, bandits, Hybrid work, Gurobi integration, new calibration, and file
reporting remain deferred until explicitly authorized.

## MILP Kernel live-repair gate

Updated: 2026-08-01. Status: DNS/network repair complete; MILP forwarder
correction pending.

- Proved that the initial readiness failure was caused by stale kind node
  networking after restart, not by the absolute flow-generator URL.
- Restarted only `kindnet` and `kube-proxy`, then recycled only the isolated
  2x3x2 MILP workloads. Correct node PodCIDRs, Service DNS, and cross-node
  replica reachability are restored.
- Re-ran the exact verbose 2x3x2/cutoff-10/planning-link-2 command. The
  controller reached the Service and the primary SciPy/HiGHS model proved an
  incumbent objective of 333.62750071 optimal before traffic.
- Traffic then failed explicitly because the frozen Exact forwarder rejected
  the valid MILP stage-1-to-stage-3 route as noncontiguous. Therefore no
  completed metrics or Phase 6 live replay exists yet.
- Before the live gate can close, add and test an isolated MILP forwarder that
  accepts the already-authoritative two-selected-stage route without changing
  Exact/Hybrid or any processor, latency, utility, SLA, resource, or telemetry
  policy. Rebuild only the MILP image and repeat the same 2x3x2 run. Require
  two routes, four observations, two measured pairs, one public solver call,
  complete provenance/metrics, and successful Phase 6 replay.

### MILP Kernel live-repair gate result

Updated: 2026-08-01. Status: complete.

- Added the isolated MILP forwarder and resource projection while preserving
  Exact's contiguous-route default and every accepted processor/resource/
  latency/utility contract.
- Added regression coverage for noncontiguous MILP acceptance, reverse-stage
  rejection, unchanged Exact rejection, generated MILP application command,
  absolute readiness URL/failure provenance, and live `AnyHttpUrl` replay
  normalization.
- Added silent in-memory Phase 6 replay to the live controller and expanded
  its single final metrics line with complete aggregate/count separation.
- Rebuilt only `milp-testbed:kernel-phase5` and ran the requested verbose
  2x3x2 experiment with cutoff 10 seconds and planning link 2 ms. The Job
  completed with proven optimum 333.62750071, equal bound, zero gap, two
  routes, four observations, two pairs, and `replay=ok`.
- The final live aggregate metrics were expected-stage welfare 337.628,
  configured planning deduction 4.000, physical realized utility 338.040,
  physical latency 57.960 ms, measured-pair latency 14.045 ms, raw latency
  72.005 ms, pair-reference utility 323.995, zero physical-only SLA
  violations, Jain fairness 0.999997, solver time 0.033037 seconds, traffic
  time 0.074069 seconds, and total controller-slot time 0.111500 seconds.
- Gate verification: 150 MILP Phase 0--6 tests and 95 relevant unchanged
  Exact/runtime tests pass. Compilation, silent import, global-RNG neutrality,
  no-file-side-effect coverage, diff checking, frozen IBG/Hybrid trees, no
  MILP Markdown, and no Hybrid algorithm import checks pass.

The small 2x3x2 testbed remains deployed. No 15x3x10 topology, netem,
forwarding/cgroup extension, DPDK/VPP, Gurobi, Hybrid algorithm, learning,
calibration, or file reporting was added or run.

### MILP Kernel launcher observability addendum

Status: complete.

The guarded launcher now automatically prints pre-solver scale/footprint,
cutoff/planning inputs, capacity notice, cluster nodes, image mode, rollout
milestones, Ready snapshot, controller Job name, and controller-wait state.
`--verbose` still controls only native HiGHS output. This addendum does not
create persisted reports, change the MILP/Kernel contract, or impose a new
replica cap. The prior 15-replicas-per-stage live attempt demonstrates why
deployment progress must be visible: 45 two-container Pods exceeded the
small local cluster's live capacity and stalled before a controller Job was
created.

## MILP bounded experiment-input parity repair result

Updated: 2026-08-01. Status: complete; this is not a new MILP phase.

- Added immutable `milp-experiment-profile-v1` and a fingerprint over the
  complete planner input, cutoff, source/mode provenance, and separate pure
  measured-pair profile.
- Added `python -m MILP.experiment` for pure same-input runs. It performs no
  Kubernetes/image/report-file work and prints one compact line by default;
  `--verbose` enables native HiGHS output and a provenance banner.
- Changed the Kernel launcher/controller to mount and consume the same profile
  after Ready discovery. MILP admission no longer comes from old runtime
  profile capacity.
- Added `assigned-flows-per-slot` admission, a flow-count default,
  `--assigned-flow-capacity`, and complete explicit link input through
  `--planning-links`; uniform link mode remains available and labelled
  objective-constant.
- Added mutation, round-trip, CLI construction, legacy-capacity,
  uniform/explicit-link, large construction-only, RNG, and small real-solver
  parity tests. Existing Phase 4 behavior remains unchanged.
- Completed a live 2x3x2 gate. Pure and Kernel shared fingerprint
  `011001de78293ceefae74d4c52a330a5`; both proved objective/bound
  `333.62750071` with zero gap under cutoff 10 seconds. Kernel completed two
  routes, four observations, two pairs, and replay.

Gate result: 158 MILP Phase 0--6/parity tests and 127 relevant unchanged
Exact/runtime tests pass. No new phase, heuristic, solver, calibration,
learning, report, netem, DPDK/VPP, Gurobi, Hybrid behavior, commit, or push was
added.

### Immediate MILP follow-up: latency-aware planning profile

Status: pending explicit implementation authorization.

Replace the uniform `--planning-link-ms` smoke/control default with a complete
deterministic heterogeneous directed planning-latency profile consumed by both
pure and Kernel paths. Demonstrate that it changes pair selection where
appropriate, preserve its provenance/fingerprint, and retain actual Kernel
pair latency only as post-placement outcome telemetry. This is a bounded input
profile correction, not a new formulation/solver/Kubernetes phase.

### Immediate MILP follow-up: Kernel replica-rollout scalability

Status: pending investigation; planning-latency profile work is paused.

Measure the resource and scheduling envelope of the two-container MILP replica
Pod, identify why larger StatefulSets do or do not become Ready, and determine
safe resource/topology changes that permit more replicas. Begin with read-only
node/Pod evidence and controlled small rollouts. Do not change requests,
limits, worker counts, or topology until the bottleneck is established and a
specific change is accepted.

The deployment-ownership prerequisite is complete: MILP now has its own
resource/profile/discovery boundary, with the existing footprint preserved.
Next, measure only MILP at progressively larger replica counts and evaluate
MILP-only rollout/resource changes without altering IBG.

The first MILP-only footprint change is complete: use the split service and
controller images in the next controlled rollout, then compare image loading,
Ready time, measured service RSS/CPU, and node pressure against the prior
single-image baseline. Keep worker counts and resource specifications fixed
for that comparison.

The 12x3x6 service-image gate passed: 18 Pods became Ready with zero restarts,
and the sampled forwarder cgroup footprint fell by 31.8% while the processor
footprint remained stable. Next scaling work may test a larger MILP-only
replica count, still with the same workers and resource declarations.

### MILP rollout/resource optimization: first bounded change complete

Updated: 2026-08-03.

The first MILP-only rollout optimization is complete. The private processor
now requests 64Mi and is capped at 256Mi while retaining its prior CPU and one
worker; the public forwarder remains unchanged. The launcher now supports a
positive `--rollout-batch-size` with default two replicas per stage and waits
for each all-stage batch before scaling further.

The fresh 6-flow/3-stage/3-replica validation used batch size two, completed
the `2 -> 3` sequence, reached nine Ready zero-restart replica Pods, then
completed one solver/traffic slot. The next rollout-scaling work may test a
larger MILP-only target with these fixed values and collect same-shape rollout
and cgroup evidence. It must not re-open the paused planning-latency profile
work or alter worker counts, forwarder resources, or MILP outcome semantics.

The batching control was then corrected before further scaling: an existing
deployment's desired count is now the starting point for scale-up, rather than
being reset to the first batch. Live 3-to-5 validation confirmed that count
behavior but also showed a profile-hash-driven rolling refresh of existing
Pods. The next larger MILP-only gate should distinguish count preservation from
Pod-process preservation before making any additional resource or topology
decision.

The profile-hash cause is now repaired. The live 10x3x5-to-10x3x6 gate proved
that append-only profile expansion preserves the existing 15 replica-Pod UIDs
and creates only the three new ordinal-5 Pods. Future rollout-scale gates may
use this non-disruptive behavior, but a deliberate state/profile change of an
existing replica remains a separately explicit refresh operation.

### MILP planning-latency profile repair complete

Updated: 2026-08-03. Status: complete.

- Strengthened the shared `milp-planning-links-v1` parser for complete
  dimension-matched directed profiles, strict IDs, stage direction,
  duplicates, finite nonnegative costs, source, and version provenance.
- Added explicit source/contract/mode provenance to the canonical pure/Kernel
  experiment profile and compact output while preserving the existing
  whole-input fingerprint and byte-equal planner-input parity.
- Added the opt-in `python -m MILP.planning_links` deterministic heterogeneous
  example generator. It writes only to stdout and is explicitly not calibrated.
- Proved in a one-flow coupled fixture that uniform links choose canonical
  `(1,1) -> (2,1)`, while a heterogeneous table with otherwise identical
  states/capacities changes the selected pair to `(2,2) -> (3,2)`.
- Proved that changing outcome-only measured-pair profiles changes measured
  telemetry but not planner coefficients or placement.
- Gate result: 192 MILP Phase 0--6/parity/rollout/planning-link tests and 40
  relevant unchanged Exact latency/processor/forwarder tests pass. Compilation,
  silent imports, RNG neutrality, diff checking, frozen IBG/Hybrid trees, no
  MILP Markdown, and no Hybrid algorithm import checks pass.

The next planning-link task, if requested, is evidence-backed coefficient
calibration. It is not part of this contract repair and must not reinterpret
the deterministic example as measured latency.

### Future: common seeded hidden-state experiments

Requested: 2026-08-03. Deferred.

Add a cross-baseline --seed option with default 2050. It must generate one
reproducible hidden-state map at experiment start, keep it unchanged through
all slots, retain it in provenance, and allow IBG-Exact, IBG-Hybrid, MILP, and
future baselines to run against the same map. This is distinct from
post-placement outcome RNG streams. Acceptance requires pure/Kernel parity,
same-seed reproducibility, different-seed state-map variation, no global-RNG
mutation, and explicit safe refresh behavior for existing Kernel Pods.

### MILP temporary benchmark-input parity check

Status: ready for user-run validation.

Use `--planner-profile synthetic-scale --profile-seed 20260801` in pure and
Kernel MILP entry points to construct the existing Phase 4 benchmark input,
including state/capacity/link tables. Confirm equal fingerprints and compare
solver status/bound/gap/solve time before interpreting Kernel traffic. This is
an opt-in diagnostic check only; ordinary runtime mode remains unchanged.

### MILP future profile-difficulty ablation

Deferred until requested. To identify whether replica states or planning-link
coefficients dominate the observed solver-time difference, compare benchmark
states with runtime links, runtime states with benchmark links, and the full
benchmark profile at equal dimensions/cutoff. Do not treat this diagnostic as
latency calibration or alter the normal runtime profile by default.

## Future IBG-Hybrid Kernel rollout/resource phases

Evaluated: 2026-08-06. Not implemented.

### Infrastructure Phase 0: freeze ownership and reuse boundaries

Specify Hybrid-owned names, labels, profile schema, Ready-only discovery,
controller lifecycle, and image ownership. Record the existing one-worker
processor/two-worker forwarder split as reused infrastructure, not new work.
No deployment or image build belongs to this phase.

### Infrastructure Phase 1: Hybrid L=2 route execution

Add and test the versioned exactly-two-hop route contract around the existing
processor/forwarder split. Support noncontiguous routes and routes beginning
after stage 1. Prove that the skipped stage receives no request, observation,
pair endpoint, learning input, or metric contribution.

### Infrastructure Phase 2: Hybrid-owned Kubernetes boundary

Add the separate namespace, RBAC, labels, ConfigMaps, profiles, Services,
StatefulSets, flow generator, Ready discovery, and controller adapter. Require
complete placement and exact Ready ordinal coverage before traffic. Do not
share mutable ownership with Exact or MILP.

### Infrastructure Phase 3: lean Hybrid image split

Create separate service and controller images. Prove the service image excludes
controller-only policy dependencies and that the controller contains the
Hybrid policy/learning stack without unnecessary MILP solver dependencies.
Preserve ports, workers, clients, keep-alive, latency, observation, and
telemetry behavior.

### Infrastructure Phase 4: first small live Kernel gate

Run only a separately approved small topology. Verify routing, complete
two-observation/one-pair telemetry per flow, skipped-stage absence, belief
retention across slots, imports, readiness, restarts, and pure/Kernel semantic
parity before adding rollout optimizations.

### Infrastructure Phase 5: bounded rollout and existing-count preservation

Add deterministic all-stage rollout batches. Preserve the existing consistent
replica count during scale-up, add only missing ordinals, reject partial or
inconsistent StatefulSet ownership, and finish at the explicitly requested
replica count.

### Infrastructure Phase 6: append-only runtime profiles

Allow new ordinal profile entries without rolling existing Pods. Reject any
change to a running identity's runtime profile, prove existing Pod UID
preservation, and keep learned beliefs exclusively in controller state.

### Infrastructure Phase 7: Hybrid-specific resource evidence

Measure the Hybrid service image before accepting the candidate processor
50m/1 CPU and 64Mi/256Mi memory declaration. Preserve the forwarder at two
workers and 25m/1 CPU, 128Mi/256Mi unless new separately authorized evidence
supports a change. Record cgroup memory, CPU throttling, probes, restarts,
OOM/eviction, rollout time, and controller resource use.

### Infrastructure Phase 8: incremental scale validation

Increase topology only one explicitly approved step at a time. Choose each
next scale from the preceding phase's node/Pod/controller evidence; there is no
pre-authorized final-scale readiness gate. If Monte Carlo is later reopened, size
its controller CPU/memory/deadline separately without retuning replica services
or changing policy semantics.

No implementation phase begins from this evaluation alone; it requires a new
explicit user authorization.

## IBG-Hybrid MC root-shortlist correction

Next authorized pure-algorithm task. Updated: 2026-08-06.

Replace the planned production `Q=10` MC root shortlist with the professor's
top-five complete-route shortlist. Preserve existing per-stage `C=5` pruning,
rank the resulting complete feasible action pool by immediate joint score, and
give only the canonical top five roots `S=50` independent epsilon-greedy
rollouts. Keep `D=2`. Future rollout flows use the current updated-state Phase
2 greedy/pruned policy with its seeded epsilon exploration; they never invoke
deterministic lookahead. Preserve the historical all-feasible-root MC as a
test/reference path and keep automatic MC disabled.

Acceptance requires root-shortlist, fewer-than-five, outside-shortlist,
candidate-specific sample-count, seed, canonical-tie, separate
`D_LOOKAHEAD=2` and `D_MC=10` behavior, D_MC clamping, updated-state
greedy/epsilon MC-window behavior, pure-greedy completion-tail behavior,
no-lookahead, branch-isolation, focal-only-value, and fixed-seed 20x3x10
sequential-runtime tests. This task is pure Python;
Kubernetes, containers, images, rollout batching, resource tuning,
append-only profiles, nodes, and traffic remain out of scope.

The MC branch must not terminate its projected state at `D_MC`. After the
noisy MC window it completes the remaining branch arrivals through pure greedy
Phase 2 choices, so their congestion contributes to the focal value. This tail
is an approximation only; it is not normal Hybrid lookahead or another MC
decision.

## IBG-Hybrid rollout/resource phases postponed

The previously evaluated Hybrid infrastructure phases are retained as future
reference only. Do not begin any of them now. Reopen them during later Hybrid
Kubernetes/node implementation, in the recorded order and one separately
authorized phase at a time.

## IBG-Hybrid professor-baseline MC correction completed

Completed: 2026-08-06.

The pure-Python production `select_monte_carlo` now uses the canonical top five
complete roots from the unchanged Phase 2 `C=5` per-stage pruned pool. Every
retained root receives `S=50` independent samples. `D_MC=10` owns only the
epsilon-greedy window; a pure updated-state greedy tail completes the projected
slot. `D_LOOKAHEAD=2` remains independent. The old all-root/truncated method is
available only through an explicitly named reference boundary, and automatic
slot orchestration still cannot select MC.

Acceptance evidence includes canonical fifth-root ties, fewer-than-five pools,
excluded-root absence, exact per-root sample counts, depth independence and
clamping, epsilon-window and no-noise-tail behavior, updated-state Phase 2
accounting, forbidden lookahead/recursive-MC calls, branch isolation,
focal-only scoring, fixed seeds, reference-path separation, and a sequential
20-flow/3-stage/10-replica production-boundary run. The local explicit MC call
accounted for 75 roots, sampled five, excluded 70, ran 50 samples per root with
10 noisy plus nine tail arrivals, and completed in 11.489301 seconds. This is
local solver evidence, not a real-time guarantee.

Next work is not implicitly authorized. MC automatic activation and
parallelism remain deferred. All previously evaluated Hybrid Kubernetes,
node, image, resource, rollout, append-only-profile, and live-traffic phases
remain postponed until explicitly reopened one phase at a time.

## IBG-Hybrid explicit full-slot MC execution and bounded parallelism

Completed: 2026-08-06.

The pure runner now exposes explicit `--policy mc` full-slot/multi-slot
execution while retaining `lookahead` as the unchanged default. MC processes
all real flows in the established slot-wide order, commits only focal actions,
and then reuses the existing simulation, observation, learning, metric, and
equilibrium path. It prints one compact line per completed slot.

Independent shortlisted-root rollout groups may use `--mc-workers N`; the
current default is three process workers. Acceptance requires and includes
fixed-seed sequential/parallel equality, no global-RNG consumption, retained
canonical ordering, and no real branch-state leakage. Automatic MC activation,
Kubernetes/node work, and any broader parallelization remain deferred.

Automatic MC activation remains explicitly out of scope. Production MC is a
manual experiment mode through `--policy mc` until separately authorized.
