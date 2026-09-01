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

Active detailed implementation plan. This Phase 0--8 sequence is the roadmap
for Hybrid Kubernetes work: it already combines the original Kernel
implementation with the image, rollout, append-only-profile, and resource
optimizations at the phases where they become safe to introduce. The later
short "Reframed" summary is retained only as an intermediate planning record;
it does not replace this detailed order.

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

Run only a separately approved small topology in a dedicated persistent Hybrid
cluster. Create that cluster only when absent, reuse it when present, and leave
it available after the run; deletion is an explicit recovery/cleanup action,
never normal completion behavior. Verify routing, complete two-observation/
one-pair telemetry per flow, skipped-stage absence, belief retention across
slots, imports, readiness, restarts, and pure/Kernel semantic parity before
adding rollout optimizations.

### Infrastructure Phase 5: bounded rollout and existing-count preservation

Add deterministic all-stage rollout batches. Preserve the existing consistent
replica count during scale-up, add only missing ordinals, reject partial or
inconsistent StatefulSet ownership, and finish at the explicitly requested
replica count. Add Exact-compatible `--skip-build` lifecycle semantics for the
two Hybrid images: after one successful normal build/load/deploy, the flag must
reuse the images already loaded in the persistent kind node, skip both Docker
builds and kind image loads, and suppress the otherwise explicit service
rollout restart. Manifests, requested counts, readiness, and the fresh
controller Job are still reconciled; a real configuration change may trigger
only the Kubernetes changes it requires. Reject `--skip-build` if either
expected Hybrid image is absent from the node.

### Infrastructure Phase 6: append-only runtime profiles

Allow new ordinal profile entries without rolling existing Pods. Reject any
change to a running identity's runtime profile, prove existing Pod UID
preservation, and keep learned beliefs exclusively in controller state. When
Phase 5 `--skip-build` is used for append-only expansion, preserve every
existing service process and Pod UID, create only the newly requested
ordinals, and do not turn ConfigMap reconciliation into an implicit rollout.

### Infrastructure Phase 7: Hybrid-specific resource evidence

Measure the Hybrid service image before accepting the candidate processor
50m/1 CPU and 64Mi/256Mi memory declaration. Preserve the forwarder at two
workers and 25m/1 CPU, 128Mi/256Mi unless new separately authorized evidence
supports a change. Record cgroup memory, CPU throttling, probes, restarts,
OOM/eviction, rollout time, and controller resource use.

### Infrastructure Phase 7.5: manual MC Kubernetes controller gate

After Phase 7 is accepted, expose the existing frozen Hybrid MC implementation
through the Kubernetes controller Job only by explicit `--policy mc`, with an
explicit bounded `--mc-workers` value. Keep deterministic lookahead as the
default and prohibit automatic MC activation. Reuse the Phase 7-accepted
topology without increasing scale, preserve the persistent dedicated cluster
and Phase 5 `--skip-build`/Phase 6 Pod-UID guarantees, and change no service
image, processor/forwarder resource, route, telemetry, learning, utility, SLA,
or jitter behavior.

The controller must create one bounded MC process pool per slot, reuse it
across all focal placements, close it before HTTP traffic and learning, finish
all placements before the one complete flow-generator request, and retain
beliefs across slots. Acceptance requires fixed-seed pure/Kernel MC placement
and final-load parity, one-worker/bounded-worker decision equality, unchanged
global RNG state, manual-only selection, complete exactly-two-hop telemetry,
skipped-stage absence, no hidden-state exposure, controller CPU/RSS/deadline
evidence, zero service-Pod restart/UID change under `--skip-build`, and a fresh
finite controller Job. This phase authorizes no rollout or scale increase.

### Infrastructure Phase 8: incremental scale validation

Increase topology only one explicitly approved step at a time. Choose each
next scale from the preceding phase's node/Pod/controller evidence; there is no
pre-authorized final-scale readiness gate. If Monte Carlo is later reopened, size
its controller CPU/memory/deadline separately without retuning replica services
or changing policy semantics. Continue on the dedicated persistent Hybrid
cluster so ordinal/UID preservation is observable across gates; cluster
recreation is an explicit recovery event and invalidates cross-step UID
continuity evidence.

If Phase 7.5 passes, Phase 8 may run manual MC at a larger approved scale only
as a separately selected variant of that scale gate. Re-measure MC controller
CPU, RSS, worker count, and deadline at each such scale; lookahead remains the
default and a successful lookahead scale step does not automatically authorize
MC at that size.

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

The bounded local worker pool is now created once per explicit MC slot and
reused across focal decisions; it closes before outcome simulation/learning.
This is the completed no-Kubernetes process-lifetime optimization. Further
parallelism remains deferred.

## IBG-Hybrid Kernel sequencing clarification

Updated: 2026-08-06. The preceding detailed Infrastructure Phase 0--8 plan is
authoritative. This short list is a non-authoritative summary retained from an
intermediate reframing discussion; it must not create a parallel implementation
track.

1. **Hybrid Kernel foundation:** create Hybrid-owned deployment/configuration
   boundaries and versioned L=2 two-selected-stage route execution, including
   skipped/noncontiguous-stage handling.
2. **Hybrid image and baseline runtime:** establish isolated service/controller
   image ownership while reusing the proven private-processor/public-forwarder
   split and its existing worker/resource baseline.
3. **Small live gate:** validate Ready discovery, exact two selected
   observations plus one pair per flow, belief retention, and pure/Kernel
   outcome parity on a reviewed small topology.
4. **Safe scale rollout:** implement bounded all-stage rollout, existing
   ordinal preservation, and append-only profile validation together; reject
   profile drift and wait for complete Ready coverage.
5. **Hybrid resource evidence:** measure service and MC-controller cgroups,
   restart/OOM/throttling/rollout behavior, then accept only evidence-backed
   resource right-sizing.
6. **Incremental scale gates:** increase one requested topology at a time from
   the previous phase's readiness and resource evidence.

None of these phases authorizes automatic MC activation, changes to Exact or
MILP, or a change to Hybrid placement/learning/utility/latency/SLA semantics.

## IBG-Hybrid Kernel Infrastructure Phase 0 result

Completed: 2026-08-06.

- Added the versioned, immutable Hybrid-owned namespace, labels, selectors,
  object names, ConfigMap names, and separate service/controller image roles.
- Added a complete canonical processor runtime-profile schema containing only
  replica identity, hidden state, and observation seed. Beliefs, admission
  capacity, and planning-link metadata remain in their correct separate
  controller boundaries.
- Added the pure Ready-discovery contract for exact configured ordinal
  coverage and rejection of missing, duplicate, foreign, unready, mislabelled,
  or identity-mismatched Pods.
- Added the future controller lifecycle contract: Ready discovery, complete
  sequential placement, selected-route traffic, telemetry validation,
  selected-only learning, and slot result. Belief persistence and manual-only
  MC remain explicit.
- Recorded Exact's one-worker processor/two-worker forwarder, ports, split
  clients, and keep-alive behavior as reused infrastructure. No route execution
  or resource decision was pulled forward from Phases 1 or 7.
- Focused Infrastructure Phase 0 tests pass with the full Hybrid Phase 0--5
  suite: 108 tests. Seventy-seven relevant unchanged Exact/runtime adapter,
  processor, forwarder, flow-generator, runner, learning, and dynamic-
  configuration tests also pass. Compilation, import safety, diff checks,
  frozen `IBG/`/`MILP/` checks, and the no-Markdown-under-`IBG_Hybrid/` check
  pass.

Infrastructure Phase 1 is next but not implicitly authorized. It will add the
versioned Hybrid L=2 two-hop route contract, including noncontiguous routes,
routes beginning after stage 1, and complete skipped-stage absence. No
manifest, image, deployment, cluster, or live traffic belongs to the completed
Phase 0.

## IBG-Hybrid Kernel Infrastructure Phase 1 result

Completed: 2026-08-06.

- Added the versioned immutable exactly-two-hop Hybrid request and response
  contracts with canonical flow ordering, final-load validation, and explicit
  skipped-stage identity.
- Added a pure builder that refuses incomplete placement and converts complete
  real Hybrid focal actions plus the Phase 0 Ready snapshot into executable
  two-hop routes.
- Added a Hybrid-only public-forwarder subclass permitting exactly one
  strictly later selected stage while inheriting Exact processor, HTTP,
  telemetry, timing, and pair behavior unchanged.
- Added a pure concurrent executor that validates exactly two selected
  observations and one measured pair per flow, including separated-jitter,
  exact-likelihood, identity, load, endpoint, and pair correlation.
- Proved noncontiguous stage 1 to stage 3 routes, routes beginning at stage 2,
  different selected stage pairs within one slot, skipped-stage absence,
  complete-placement-before-traffic, final-load propagation, partial telemetry
  failure, and unchanged Exact contiguous-route rejection.
- The full Hybrid Phase 0--5 plus Infrastructure Phase 0--1 suite passes 127
  tests. Seventy-seven relevant unchanged Exact/runtime processor, forwarder,
  flow-generator, adapter, runner, learning, and dynamic-configuration tests
  pass.

Infrastructure Phase 2 is next but not implicitly authorized. It owns the
Hybrid namespace/RBAC/manifests, runtime and planning ConfigMaps, Services,
StatefulSets, flow-generator HTTP wrapper, Ready discovery adapter, and Hybrid
controller adapter. It must require complete Ready ordinal coverage and
complete placement before traffic, while leaving image splitting/building for
Phase 3 and live deployment for Phase 4.

## IBG-Hybrid Kernel Infrastructure Phase 2 result

Completed: 2026-08-08.

- Added the isolated `deploy/hybrid-kubernetes/` namespace, namespace-scoped
  Pod get/list RBAC, Hybrid selectors, headless stage Services, three
  StatefulSets, flow-generator Service/Deployment, two ConfigMaps, Kustomize
  base, and explicit controller Job template. The base renders 14 long-running
  resources; the Job remains outside it so traffic cannot race rollout.
- Added a complete versioned processor profile with identity, hidden state,
  and observation seed only, plus a separate controller input document for
  complete assigned-flow capacity and directed planning-link metadata.
  Beliefs are absent from both documents and the controller does not mount the
  hidden-state profile.
- Added Hybrid-only processor and forwarder ASGI wrappers around the frozen
  Exact runtime and the Phase 1 continuation subclass. Added the Hybrid flow-
  generator ASGI service around the completed concurrent L=2 executor; it
  supports noncontiguous and stage-2-first routes and rejects Exact contiguous
  request substitution or wrong contract versions.
- Added Hybrid-labelled, namespace-scoped Ready discovery that requires exact
  configured stage/ordinal coverage and rejects missing, duplicate,
  unexpected, foreign, unready, mislabelled, or identity-mismatched Pods.
- Added a stateful Hybrid controller and traffic adapter. The existing runner
  performs every focal placement before the adapter sends exactly one complete
  slot request. The adapter validates final assigned loads, discovered
  identity, exactly two selected observations, and one measured pair per flow
  before the existing selected-only learning/metric boundary runs. Beliefs are
  retained for the next slot.
- Added explicit seedless Kernel observation provenance. Physical processing,
  independent observation jitter, the exact convolved likelihood, and selected
  measured-pair latency come from correlated Kernel telemetry. No skipped-stage
  or fabricated simulation-seed input is created. Planning links remain
  separate from measured pair outcomes.
- Preserved the one-worker 8081 Exact processor and its 50m/1 CPU, 128/768 MiB
  resources, the two-worker 8080 forwarder and its 25m/1 CPU, 128/256 MiB
  resources, separate clients, and 30-second public keep-alive. No 64/256 MiB
  reduction was applied.
- Sixteen focused mocked/controller Phase 2 tests pass. The full Hybrid Phase
  0--5 plus Infrastructure Phase 0--2 suite passes 143 tests. Seventy-seven
  relevant unchanged Exact processor, forwarder, flow-generator, adapter,
  runner, learning, and dynamic-configuration tests pass. Python compilation,
  JSON/YAML parsing, Kustomize rendering, import/RNG/file safety, frozen
  `IBG/`/`MILP/` diffs, no-Markdown-under-`IBG_Hybrid/`, and `git diff --check`
  pass.

Infrastructure Phase 3 is next but not implicitly authorized. It owns the
lean Hybrid service/controller image split and dependency-content proof. It
must not deploy or run live traffic; the first separately approved live small
Kernel gate remains Infrastructure Phase 4.

## IBG-Hybrid Kernel Infrastructure Phase 3 result

Implemented: 2026-08-08. Image construction remains blocked on deliberately
ungranted dependency-network access.

- Added separate Hybrid service/controller Dockerfiles, minimal dependency
  manifests, narrow package initializers, and an explicit `.dockerignore`
  whitelist. Both retain the Phase 0 image identities.
- The service source allowlist contains only the frozen Exact processor/
  forwarder runtime and Hybrid profile, two-hop route, executor, forwarder,
  processor, and flow-generator modules. It excludes Hybrid policy, runner,
  controller, learning orchestration, belief retention, reporting, MILP,
  SciPy/HiGHS, OR-Tools, and pandas.
- The controller source allowlist contains deterministic lookahead, manual MC,
  selected-only learning/metrics, Ready discovery, controller adapters, and
  the Job entry point. It excludes MILP and solver dependencies and has no
  Hybrid service ASGI entry point or Uvicorn dependency.
- Added deployment-only L=2 and lean Exact learning/metric compatibility files
  to avoid legacy eager imports. Tests compare the Exact learning, retention,
  utility, fairness, equilibrium, and SLA behavior exercised by Hybrid slots;
  no file under `IBG/` or `MILP/` changed.
- Temporary materialized image roots prove source absence/presence, dependency
  ownership, silent import behavior, RNG neutrality, no file output, manual-MC
  availability, and no hidden-state/profile mount in the controller.
- Phase 2 route/manifests remain valid and unchanged: noncontiguous and
  stage-2-first requests, exact two-observation/one-pair telemetry, one 8081
  processor worker, two 8080 forwarder workers, split clients, 30-second
  public keep-alive, probes, and current resources are preserved.
- Nine focused Infrastructure Phase 3 tests pass. The full Hybrid Phase 0--5
  plus Infrastructure Phase 0--3 suite passes 152 tests, and 77 relevant
  unchanged Exact runtime tests pass.
- Docker found the existing Azure Linux Python base and accepted the corrected
  context. The `--pull=false --network=none` service build then failed at pip
  because dependency wheels were not cached. Per the gate, no new network was
  used, the controller build was not attempted, and no successful local image
  or in-image inspection is claimed.

Infrastructure Phase 4 remains the first separately approved small live
Kernel gate. Before that gate can begin, both Phase 3 images must be built and
inspected with separately available/approved dependency access, then loaded by
the Phase 4 procedure. Phase 4 must remain small and prove Ready discovery,
complete placement before traffic, exactly two observations/one pair,
skipped-stage absence, belief retention, restarts, and pure/Kernel semantic
parity before any rollout or resource optimization.

### Infrastructure Phase 3 image gate completed

Completed: 2026-08-08.

- Built both frozen Phase 0 image tags locally. The service image is
  78,954,015 bytes and the controller image is 78,492,804 bytes.
- Built the controller from the individually downloaded wheelhouse with a
  read-only BuildKit mount and `--network=none`; no wheel was added to the
  repository or image. The earlier online attempt was canceled after a read
  timeout and left no download process.
- Direct image inspection proves the service owns Uvicorn and ports 8080/8081,
  while the controller owns only its Job command and exposes no ports. Both
  run as `10001:10001`.
- Read-only/network-disabled in-image imports prove service/controller source
  separation, manual MC availability in the controller, silent/RNG-neutral/
  file-clean imports, and absence of MILP, pandas, SciPy/HiGHS, and OR-Tools.
- The focused Phase 3 suite continues to pass 9 tests. The previously completed
  full gate remains 152 Hybrid Phase 0--5 plus Infrastructure Phase 0--3 tests
  and 77 unchanged Exact runtime tests.

Infrastructure Phase 3 has no remaining acceptance item. Infrastructure
Phase 4 remains separately approved work: load the already inspected images
and run only the small live Kernel topology and parity gate before any rollout,
profile-scaling, resource, or scale phase.

## IBG-Hybrid Kernel Infrastructure Phase 4 result

Completed: 2026-08-08.

- Added `deploy/hybrid-kubernetes-phase4-small/` as a two-flow, three-stage,
  one-replica-per-stage overlay. Its long-running render contains the isolated
  Hybrid namespace/RBAC/ConfigMaps/Services, three StatefulSets, and one flow-
  generator Deployment; it deliberately excludes the controller Job.
- Added an explicit two-slot validation Job and import-safe controller entry
  point. The Job was applied only after all three exact configured replica
  ordinals and the flow-generator Pod were Running and Ready.
- Loaded the existing Hybrid service tag and the validation-capable controller
  tag into the three nodes of the restarted existing kind cluster. No cluster
  was created and no image was pushed.
- The Job completed once with both `(1, 3)` noncontiguous and `(2, 3)` stage-2-
  first routes. Each slot returned four selected observations and two measured
  pairs for two flows, with complete placement before one request and no
  skipped-stage request, telemetry, learning input, metric input, or pair
  endpoint.
- The second slot began from the first slot's retained beliefs. Both slots
  preserved separated physical/observation jitter, seedless Kernel provenance,
  final assigned loads, planning-link/measured-pair separation, and pure/Kernel
  placement-learning-metric parity. Both recorded zero physical-only SLA
  violations.
- All four long-running Pods retained their original UIDs, stayed Ready, and
  recorded zero restarts after traffic. The completed Job recorded zero
  restarts; no OOM kill or eviction occurred.
- The full Hybrid Phase 0--5 plus Infrastructure Phase 0--4 and relevant
  unchanged Exact runtime suite passes 236 tests. Python compilation,
  `git diff --check`, frozen `IBG/`/`MILP/` diff, and no-Hybrid-Markdown checks
  pass.

Infrastructure Phase 4 is complete. Infrastructure Phase 5 is the next
separately approved gate: add deterministic all-stage rollout batches while
preserving the existing consistent replica count, adding only missing
ordinals, rejecting partial/inconsistent StatefulSet ownership, and stopping
at the explicitly requested count. No Phase 5 rollout work began here.

### Infrastructure Phase 4 post-gate isolation correction

Completed: 2026-08-08.

- Stopped the three historical `ibg` kind-node containers after discovering
  that restarting them had revived 30 retained MILP stage Pods (60 service
  containers) alongside the small Hybrid gate. Host used memory fell from
  approximately 8.8 GiB to 2.4 GiB, with available memory rising from about
  6.8 GiB to 13 GiB and swap remaining unused.
- Added a pinned, one-control-plane `ibg-hybrid` kind configuration and a
  Hybrid-only live-gate runner. The runner contains no shared-cluster context
  or node name, requires local images, rejects wrong node identity, foreign
  baseline namespaces, and foreign workload Pods, and revalidates inventory
  before the controller Job.
- The default `run-small` path deletes the dedicated cluster after success or
  failure; keeping it requires explicit opt-in. Focused isolation validation
  includes wrong-node/foreign-workload rejection, local-only ownership,
  silent import, and failure-path cleanup.
- The full Hybrid Phase 0--5 plus Infrastructure Phase 0--4 and relevant
  unchanged Exact suite now passes 240 tests. No new cluster was created while
  applying this correction, and frozen `IBG/` and `MILP/` sources/resources
  were not changed.

Infrastructure Phase 5 remains separately authorized. Its eventual rollout
gate must use `ibg-hybrid`/`kind-ibg-hybrid` isolation and may not restart or
reuse the historical shared cluster.

### Infrastructure Phase 4 persistent-lifecycle gate passed

Completed: 2026-08-08.

- Created the isolated one-node `ibg-hybrid` cluster from the pinned local node
  image and ran the two-slot small gate successfully. The first slow node-
  preparation attempt was interrupted before kubeadm, leaving no API; that
  incomplete dedicated node alone was explicitly cleaned up, and one clean
  retry completed.
- Ran the same Phase 4 command a second time. It reused the same container ID
  and Kubernetes node UID, reconciled unchanged resources, restarted only the
  normal Hybrid serving workloads, replaced only the controller Job, and again
  completed both `(1, 3)` and `(2, 3)` routes with complete telemetry, belief
  retention, skipped-stage absence, and pure/Kernel parity.
- The shared `ibg` control-plane and two workers remained stopped. The
  dedicated cluster has no `ibg-testbed` or `milp-testbed` namespace. After the
  second run, all four serving Pods were Ready with zero restarts and the Job
  had succeeded.
- The persistent node currently uses about 1.188 GiB; host memory is about
  3.6 GiB used, 11 GiB available, and zero swap. The node intentionally remains
  running for future reuse.

This closes the pre-Phase-5 lifecycle check only. Infrastructure Phase 5 has
not started; no `--skip-build`, bounded rollout, existing-count expansion, or
Pod-UID preservation claim is made by this normal-restart evidence.

Phase 5 image reuse must use node-runtime evidence, not `kind load` output.
During the second normal Phase 4 run, kind said both images were not present
and re-imported them, but node `crictl images` confirmed the normalized service
and controller tags with platform IDs `bb6c47d791a1f` and `eda04655da857`.
The future `--skip-build` gate must recognize those normalized tags/IDs and
fail only on real absence or mismatch.

### Infrastructure Phase 5 implementation result

Completed: 2026-08-09.

- Added the pure `ibg-hybrid-kernel-rollout-v1` adapter for exact three-stage
  StatefulSet ownership/count discovery, no-shrink validation, deterministic
  missing-ordinal batches, and exact Running/Ready ordinal coverage at every
  target. Mocked Kubernetes tests cover missing, partial, duplicate, foreign,
  mislabelled, inconsistent, equal-count, scale-down, and multi-batch cases.
- Added `--skip-build`, `--replica`, and `--rollout-batch-size` to the dedicated
  persistent Hybrid runner. The normal path owns two offline-only builds, two
  image loads in one Hybrid-only kind operation, explicit service restart,
  count-safe reconciliation, Ready gates, and a fresh Job. The skip path omits
  builds, loads, and restart while preserving reconciliation, readiness, and
  Job replacement.
- Added fail-closed node-image proof using normalized runtime tags and full
  platform config IDs. The expected config IDs are derived from each local
  linux/amd64 OCI image rather than frozen to the observed `bb6c...` and
  `eda0...` values. Missing/mismatched tags or config IDs fail before resource
  reconciliation or traffic.
- Added serving Pod UID/restart snapshots and rejection of any change to an
  existing process under skip-build. Foreign Pods inside the Hybrid namespace
  are now rejected in addition to foreign namespaces/workloads.
- Mocked rollout validation exercised `1 -> 3 -> 5`, applying the same target
  to all stages and completing every Ready gate before the controller Job.
  This is control-plane evidence only: no live new ordinal was created.
- The live gate used only the already-running one-node `ibg-hybrid` cluster at
  2 flows x 3 stages x 1 replica. It performed no build, image load, restart,
  or scale-up. Node UID and all four serving Pod UIDs/restart counts remained
  unchanged; only the completed controller Job was replaced. Both two-hop
  route shapes, complete telemetry, belief retention, skipped-stage absence,
  separated jitter, and pure/Kernel parity passed. The shared `ibg` nodes
  remained stopped and the dedicated cluster remains running.
- Fourteen focused Infrastructure Phase 5 tests, 179 Hybrid Phase 0--5 plus
  Infrastructure Phase 0--5 tests, and 111 relevant unchanged Exact runtime,
  learning, dynamic-configuration, experiment, and launcher tests pass.

Infrastructure Phase 6 is next and has not started. It must add append-only
runtime/controller profiles, reject drift for every running identity, preserve
all existing Pod UIDs/processes under skip-build while creating only newly
profiled ordinals, and then establish the first safe 3-flow x 3-stage x
2-replica live boundary. Resource right-sizing, Kubernetes MC wiring, and
larger-scale validation remain Phases 7, 7.5, and 8 respectively.

### Infrastructure Phase 6 implementation result

Completed: 2026-08-09.

- Added a separate 3x3x2 Kustomize overlay and exact source identity. The
  runtime profile retains the three Phase 4 entries and adds only replica 2 at
  each stage. Controller inputs retain all old capacities/links and add the
  complete new admission and directed-link coverage.
- Added `ibg-hybrid-kernel-profile-expansion-v1` to validate exact shapes,
  canonical completeness, and entry preservation. Mocked tests cover state,
  seed, identity, capacity, link, missing, duplicate, unexpected, partial,
  malformed, and incomplete-target rejection before mutation.
- Extended the persistent runner to read both deployed ConfigMaps before
  apply, validate their append-only transition, require a server-side dry-run
  with unchanged StatefulSet Pod templates, reconcile at the existing count,
  verify exact target data, then use the Phase 5 bounded rollout. The 3x3x2
  boundary is accepted only with `--skip-build`; larger counts remain rejected.
- Mocked validation covers ConfigMap-before-scale ordering, template-drift
  failure before apply, only-missing-ordinal creation, exact Ready gates,
  controller-after-readiness ordering, process preservation, complete
  three-flow telemetry, route forms, final loads, learning, retention, and
  pure/Kernel parity.
- The live gate reused the existing one-node dedicated cluster and scaled only
  the three StatefulSets from one to two. All ordinal-0 and flow-generator
  UIDs/restarts stayed unchanged; only `hybrid-stage-{1,2,3}-1` were created.
  All six stage Pods reached Ready with zero restarts before the fresh Phase 6
  Job ran.
- Two live slots each produced six selected observations and three measured
  pairs after one complete request. Required noncontiguous and stage-2-first
  routes, skipped-stage absence, selected-only learning, belief retention,
  seedless provenance, planning/measured and physical/observation separation,
  and pure/Kernel parity passed.
- No image build, kind load, download, service restart, new node, shared-
  cluster action, resource reduction, Kubernetes MC integration, or larger
  scale occurred. The dedicated cluster remains running.
- Twelve focused Phase 6 tests, 191 Hybrid Phase 0--5 plus Infrastructure
  Phase 0--6 tests, and 119 relevant frozen Exact runtime/lifecycle tests pass,
  along with compilation, Kustomize rendering, and repository integrity checks.

Infrastructure Phase 7 is next and has not started. It must collect Hybrid-
specific processor, forwarder, flow-generator, and controller CPU/memory/
throttling/restart/OOM/rollout evidence at the accepted persistent 3x3x2
topology before deciding whether the candidate processor 64Mi/256Mi memory
declaration is safe. Phase 7.5 and Phase 8 remain separately authorized later
gates.

#### Phase 6 explicit topology CLI correction

Completed: 2026-08-09.

- Added `--flow`/`--flows`, `--stage`/`--stages`, and
  `--replica`/`--replicas` to align the Hybrid runner with Exact and MILP.
- Added fail-closed tuple resolution for only `2x3x1` and `3x3x2`; omitted
  flow/stage values are inferred from the unique approved replica profile.
- Added resolved-topology output before execution and rejection of mismatched,
  non-three-stage, or larger tuples before the first cluster command.
- Focused mocked lifecycle tests prove explicit selection, aliases, inference,
  unchanged approved execution, and pre-contact rejection. The full Hybrid
  Phase 0--5 plus Infrastructure Phase 0--6 suite now passes 196 tests; 119
  relevant frozen Exact tests still pass.
- No live rerun, profile/resource mutation, image operation, cluster action,
  Phase 7, Phase 7.5, or Phase 8 implementation occurred.

Infrastructure Phase 7 remains the next step.

### Infrastructure Phase 7 implementation result

Completed: 2026-08-09.

Phase 7 now has a baseline 3x3x2 projection, a processor-only 64Mi/256Mi
candidate projection, a five-slot finite controller Job, and a bounded live
resource collector. The transition validator compares complete StatefulSet
specs, rejects replica/resource/command/probe/ownership drift, and permits
only the private processor's two memory values to differ. Live evidence uses
exact per-container CRI coverage, cgroup-v2 counters, Pod/events, controller
RSS/deadline, node pressure, and explicit UID lineage; no policy or placement
mathematics enters the resource adapter.

Baseline and candidate five-slot gates both completed at exactly 3 flows x 3
stages x 2 replicas with six observations and three measured pairs per slot,
complete placement before traffic, both required route forms, skipped-stage
absence, belief retention, seedless provenance, separated jitter/link inputs,
and pure/Kernel parity. Baseline processor peak/working set were
48,599,040/44,486,656 bytes. Candidate values were
46,583,808/42,487,808 bytes with 221,851,648 bytes of limit headroom and zero
processor throttling, memory events, restarts, OOM/eviction, fatal events, or
post-Ready probe failures. The 64Mi request / 256Mi limit candidate is
accepted; CPU remains 50m/1 CPU.

The deliberate resource rollout replaced only the six stage Pods and retained
the dedicated node and flow generator. All new stage containers have zero
restarts. Pods became Ready five to seven seconds after creation, with a
16-second earliest-creation-to-final-Ready window; startup-only readiness
failures cleared before traffic. No image build/load/download, worker/topology
scale, Phase 7.5 MC integration, Phase 8 validation, shared-cluster action,
commit, or push occurred.

Phase 7.5 is next and remains separately authorized. It must reuse this
accepted 3x3x2 candidate service-resource boundary under `--skip-build`, keep
lookahead as the default, expose MC only through explicit `--policy mc` plus a
bounded worker count, and size controller MC CPU/RSS/deadline without changing
service resources or scale.

Seven focused Phase 7 tests, the complete 203-test Hybrid Phase 0--7 suite,
and 119 relevant frozen Exact regressions pass, along with compilation,
Kustomize, CLI, diff, frozen-tree, and process checks.

### Infrastructure Phase 7.5 implementation result

Completed: 2026-08-09.

Phase 7.5 adds a bounded controller CLI, adapter worker-count propagation, an
MC-aware pure/Kernel replay gate, a controller-only no-build source mount, and
controller process/resource evidence. Omitted policy remains lookahead. MC is
reachable only through `--policy mc --mc-workers N`, with `N` in 1--2. The
existing pure runner supplies one process pool per slot, reuses it for all
focal placements, and closes it before the single traffic request; no policy
mathematics was copied into Kubernetes code.

The live gate reused `--skip-build --flow 3 --stage 3 --replica 2` and the
accepted Phase 7 candidate resources. One-worker and two-worker Jobs each ran
two slots and produced identical placements/final loads. Every slot returned
six observations and three pairs, exercised noncontiguous and stage-2-first
routes, omitted skipped stages, retained beliefs, preserved selected-only
learning and latency/jitter separation, and passed pure/Kernel replay parity.
Both Jobs observed exactly their requested direct children and zero children
after each slot.

Both controller Jobs completed in eight seconds against the 600-second
deadline. One/two-worker CPU use was 3,367,647/3,408,358 usec; cgroup peaks
were 62,308,352/67,727,360 bytes; maximum process RSS was
71,356,416/71,315,456 bytes; throttling was 0/897 usec. No resource retuning is
required. The dedicated node, all six stage Pods, and flow generator retained
their UIDs and zero restarts; shared `ibg` nodes stayed stopped. No build,
load, download, service rollout, or scale change occurred.

Infrastructure Phase 8 is next and has not started. It must choose one
explicit incremental topology step from the Phase 7/7.5 node, service, and
controller evidence, extend profiles append-only, and re-measure lookahead and
any separately approved manual-MC variant at that scale. No final scale is
pre-authorized.

### Infrastructure Phase 8 Gate 1 implementation result

Completed: 2026-08-09.

Gate 1 adds only the explicitly approved 4 flows x 3 stages x 2 replicas
lookahead boundary. The runner accepts the new tuple only with explicit
dimensions and `--skip-build`, rejects MC and every other new tuple before
cluster contact, and retains historical `2x3x1`/`3x3x2` operation.

The new Kustomize projection preserves all six runtime profiles, admission
capacities, planning links, candidate service resources, and StatefulSet Pod
templates. A dedicated flow-only transition validator rejects old-profile or
controller-input drift before apply. Mocked lifecycle tests prove that the
equal replica target emits no scale command or service restart, reconciles
only the authorized ConfigMaps, waits for exact 2/2 Ready coverage, and then
recreates only the finite lookahead Job.

The live persistent-cluster gate completed two slots. Each slot made four
placements before one request and returned eight selected observations and
four measured pairs. It covered noncontiguous and stage-2-first routing,
excluded skipped stages, propagated final loads within admission capacity,
retained beliefs, applied selected-only learning after complete telemetry,
used seedless Kernel provenance, preserved jitter/link separation, and passed
pure/Kernel lookahead parity.

The dedicated node, all six stage Pods, and flow generator retained their
UIDs and zero restarts. Serving cgroup peaks remained below the accepted
limits with zero serving throttling or memory events. The controller completed
in 22 seconds with 578 seconds of deadline margin, and there were no fatal
events, post-Ready probe failures, or node pressure. Shared `ibg` nodes stayed
stopped. No image build/load/pull/download, new ordinal, service rollout,
resource change, MC-at-scale run, later Phase 8 topology, commit, or push
occurred.

Fourteen focused Gate 1 tests, 225 complete Hybrid tests through Gate 1, and
122 relevant frozen Exact regressions pass, along with Python compilation,
Kustomize rendering, diff, frozen-tree, import-safety, and process checks.

The next Phase 8 gate remains separately authorized. Gate 1 evidence supports
considering a one-flow `5x3x2` lookahead increment without changing replicas
or nodes; alternatively, manual MC at `4x3x2` would require a separate
controller-resource gate. No choice is pre-authorized.

### Dynamic-topology correction complete

Completed: 2026-08-09.

The hardcoded Phase 8 Gate 1 tuple selector has been replaced by the intended
dimension-driven Hybrid experiment launcher. Positive flow and replica values
are now general inputs while the frozen stage count remains three. Historical
`2x3x1`, `3x3x2`, and `4x3x2` documents remain compatible projections, not a
whitelist. The runner deterministically generates complete append-only runtime
profiles, formula-derived admission inputs, and the complete three-stage-pair
planning-link cross-product before reconciliation.

The correction preserves drift rejection, fixed-name ConfigMaps, unchanged
StatefulSet templates, no implicit shrink, Phase 5 bounded equal-stage rollout,
exact Ready coverage at each target, and controller-after-final-readiness. The
live acceptance scaled the persistent cluster from two to five replicas per
stage through targets four and five, then ran two ten-flow lookahead slots. A
second unchanged run preserved all fifteen stage Pods and the flow generator
and recreated only the controller Job.

At `10x3x5`, both live runs passed twenty-observation/ten-pair telemetry,
skipped-stage absence, noncontiguous/stage-2-first routes, admission/final-load
checks, selected-only learning, belief retention, seedless provenance,
physical/observation and planning/measured separation, and pure/Kernel parity.
The then-current one-node resource envelope remained safe without resource or
image changes. Shared `ibg` nodes stayed stopped. The next separately approved
topology correction is one Hybrid control-plane node plus one worker node, with
all Hybrid workloads on the worker. It must validate worker-only placement and
the two-node resource envelope; it deliberately cannot establish same-worker
versus cross-worker workload-path evidence.

The stopped command printed a 15-flow selected topology while its controller
evidence recorded `num_flows: 20`. A later user test confirmed the requested
flow value is propagated correctly, so treat the stopped-run mismatch as an
interrupted-run anomaly rather than a worker-topology gate blocker. Do not use
that stopped run as 15-flow comparison evidence.

Validation passes 9 focused dynamic-topology tests, 234 complete Hybrid tests,
119 relevant frozen Exact tests, and 194 frozen MILP launcher/profile/rollout
tests. Python compilation, seven historical Kustomize renders, diff checks,
frozen-tree checks, and process checks pass. No commit or push occurred.

The dynamic lookahead interface is now usable for further positive flow and
replica requests subject to no-shrink, deterministic profile validation,
exact Ready coverage, and the current node resource preflight. Larger requests
are not pre-certified: each must fit and complete its live evidence gate.
MC remains manual-only and was not run at `10x3x5`.

### Hybrid per-timeslot console presentation complete

Completed: 2026-08-09.

Pure Hybrid and Kernel controller entry points now share a human-readable
completed-slot formatter. Both deterministic lookahead and explicit MC use the
same output fields and precision. Kernel slots flush through a completion
callback before the next slot starts, and the persistent host runner follows
the Job logs live instead of waiting to display output until the entire Job is
finished. Detailed JSON evidence is retained for validation but hidden from
the human console.

The implementation is presentation-only. Predicted per-flow utility was
already summed from the two stage contributions before entering
`HybridSlotMetrics`; the active outcome mode remains `physical-only-v1`, and
all solver, latency, pair, jitter, learning, utility, SLA, fairness,
equilibrium, adapter, and storage behavior is unchanged.

Validation passes 53 focused presentation/Phase 5/Phase 4/Phase 7.5 tests,
238 complete Hybrid tests, and 119 relevant frozen Exact tests. Python
compilation, seven retained Kustomize renders, and three controller-Job parses
pass. No live experiment, cluster mutation, image operation, Exact/MILP edit,
commit, or push occurred.

### Hybrid production experiment lifecycle correction complete

Completed: 2026-08-09.

The normal dynamic launcher command is now `run`, with required positive
topology dimensions and `--max-iterations`. The controller runs sequential
slots with retained beliefs, prints each completed result before the next slot,
stops immediately on the existing equilibrium result, and otherwise completes
exactly the requested maximum with an explicit not-reached status. The
historical `run-small` gate and its bounded evidence assertions remain
compatible but are no longer the ordinary experiment lifecycle.

The requested iteration count is injected into the rendered dynamic Job; its
template no longer hardcodes two slots. Production rendering is finite by the
positive iteration bound and omits the historical gate deadline so the latter
cannot stop a valid experiment early. All dynamic profile, no-shrink, rollout,
Ready, `--skip-build`, process-preservation, and one-request-per-slot contracts
remain unchanged.

The human completed-slot block no longer includes per-flow latency. All
physical, pair, raw end-to-end, and selected-outcome latency fields remain in
the immutable result and hidden machine evidence. Lookahead remains default;
manual MC remains restricted to the previously accepted `3x3x2`, one-or-two-
worker Kubernetes boundary.

Validation passes 73 focused lifecycle/presentation/infrastructure tests, 249
complete Hybrid tests, and 119 relevant frozen Exact tests. All seven retained
Hybrid Kustomize projections and seven controller Job templates parse. No live
experiment, cluster mutation, image operation, dependency download, Exact/MILP
edit, commit, or push occurred.

### Hybrid intentional replica scale-down correction complete locally

Completed locally: 2026-08-11. The live acceptance gate is not yet run.

The dynamic production launcher now models rollout direction explicitly. It
keeps equal targets unchanged, preserves bounded scale-up, and accepts one
deliberate lower all-stage target. Mocked `8 -> 5` coverage removes only
zero-based ordinals `5--7`, keeps old complete ConfigMaps through Pod removal,
then reconciles exact reduced documents and requires final Ready coverage before
the controller Job. Retained stage and flow-generator process identities are
checked separately from intentionally removed Pods.

Profile validation now regenerates exact deployed and target documents and
reports retained/added/changed/removed runtime, admission, and planning-link
sets. Retained identity/state/seed and links cannot drift; admission changes are
formula-bound, and removed links must contain a removed endpoint. Scale-down
resource preflight has zero added Pods. Scale-up, equal reuse, production
iterations, console presentation, and frozen Hybrid semantics remain unchanged.

The next action is a separately approved read-only pre-snapshot followed by the
live `--skip-build --flow 10 --stage 3 --replica 5 --rollout-batch-size 2`
acceptance gate if the deployed topology is still exactly eight replicas per
stage. It must prove retained UID/restart preservation, absence of only the nine
high-ordinal Pods, controller completion, and an unchanged five-replica rerun.

Local validation passes 37 focused tests, 105 Phase 5--8/lifecycle tests, all
252 Hybrid tests in memory-bounded groups, 119 relevant frozen Exact tests, and
50 frozen MILP Phase 5 tests, plus compilation, seven Kustomize renders, and
seven controller Job parses. No live Kubernetes or image action occurred.

### Hybrid initial/final belief snapshots complete

Completed locally: 2026-08-11.

Production `run` now prints the sorted four-state belief vector for every
replica once before the first slot and once after equilibrium or the configured
maximum. It uses Exact's aligned table and three-decimal vector style without
copying Exact's hidden-state or legacy runtime columns. Per-slot metrics remain
belief-free, and lookahead/MC selection, learning, retention, equilibrium, and
all Kernel behavior remain unchanged.

Validation passes 70 focused tests, all 253 Hybrid tests in memory-bounded
groups, and 119 relevant frozen Exact tests, plus compilation and seven
Kustomize renders. No live or image action occurred.

### Hybrid reproducible offline image-build correction complete locally

Completed locally: 2026-08-11. The cache-dependent normal image path is
replaced with separately manifested service/controller local wheelhouses.
Normal execution validates both sets before Docker and then builds both images
with offline-only pip, `--pull=false`, and `--network=none`; skip-build neither
requires nor reads those wheelhouses and continues its node-image reuse path.
The helper can list, validate, and explicitly stage pre-supplied wheels, but
does not download.

Focused wheelhouse/Phase 3--5 tests (48), dynamic/lifecycle/Phase 6 tests (39),
and Phase 7.5/8/Hybrid regressions (52) pass locally. No complete project-local
wheelhouse was present, so no fresh Docker build was claimed; no cluster,
kind-load, image load, dependency download, commit, or push occurred. The next
normal-build gate requires an operator to populate both local wheelhouses using
the committed manifests, validate them, then separately approve any live run.

The one-time wheel acquisition was subsequently explicitly authorized. Both
wheelhouses validated and the clean local service/controller builds completed
with no cache and no network. No kind load, deployment, or live experiment was
performed; a normal runner invocation remains the separately chosen step that
would load the rebuilt images and reconcile serving workloads.

### Hybrid seeded hidden-state profile allocation complete locally

Completed: 2026-08-11. Production `run` now has a required independent
`--profile-seed` and generates balanced, seed-permuted, append-only per-stage
state sequences. The fixed v1 distribution is Very Good/Good/Bad/Very Bad at
30/30/20/20. Ten replicas therefore produce exact 3/3/2/2 coverage in every
stage, while arbitrary prefixes stay within one replica of ideal. Historical
fixed profiles remain unchanged compatibility fixtures.

Seeded provenance and true state remain processor-private. Controller inputs
and mounts contain no seed/state allocation information, discovery continues to
construct policy replicas with `hidden_state=None`, and initial beliefs remain
uniform. Same-seed growth/trim preserves retained identities. A legacy-to-seeded
or reseeded deployment requires explicit `--refresh-runtime-profiles`; its mocked
path validates before write and replaces only changed Pods stage-by-stage after
ConfigMap reconciliation and before controller traffic.

No live migration is part of this completion. The next separately approved gate
must first re-snapshot the dedicated cluster, verify the expected legacy
15-flow/3-stage/10-replica profile, then run one explicit seeded refresh and an
unchanged seeded rerun to prove affected-versus-unaffected UID lineage.


### Hybrid one-control-plane/one-worker topology correction implemented locally

Implemented locally: 2026-08-15. Repository phases 1 and 2 are complete; the
clean-cluster live gate remains pending separate approval.

- The kind configuration now creates one control-plane and one labelled worker.
  All replica StatefulSets, the flow generator, and all retained controller Job
  templates select the worker label.
- The launcher now requires the exact two Ready roles, rejects Hybrid workloads
  bound anywhere except the worker, repeats placement validation at serving
  rollout gates, validates node-local images on both nodes, and collects Phase 7
  CRI serving statistics from the worker.
- Dynamic resource preflight now uses worker allocatable CPU/memory and only
  worker-bound nonterminal Pod requests, plus the unchanged added-replica,
  fresh-cluster flow-generator, and finite-controller request formulas.
- Focused tests cover kind topology, all long-running and finite-Job selectors,
  invalid node roles, control-plane workload rejection, rollout-ready placement,
  two-node image validation, and worker-only resource acceptance/rejection.
- Local validation passes 183 Hybrid Kernel/infrastructure tests and 93 pure
  Hybrid tests, for 276 Hybrid tests in memory-bounded groups. The established
  119 relevant frozen Exact regressions pass. All seven retained Hybrid
  Kustomize projections and all seven controller Job templates render offline;
  changed Python compiles and `git diff --check` passes.

Pending live gate, only after explicit approval: cleanly replace the existing
one-node `ibg-hybrid` cluster, require the two expected node identities/labels
and Ready states, verify every replica and flow-generator Pod plus the finite
controller Pod actually runs on `ibg-hybrid-worker`, run worker resource
preflight, and require the existing pure/Kernel parity and telemetry gates with
zero unsafe restart/pressure behavior. Use an explicitly selected finite
production command and correct requested-flow propagation. Do not reuse the
stopped mismatch as 15-flow evidence. The gate cannot establish same-worker
versus cross-worker workload behavior, multi-host networking, NIC, or line-rate
evidence.


### Hybrid clean-cluster bootstrap readiness race corrected

Corrected: 2026-08-15. The user-authorized 15-flow/3-stage/7-replica launch
created the intended two-node cluster, then failed before build/deployment
because the worker had not reached Ready when the strict inventory check ran.
The launcher now waits for both exact nodes after fresh creation and before
preflight. Fifty-five focused topology/dynamic-rollout tests pass, along with
compilation and `git diff --check`; the read-only live preflight passes on the
retained two-node cluster.

The remaining live gate resumes with the same normal-build command against the
existing empty cluster. It must still prove resource fit, worker-only replica,
flow-generator, and controller placement, rollout/restart safety, and pure/
Kernel parity. No same-worker/cross-worker, multi-host, NIC, or line-rate claim
is available from this topology.

The retained-cluster resume case is covered: absence of the Hybrid namespace
selects the existing namespace-first clean bootstrap path with zero existing
replicas. Read-only live inspection confirms that this exact condition holds;
only Kubernetes management Pods currently exist.


### Hybrid two-node functional gate user-confirmed

Confirmed: 2026-08-15. The user reran a test after reviewing the recent
corrections and reported that it works. The requested management/workload
separation implementation is therefore functionally complete for the current
scope. No detailed result capture or formal performance-evidence phase is
required unless separately requested.


### Deferred Hybrid follow-up plan

Recorded: 2026-08-15. These phases are intentionally not started.

1. **Hybrid netem robustness.** Specify the supported delay/jitter parameters,
   replica interface and privilege boundary, trace provenance, enable/disable
   rollout behavior, and matched baseline methodology. Implement default-off
   Kernel impairment, focused manifest/launcher/qdisc-cleanup tests, and a
   summarizer gate for convergence, posterior development, selected-state mix,
   utility/SLA integrity, and unchanged pure-policy behavior. Packet loss is a
   separate future scope.
2. **Hybrid CSV verification.** Characterize every retained writer in
   `IBG_Hybrid/header.py` and `IBG_Hybrid/report.py`; add temporary-directory
   tests for first write, append, unequal-length columns, identifiers, malformed
   input, and metric semantics. Then decide explicitly whether production
   should call corrected legacy helpers or a host-side structured-trace
   exporter. Verify that default runs create no CSV files.
3. **Hybrid control-plane footprint.** Define a versioned per-timeslot schema
   and opt-in flag, with categorized controller-boundary bytes/messages and an
   explicit logical/application-versus-wire interpretation. Instrument without
   changing execution, validate exact component sums and disabled-mode absence,
   add summary/export coverage if requested, and run Pure/Kernel regression and
   live integrity gates.

Each phase requires a focused implementation review and authorization when it
is resumed. No DPDK/VPP, multi-host, NIC, line-rate, algorithm, learning, or
outcome change is part of this plan.


### Hybrid persistent JSONL experiment evidence complete locally

Completed: 2026-08-15.

- Production `run` now saves the collected detailed slot evidence to
  `runs/ibg-hybrid-experiment-<UTC timestamp>.jsonl`; `--trace-dir` selects a
  different host directory.
- The file contains versioned start, per-iteration, and completion events. Each
  per-iteration event preserves the existing per-flow `measured_pair_ms` and
  the rest of the current detailed Hybrid evidence.
- Pre-write validation rejects missing flows, missing/invalid measured pairs,
  incomplete selected observations, dimension drift, noncontiguous slots, and
  invalid metrics. Focused tests prove lifecycle shape, pair preservation,
  malformed-pair rejection without file creation, CLI integration, and printed
  trace location.
- The full Hybrid Kernel test selection passes 178 tests. Compilation and
  `git diff --check` pass. No live experiment or cluster mutation was performed.

This closes persistence of the current Hybrid evidence. Netem, CSV verification,
and opt-in control-plane-footprint work remain separate deferred phases.


### Hybrid SLA threshold changed to 80 ms locally

Completed: 2026-08-15. The Hybrid runner now uses a dedicated public 80-ms SLA
constant for physical-only classification and records that value in slot
metrics. Tests cover the Exact 110-ms/Hybrid 80-ms separation, physical-only
input, observation/pair exclusion, and two-selected-stage aggregation.

All 279 Hybrid tests pass. Compilation and `git diff --check` pass. No Exact
source file, live cluster, image, Job, or trace was changed. A future live run must use
a normal image build before `--skip-build` can reuse the new controller image.


### Hybrid automatic random multi-run orchestration complete locally

Completed: 2026-08-15. The production launcher now accepts `--runs N` with no
seed arguments. It fixes one seeded runtime environment across the series,
starts every member in a fresh controller Job with fresh beliefs, assigns a
unique operating-system-random experiment seed to the policy root and first
slot ID, and writes one seed-provenanced JSONL trace per member. Existing
seeded environments are reused; fresh environments get one automatic random
profile seed; legacy environments without seeded provenance fail closed.

CLI validation covers the no-seed contract and incompatible options. Focused
tests cover fixed-environment reuse, fresh-environment profile generation,
zero/duplicate rejection, per-run build reuse, Job seed propagation, fresh CLI
routing, series trace naming and provenance, and controller seed ingestion.
The complete Hybrid selection passes 284 tests, and the relevant frozen Exact
regression selection passes 109 tests. Changed Python compiles and
`git diff --check` passes. No live cluster, image, Job, or traffic was mutated
during this implementation.

The next normal production invocation must build the updated image before a
later invocation can safely use `--skip-build`. The separate deferred CSV
verification remains the next requested review and must not be folded into
this series feature.


### Hybrid interrupted scale-down resume corrected locally

Corrected: 2026-08-15. The first user trial exposed a retained live state with
three Ready replicas in every StatefulSet while the exact seeded ConfigMaps
still described the former 20-flow/10-replica environment. Kubernetes managed
fields identify the replica field as a scale-subresource update; the last
applied StatefulSet count and profile count also differ. This is the precise
window after high ordinals are removed but before the final lower-profile
reconciliation.

The dynamic transition gate now permits only that exact profile-superset/live-
prefix state and resumes from the actual count. Tests prove opt-in validation,
continued rejection of excess live Pods and document drift, and an end-to-end
mocked 3-to-7 recovery that trims 10-replica profiles, rolls out in bounded
batches, and preserves processes. All 286 Hybrid tests and the relevant 109
frozen Exact regression tests pass; compilation and `git diff --check` pass.
Only read-only live inspection was performed. The cluster was not repaired or
otherwise mutated by Codex.


### Hybrid CSV verification and opt-in export complete locally

Completed: 2026-08-15. The deferred legacy CSV review found that normal
create/append worked but belief-column order could silently corrupt meaning,
schema growth could create malformed rows, empty metric files failed, and no
active Hybrid path called the helpers. The repaired helpers preserve their
wide layouts while using deterministic header alignment, blank-cell padding,
validation, and atomic replacement. `log_results` was explicitly left outside
the work.

Production `--csv 1` now exports the four metric reports and belief report from
each completed JSONL trace. `aggregate_utility.csv` uses raw end-to-end utility
as requested. Tests cover empty files, uneven run lengths, semantic rejection,
reordered and added belief identities, exact output filenames/layouts,
end-to-end rather than predicted/physical utility, duplicate-run rejection,
CLI default-off/explicit-on behavior, single-run routing, and multi-run columns.
An existing six-slot Hybrid JSONL trace exported successfully in a temporary
directory with six rows in each metric file and seven belief snapshots.

All 291 Hybrid tests and the relevant 109 frozen Exact regression tests pass;
changed Python compiles, CLI help is correct, and `git diff --check` passes.
No live cluster, image, Job, traffic, historical CSV, or repository `figures/`
file was changed during implementation.


### Hybrid CSV directory isolation complete locally

Completed: 2026-08-15. The default Hybrid CSV destination is now
`figures/IBG_hybrid/`, and export creates the missing directory tree before
writing. Focused coverage proves the exact default path and first-export
directory creation. No CSV schema, filename, metric, live runtime, or Exact
behavior changed.


### Hybrid per-timeslot control-plane data footprint complete locally

Completed: 2026-08-15. The deferred footprint phase now records categorized
application-body bytes and message counts only when production uses `--csv 1`.
Host activation is propagated into each finite controller Job, successful
slots persist a validated data-only evidence block, and disabled runs reject
unexpected footprint data while emitting neither the block nor footprint
CSVs.

Actual HTTPX body sizes cover one accepted aggregate Kubernetes discovery
exchange and one route/telemetry exchange. Belief TX/RX remain observed zeros.
Six-category totals and derived belief TX-plus-RX views are validated without
double counting. Sixteen separate footprint files use the existing wide CSV
layout under `figures/IBG_hybrid/footprint/`; the original five Hybrid reports
are unchanged. Timing, CPU, memory, cgroups, wire bytes, and forwarding traffic
were deliberately excluded.

All 305 Hybrid tests and a broad 188-test frozen Exact regression selection
pass. Seven retained Hybrid Kustomize overlays render offline, changed Python
compiles, production help exposes the combined `--csv` behavior, and
`git diff --check` passes. No live cluster, image, Job, traffic, existing trace,
or generated CSV was mutated. Any live validation remains a separate approval
gate.

Final verification addendum: the Hybrid-specific data summary command now
validates completed traces and reports median/p95 payload/message categories,
derived belief totals, and exact grand totals without CPU or timing fields.
Its three focused tests raise the complete Hybrid count from the earlier 305
to 308 passing tests. The previously recorded 188 Exact regressions, seven
offline renders, compilation, and diff checks remain passing.


### Planned Hybrid per-timeslot execution optimization sequence

Planned: 2026-08-16. No implementation or live mutation is part of this entry.

1. **Phase 1: persistent HTTP clients — medium difficulty.** Move Kubernetes
   discovery, controller-to-flow-generator, and flow-generator ingress clients
   to explicit controller/application lifetimes. Prove connection reuse and
   cleanup while retaining exactly one accepted discovery exchange and one
   route/telemetry exchange per completed slot, unchanged application bodies,
   errors, telemetry, footprint totals, and Pure/Kernel results. Do not alter
   inherited public-forwarder clients or keep-alive values.
2. **Phase 2: bounded parallel candidate evaluation — high difficulty.**
   Introduce a pure, process-safe task for one focal lookahead candidate and
   return its canonical index. Keep real flows and each branch's projected
   future flows sequential. First validate serial versus two-process branch
   equality without activating the parallel path in production. Require exact
   candidate accounting, scores, failures, selected routes, loads, and metric
   parity.
3. **Phase 3: controller-lifetime process pool — medium-high difficulty.**
   Create one bounded two-process pool for the finite controller run, reuse it
   across flows and slots, and activate only the Phase 2 independent-candidate
   boundary. Prove no stale belief/load state, deterministic canonical
   collection, clean exception propagation, termination cleanup, no orphaned
   children, and complete serial/parallel Hybrid result equality.
4. **Phase 4: soft controller CPU priority — medium overall difficulty and
   last by design.** Only if controlled results show remaining controller CPU
   contention, raise the shared CPU request from `100m` toward a measured
   value, initially evaluating `1`, while keeping the `2`-CPU limit. Update all
   controller templates and worker resource-preflight formulas together. Do
   not pin cores, add nodes, or reduce replica access to idle CPU. A live A/B
   gate requires separate approval and must show resource fit, no serving
   regressions/restarts, and unchanged Pure/Kernel behavior.

Each phase ends with its focused suite, the full Hybrid selection, relevant
frozen Exact regressions, compilation, applicable offline Kustomize renders,
and `git diff --check`. Phase 1 is the next authorized planning handoff; later
phases must not be pulled forward before the preceding acceptance gate passes.


### Hybrid optimization Phase 1 complete locally

Completed: 2026-08-16. Controller-side Kubernetes discovery and flow-generator
HTTP clients now persist across slots and close with the finite controller.
The flow-generator starts and closes one asynchronous first-forwarder client
pool through its FastAPI lifespan. Construction failure, normal completion,
slot failure, application shutdown, repeated closure, and use-after-close have
explicit ownership behavior. Direct non-ASGI executor calls retain their
historical per-call lifecycle.

Focused tests prove two-slot reuse, exact enabled footprint message totals,
belief continuity, application startup/shutdown, failed-slot cleanup, and
unchanged direct-call behavior. All 312 Hybrid tests pass in memory-bounded
groups, the established 188 frozen Exact regression selection passes, all
seven Hybrid Kustomize overlays render offline, changed Python compiles, and
`git diff --check` passes. No cluster, Job, workload, image, traffic, generated
trace, or CSV was changed. These are lifecycle/parity results, not live speed
evidence.

The next ordered work is Phase 2 only: expose a pure process-safe evaluator for
one independent focal lookahead candidate, retain the serial production path,
and prove canonical serial/two-process equality before Phase 3 can activate a
controller-lifetime pool.


### Hybrid optimization Phase 2 complete locally

Completed: 2026-08-16. The deterministic lookahead implementation now has one
top-level picklable task/evaluator/outcome boundary per independent focal
candidate. Tasks freeze every required current input and retain the candidate's
canonical index; workers own private state and policy caches, execute dependent
future-flow projections sequentially, and return complete success or dead-end
accounting. Decision assembly restores canonical order before the unchanged
strict-improvement and first-on-tie rule. Unexpected worker errors retain their
candidate index and action.

Production remains serial. The two-process path is reachable only through a
private import-safe validation method with a caller-owned executor. No pool was
added to the controller, runner, CLI, Job, launcher, or automatic lookahead
path, and existing MC behavior is unchanged.

The focused Phase 2/lookahead/MC group passes 46 tests. The complete Hybrid
suite passes 321 tests in memory-bounded groups, and the established 188 frozen
Exact regressions pass. Changed Python compiles, all seven Hybrid Kustomize
overlays render offline, and `git diff --check` passes. No live cluster, image,
Job, workload, or traffic operation occurred, and no speed improvement is
claimed.

The next ordered phase is Phase 3: after separate authorization, give the
finite controller one bounded two-process pool, reuse it across focal decisions
and slots, and activate only this proven independent-candidate boundary with
lifecycle and full-result parity gates. Phase 4 CPU priority remains deferred.


### Hybrid optimization Phase 3 complete locally

Completed: 2026-08-16. The finite Kernel lookahead controller now creates one
spawn-isolated two-process pool, reuses the same executor and worker processes
across all sequential focal flows and completed slots, and closes the pool
before its persistent HTTP clients at controller exit. Every task continues to
use the Phase 2 immutable indexed branch boundary and a private policy/cache.
Pure callers remain serial unless the internal executor boundary is supplied.

Focused tests prove full-slot serial/parallel equality, one map per sequential
real focal flow, identical worker PIDs across two slots, fresh belief transfer,
canonical decision equality, task-failure propagation before traffic, normal
shutdown with no remaining children, lifecycle evidence compatibility, and no
lookahead pool in manual MC mode. The complete Hybrid suite passes 325 tests in
memory-bounded groups; the established 188 frozen Exact regressions also pass.
Changed Python compiles, all seven Hybrid Kustomize overlays render offline,
and `git diff --check` passes.

No cluster, image, Job, workload, traffic, repository experiment trace, or CSV
output was created or modified. These local gates do not establish a speedup.
The next action is a separately approved clean finite-controller live gate:
build/load the changed controller image, verify exactly two stable lookahead
children across slots and none after Job completion, confirm Pure/Kernel
semantic parity and serving non-regression, and compare wall time. Phase 4 soft
CPU priority remains conditional on that evidence and is not implemented.


### Hybrid optimization Phase 3 live gate complete

Completed: 2026-08-16. After explicit user approval, only the changed controller
image was rebuilt and loaded, and the existing dedicated `ibg-hybrid` cluster
was retained. The user-authorized topology changed from 30x3x15 to 15x3x8 at
profile seed 50; ordinal-prefix Pods 0--7 and the flow generator retained their
UIDs and zero restarts, while removed ordinals 8--14 were the only serving Pods
deleted by the bounded scale-down.

The explicit-lookahead Job completed three slots at root seed 2050. Every slot
reported the fixed two-worker lifecycle/version/active-child contract, exact
Pure/Kernel replay parity, belief chaining, complete placement before one
request, 30 selected observations, 15 measured pairs, and worker-only Ready
replicas. Worker PIDs 22 and 25 persisted across all slots. The Job exited zero;
no controller container remained. Slot metric times were 10.150, 7.545, and
8.546 seconds, but no speedup is claimed without a matched serial baseline.

The validated trace is
`runs/ibg-hybrid-experiment-20260816T105745.330728Z.jsonl`. Changed Python
compiles, all seven offline overlays render, and `git diff --check` passes after
the live gate. No code correction was required, so the already-passing focused,
325-Hybrid, and 188-Exact local regression results remain the applicable code
gate. Phase 3 is complete. Phase 4 CPU priority remains conditional and needs
new explicit authorization.


### Hybrid optimization Phase 4 complete locally

Completed: 2026-08-21. All seven retained finite-controller Job templates now
request one CPU, retain their two-CPU limit, and retain their 256-MiB/1-GiB
memory boundary. The worker resource preflight now includes 1000 millicpus for
the future controller and still fails before mutation against actual worker
allocatable CPU or memory. Exact-fit CPU/memory admission and independent CPU
and memory rejection are covered explicitly.

Focused Phase 4 plus Phase 3 lifecycle verification passes 15 tests. The
complete Hybrid suite passes 331 tests in memory-bounded groups, and the
established frozen Exact selection passes 188 tests. Changed Python compiles,
all seven Hybrid Kustomize overlays render offline, and `git diff --check`
passes. No live cluster, node, image, Job, Pod, workload, or traffic mutation
occurred during local implementation.

One CPU is a soft shared request, not exclusive or pinned capacity. No service
resource, topology, node selector, process pool, algorithm, seed, jitter,
learning, utility/SLA, telemetry, pair latency, footprint, route, or scheduling
behavior changed, and local tests do not establish faster slots. The remaining
gate is read-only live preflight followed by a separately approved matched
100m-versus-1-CPU controller A/B with identical code, serving Pods, dimensions,
seeds, first slot, flow order, and iteration count.


### Hybrid end-to-end SLA work ordered

Planned: 2026-08-21.

1. Authorized now: migrate the existing Hybrid SLA violation count to strict
   raw end-to-end latency above the unchanged 80-ms threshold. Rename the
   active metric to `end_to_end_sla_violations`, update trace/console/CSV and
   Pure/Kernel parity boundaries, write `end_to_end_sla_violations.csv` without
   modifying historical `sla_violations.csv`, and preserve all non-SLA
   semantics.
2. Deferred until a later explicit user instruction: add the quality metric
   `end_to_end_sla_excess_ms` as the per-timeslot sum of positive end-to-end
   excess above 80 ms, with its own wide-layout Hybrid CSV.

The second step must not be pulled into the first implementation. Neither step
changes placement, learning, belief updates, jitter, physical-only realized
utility, the raw end-to-end reference utility, or pair measurement itself.


### Hybrid end-to-end SLA count complete locally

Completed: 2026-08-21. Step 1 now counts strict raw end-to-end latency above
80 ms under the explicit `end_to_end_sla_violations` field. The count flows
through slot metrics, Pure/Kernel replay, v2 JSONL evidence, human console
output, and the isolated `end_to_end_sla_violations.csv` wide-layout report.
Trace persistence recomputes the count from complete raw per-flow values and
rejects inconsistent or legacy physical-only evidence.

Focused semantic/trace/CSV/Phase-3 parity verification passes 65 tests. The
complete Hybrid suite passes 334 tests in memory-bounded groups, and the
unchanged frozen Exact selection passes 188 tests. Changed Python compiles,
the launcher help path succeeds, all seven offline Kustomize overlays render,
and `git diff --check` passes. No live cluster, image, Job, Pod, workload,
traffic, generated trace, or CSV was changed.

Step 2 remains deferred. `end_to_end_sla_excess_ms` and its quality CSV have
not been implemented and require a new explicit user instruction. Because the
controller runner and slot contract changed, the next live use must build the
updated controller image rather than relying on the pre-change image.


### Hybrid end-to-end SLA excess complete locally

Completed: 2026-08-21. The deferred second SLA step is now implemented.
`end_to_end_sla_excess_ms` is the per-timeslot sum of unrounded positive raw
end-to-end latency excess above 80 ms. It is present in slot metrics, complete
Pure/Kernel parity, completed Kernel JSON evidence, explicit console output,
and the opt-in wide-layout `end_to_end_sla_excess_ms.csv`. Active traces are
versioned `ibg-hybrid-experiment-jsonl-v3` and validate count and excess against
the same complete raw per-flow map.

Focused SLA/trace/CSV/Phase-3 verification passes 81 tests. The complete
Hybrid suite now collects and passes 350 tests in three memory-bounded groups
(143, 111, and 96). The established frozen Exact selection passes 188 tests
(84 and 104). Changed Python compiles, launcher help and imports succeed, all
seven offline Hybrid Kustomize overlays render, and `git diff --check` passes.

The violation count and 80-ms threshold are unchanged. Physical-only realized
utility, raw end-to-end reference utility, placement, learning, beliefs,
telemetry, scheduling, resources, HTTP and process lifecycles, and frozen Exact
behavior are unchanged. Historical traces and `sla_violations.csv` were not
rewritten. No cluster, node, image, Job, Pod, workload, traffic, generated
trace, or generated CSV was mutated. Because controller runtime code changed,
the next live run must normally rebuild the controller image before later use
of `--skip-build`.


### Hybrid tc/netem implementation and local verification complete

Completed: 2026-08-22. The two-step local task is complete. Step 1 added the
default-off production CLI, strict delay/jitter validation, Exact-compatible
replica-`eth0` qdisc command, bounded `NET_ADMIN` init container, conditional
offline image build/load validation, dynamic three-StatefulSet patches,
configuration-drift detection, deliberate replica rollout handling, `--runs`
propagation, and complete top-level `ibg-hybrid-netem-v1` lifecycle
provenance. No algorithm or metrics schema was changed.

Step 2 focused verification passes 94 tests. The complete Hybrid suite passes
372 tests in three memory-bounded groups (153, 123, and 96), and the established
frozen Exact selection passes 188 tests (84 and 104). Changed Python compiles,
launcher help/import checks pass, all seven offline Hybrid Kustomize overlays
render with default-disabled manifests, and `git diff --check` passes.

These gates establish local implementation and regression behavior only. No
image was built or loaded, no kind node or container was started, and no
cluster, StatefulSet, Pod, Job, workload, or traffic was mutated. User-run
matched enabled/disabled experiments remain the next action and must normally
build the new netem image before later `--skip-build` reuse. No live robustness
or performance result is claimed.


### Hybrid equilibrium threshold updated

Completed: 2026-08-22. The user-directed active Hybrid equilibrium threshold
is now strict `<0.04` per belief entry instead of `<0.033`. Focused Hybrid
verification confirms the slot metric uses the new threshold. This is only a
stopping-time adjustment; no belief update, algorithm, placement, learning,
utility/SLA, telemetry, runtime, or frozen Exact behavior changed. No live
validation or resource mutation occurred.


### Hybrid control-plane wall-time measurement complete locally

Completed: 2026-08-22. The existing CSV-gated controller footprint now records
validated per-slot discovery, admission, feedback, active-control, and
data-plane-wait wall times under `ibg-hybrid-control-plane-wall-time-v2` and
exports five corresponding wide-layout CSVs. Existing payload/message
accounting is preserved. No CPU or cgroup measurement was added, and the
experiment trace remains v3 because metrics and Pure/Kernel semantic parity are
unchanged.

Focused verification passes 81 tests. The complete Hybrid suite passes 376
tests in three memory-bounded groups (147, 103, and 126), and the established
frozen Exact selection passes 188 tests (84 and 104). Changed Python compiles,
launcher and summary help/import checks pass, all seven offline overlays render,
and `git diff --check` passes. No cluster, node, container, image, Job, Pod,
workload, traffic, trace, or CSV was mutated during local implementation.

The next ordered gate is a user-run five-iteration baseline using the current
one-CPU request, two-CPU limit, and two-process lookahead pool. Only after that
baseline is preserved should a separately implemented and verified candidate
resource/pool configuration be run with otherwise identical inputs. Because
controller runtime code changed, the baseline must normally rebuild before
later `--skip-build` reuse.


### Hybrid four-process CPU candidate complete locally

Completed: 2026-08-22. After the five-slot wall-time baseline showed admission
accounting for approximately 15.32 seconds versus 177 ms of selected-route
wait, the authorized candidate increased deterministic lookahead from two to
four persistent worker processes and changed every controller Job from a
one/two-CPU request/limit to two/four CPUs. Controller memory and all serving
resources remain unchanged; resource preflight now includes a 2000m controller
request.

Focused resource/lifecycle/parity verification passes 80 tests. The complete
Hybrid suite passes 376 tests in three bounded groups (147, 103, and 126), and
the established frozen Exact selection passes 188 tests (84 and 104). Changed
Python compiles, launcher checks pass, all seven offline overlays render, and
`git diff --check` passes. No live resource or generated evidence was mutated
during implementation.

The remaining gate is the user-run matched five-slot candidate. Only the
controller image should be rebuilt and loaded before a `--skip-build` run so
the existing replica and flow-generator Pods are not deliberately rolled by
the validation procedure. No speedup is established until the new wall-time
trace is compared with the baseline.


### Hybrid optional production parity replay complete locally

Completed: 2026-08-22. Production `run` and `--runs N` now accept
`--parity-replay 0|1`, defaulting to zero. The finite controller skips the
expensive second serial scheduling calculation when disabled and emits
unambiguous “not performed” evidence. Explicitly enabled replay retains the
existing Pure/Kernel semantic comparison and fails closed on disagreement.
The infrastructure-oriented `run-small` validation gate remains unchanged and
continues to require parity.

Focused lifecycle/trace/pool/netem verification passes 63 tests. The complete
Hybrid suite passes 383 tests in three bounded groups (154, 103, and 126), and
the established frozen Exact selection passes 188 tests (87 and 101). Changed
Python compiles, launcher help/import checks pass, all seven offline Hybrid
overlays render, and `git diff --check` passes.

No Docker, kind, Kubernetes, image, Job, Pod, traffic, trace, or CSV mutation
occurred. The runtime change requires a normal controller-image rebuild before
the option is available live. Local verification establishes control and
semantic preservation; it does not establish a new live wall-time result.


### Hybrid netem missing-image correction complete

Completed: 2026-08-22. A user `--skip-build --netem 1` preflight exposed that
the new netem image was absent and its Dockerfile depended on an unavailable
historical Exact base tag. The image is now self-contained from already-local,
digest-pinned kind-node artifacts and no longer requires that Exact tag or an
online package installation.

Focused netem/offline/lifecycle verification passes 67 tests; changed Python
compiles, all seven Hybrid overlays render, and `git diff --check` passes. The
3.28-MB image built with `--network=none`, passed an ephemeral 7-ms/3-ms normal
netem command, and was loaded into both retained `ibg-hybrid` nodes. No
manifest, StatefulSet, Pod, controller Job, or experiment traffic was started
by the correction.

## MILP Kernel large-profile persistence repair

Status: complete locally on 2026-08-23.

The 40-flow/3-stage/20-replica synthetic profile exposed the Kubernetes
client-side-apply annotation limit before replica rollout. The launcher now
uses server-side apply only for `milp-experiment-profile`. A server-side dry
run accepted the exact requested 40x3x20 profile. The next user-owned action
is to rerun the same MILP command; no retry, rollout, or solver run was
started by this repair.

### MILP large-solve controller-memory repair

Status: complete locally on 2026-08-23. The first 40x3x20 controller Job was
OOM-killed at its former 1-GiB hard limit before traffic. The finite controller
Job now requests 8 GiB and has a 16-GiB memory limit; CPU remains 100m/2 CPUs
and every serving resource is unchanged. The next user-owned action is a
single retry of the same 40x3x20 command, with no image rebuild required.

### MILP intentional scale-down profile-validation repair

Status: complete locally on 2026-08-23. A user-requested 20-to-5 replica
scale-down was incorrectly rejected because validation inspected replicas
6--20 even though the rollout would remove them. Validation now covers only
the retained 1--5 ordinal profiles. The exact current 20-to-5, profile-seed-50
preflight passes read-only; the next user-owned action is the 10x3x5 retry.

### MILP synthetic planning-link v2

Status: complete locally on 2026-08-23. New synthetic-scale runs use a
versioned deterministic 65.000--74.999-ms planning-coefficient range at
0.001-ms resolution. The old 0.500--5.499-ms v1 generator remains available
for historical reproduction. This changes only the MILP objective input and
profile fingerprint; it does not add delay to Kubernetes traffic. The next
user-owned action is a fresh synthetic-scale run with the desired dimensions.

## Greedy final-baseline implementation roadmap

Status: planned on 2026-08-24. Phase 0 contract work is complete; no policy,
runtime, or live operation has begun. Phases proceed in order; each gate must
be recorded before the next phase.

### Greedy Phase 0: freeze the baseline and characterize the legacy folder

Status: complete locally on 2026-08-24.

Recommended intelligence level: `high`. Contract extraction is consequential,
but this phase is bounded to documentation, legacy characterization, and frozen
fixtures rather than new runtime behavior.

- Phase preparation (when related material exists): reread the four current
  handoffs and study `misc/vesal_tex.tex`, the bounded relevant portions of
  `Greedy/*.py`, active policy-neutral IBG/Hybrid contracts, and their focused
  tests. Record which legacy items are reusable, reference-only, or excluded
  before changing code; do not read generated result files wholesale.
- Convert the architecture and decision records into executable contract
  fixtures for `pure-greedy-budgeted-l2-v1`, exactly two distinct selected
  stages, `K-2` bypasses, no rejection, canonical joint-action tie-breaking,
  selected-only learning, current Hybrid-compatible metrics, 80-ms raw
  end-to-end SLA, and strict `<0.04` equilibrium.
- Require explicit positive flow, stage, and per-stage replica dimensions with
  no topology defaults. Freeze `10 flows / 3 stages / 5 replicas per stage`
  only as the explicitly supplied canonical matched-comparison shape, and
  exactly one run per launcher invocation. The target has no `--runs`
  repetition option.
- Characterize the current `Greedy/` files with bounded tests or tiny examples:
  import-time execution, hard-coded dimensions/repetitions, active two-stage
  budgeted selection, replica-zero behavior, legacy random streams, formulas,
  and direct CSV writes.
- Classify every legacy function as reuse-with-test, reference-only, or retire.
  Treat the historical `range(1,30)` loop solely as a retired import hazard;
  do not run its 29 executions of the 50-flow, 3-stage,
  80-replicas-per-stage driver or generate legacy result files.
- Freeze canonical input/output schemas, deterministic flow order and ties,
  `ceil(N/M)` admission feasibility, per-slot selected-observation/pair counts,
  and the Greedy/Hybrid compatibility matrix.

Gate: a reviewed contract and characterization test set resolve every semantic
ambiguity without changing `IBG/`, `IBG_Hybrid/`, MILP, Kubernetes, or results.

Phase 0 result, corrected after the user's budget clarification:
`Greedy/phase0_contract.py` now contains executable topology, budgeted joint
action, sequential-load, two-hop slot, public-input, excluded-feature,
active-semantics, and Greedy/Hybrid compatibility fixtures. The frozen version
is `pure-greedy-budgeted-l2-v1`: every flow selects exactly two distinct stages
and bypasses `K-2`; planning-link cost remains excluded from selection.
The executable canonical matched-comparison configuration is explicitly
10 flows, 3 stages, and 5 replicas per stage; it is not a default. The
invocation contract requires explicit dimensions and permits exactly one run
with no `--runs` mode. The smaller hand-checked slot fixture remains test-only.
`Greedy/legacy_characterization.py` statically audits all seven historical
Python files without importing them and classifies all 38 top-level callables
and `Replica` methods as 5 reuse-with-compatibility-test, 14 reference-only,
and 19 retire. Bounded tests demonstrate the active two-stage route, dormant
replica-zero result and last-load mutation, retired 29-execution dimensions,
mixed unseeded global random streams, historical inverse-latency utility,
15-ms SLA excess, strict `<0.06` equilibrium, and direct CSV behavior without
running the experiment or writing results. The 29-execution finding is retired
legacy characterization and does not influence the target launcher lifecycle.

The corrected Phase 0 gate passed with 13 Greedy tests and 17 selected existing
IBG/Hybrid compatibility tests. The new modules import silently in a clean
temporary directory and create no files. No frozen source, Kubernetes resource,
generated evidence, or legacy file changed. Phase 1 is now the next action but
has not started.

### Greedy Phase 1: implement the pure policy core

Status: complete locally on 2026-08-24.

Recommended intelligence level: `xhigh`. This phase freezes the defining
Greedy mathematics, feasibility, tie, load-update, and no-rejection behavior;
subtle errors would invalidate every downstream comparison.

- Phase preparation (when related material exists): study the Phase 0
  fixtures, legacy Greedy scoring helpers, `IBG_Hybrid/expected_utility.py`,
  the reusable memoization/identity portions of `IBG_Hybrid/policy.py`, and the
  smallest relevant policy tests before applying this phase. Revalidate the
  phase-relevant rows of `greedy-hybrid-matched-comparison-v1` against current
  Hybrid code and record exact source versions. Explicitly list why lookahead
  action enumeration and Monte Carlo code are not reused.
- Make `Greedy` import-safe and add typed configuration, replica identity,
  load-state, admission, decision, and policy-result contracts.
- Make typed configuration require explicit positive `N`, `K`, and `M`, with
  `K>=2`; do not define topology defaults.
- Add a typed, versioned matched-comparison configuration fixture that
  distinguishes required common inputs/resources from intentional policy-only
  differences and rejects an incomplete or mismatched required row.
- Precompute immutable canonical replica identities grouped by stage and the
  canonical `L=2` action ordering once per configuration. Add
  controller-lifetime deterministic utility memoization by exact
  `(belief tuple, projected load)` with a measured bound or explicit clear
  policy and cached/uncached equality tests. Do not copy Hybrid pruning,
  activation, lookahead/MC structures, Pandas grids, or stochastic utility
  samples.
- Implement exhaustive immediate joint-action argmax for positive `N`, `M`,
  and `K>=2`. Score each feasible two-stage action by the sum of its projected
  expected stage utilities, apply both load updates sequentially by flow, use
  canonical action ties, choose the best non-positive action, and fail
  explicitly when no complete `L=2` action is feasible.
- Keep expected-utility calculation deterministic and pure; inject randomness
  only at the outer simulation/observation boundaries and never use global
  Python or NumPy RNG state in the policy.
- Add a transparent exhaustive/reference calculation for small fixtures and
  tests proving the policy never calls Hybrid pruning/lookahead/MC or link
  scoring.

Gate: silent imports, dimension/property tests, hand-computed fixtures,
tie/negative/capacity/error cases, reproducibility, compilation, and frozen
Exact/Hybrid regression selections pass.

Phase 1 result: added import-safe `Greedy/contracts.py`,
`Greedy/expected_utility.py`, `Greedy/policy.py`, `Greedy/comparison.py`, and a
minimal package marker. Configuration requires explicit `N`, `K`, and `M`;
10x3x5 exists only as the typed canonical matched-comparison fixture. The
policy precomputes canonical identities/action ordering, exhaustively scores
all feasible complete L=2 actions at projected loads, commits two loads per
real flow, preserves exact canonical ties and non-positive selection, and
fails only on empty complete feasibility. Its Greedy-owned adapter uses the
active deterministic IBG latency utility, and its exact-key 4096-entry bounded
LRU is covered by cached/uncached equality and clear/eviction tests.

The Phase 1 Hybrid audit used repository HEAD
`19229c274038db440f3cfdd62ed2102ea4c2c545` and exact locations recorded in
`ARCHITECTURE.md`; no Phase 1 comparison resource or admission value drifted.
Hybrid immutable identity, Ready/capacity, expected-utility, precomputation,
memoization, and strict-tie patterns were adapted behind Greedy ownership.
Hybrid pruning, activation, planning-link scoring, lookahead/MC continuations,
policy/depth/worker options, and process pools were not reused.

The complete Phase 0/1 Greedy suite passes 34 tests, 17 selected unchanged
latency/Hybrid semantic tests pass, and the focused unchanged Hybrid public
Ready/capacity test passes. Silent clean-directory imports, changed-Python
compilation, and `git diff --check` pass. No experiment loop, runtime adapter,
controller, container, manifest, launcher, JSONL/CSV writer, Docker/Kubernetes
command, traffic, or live mutation was added or run. Phase 2 is next and has
not started.

### Greedy Phase 2: build the stateful pure experiment loop

Status: complete locally on 2026-08-25.

Recommended intelligence level: `xhigh`. Belief continuity, selected-only
learning, separated randomness, stopping, metrics, and replay must remain
consistent across multiple dependent slots.

- Phase preparation (when related material exists): study the accepted
  Greedy policy fixtures plus the phase-relevant portions of
  `IBG_Hybrid/runner.py`, `simulation.py`, `slot_contracts.py`, `oracle.py`,
  and their focused Phase 0--2 tests. Map only policy-neutral slot, learning,
  metric, timing, and replay contracts before editing, and refresh their rows
  in the matched-comparison matrix from the current implementation.
- Add one complete pure slot: seeded flow order, budgeted `L=2` greedy
  placement, explicit `K-2` bypasses, final-load accounting, selected-only
  observations, belief update, metrics, equilibrium, and retained beliefs
  across iterations.
- Reuse or adapt only policy-neutral active contracts for latency, separated
  jitter, likelihood, physical-only realized utility, measured-pair reference
  metrics, end-to-end SLA count/excess, fairness, and timing.
- Add a finite pure experiment runner that stops on equilibrium or exactly
  `--max-iterations`, with no file or console side effects in the policy core.
- Execute exactly one experiment per runner invocation; do not add an outer
  repetition loop or `--runs` mode.
- Add dependency-injected monotonic timing seams for placement and feedback,
  plus a captured-input serial oracle. The oracle is mandatory in validation
  but is not run a second time by an ordinary production slot.
- Implement the Hybrid-compatible root/flow-order seed derivation and a shared
  deterministic keyed physical/observation schedule for paired fixtures. Prove
  common keys produce equal draws, route-dependent unused draws stay outside
  learning, and no stochastic input enters policy selection.
- Validate exactly `N` two-hop routes, `2*N` selected observations, and `N`
  selected-pair slots; bypassed and idle replicas emit no learning sample.

Gate: deterministic multi-slot fixtures prove belief continuity, selected-only
learning, metric arithmetic, stopping behavior, arbitrary `K>=2` stage counts, and no
legacy formula or global-RNG leakage.

Phase 2 result: added import-safe `Greedy/slot_contracts.py`,
`Greedy/simulation.py`, `Greedy/learning.py`, `Greedy/metrics.py`,
`Greedy/runner.py`, `Greedy/oracle.py`, and `tests/test_greedy_phase2.py`.
One pure slot preserves the Phase 1 policy result, validates `N` placements,
`2*N` selected final-load observations, `N` selected-pair records, and `K-2`
bypasses per flow, then applies selected-only learning and active separated
metrics. One finite experiment retains beliefs/policy cache across slots and
stops on strict equilibrium or exactly the explicit positive iteration limit.

Flow ordering reproduces active Hybrid's versioned root/slot derivation. The
component schedule has immutable experiment/slot/flow/stage/replica/load/type
keys and separate local physical/observation generators. Canonical experiment
ID 1 produces the exact active Hybrid component seed bytes; other pure fixture
IDs are explicitly namespaced. The sorted hidden-state/observation-seed map is
fingerprinted independently, and profile seed enters neither order nor draws.

The explicit captured replay path consumes frozen observations/pairs without
redrawing and checks an independently enumerated immediate-policy reference,
cached/uncached placements, loads, beliefs, and metrics. Ordinary slot
execution calculates once and does not import or invoke replay. The Phase 2
Hybrid audit used repository HEAD
`19229c274038db440f3cfdd62ed2102ea4c2c545`; exact locations/blob versions and
the canonical-experiment source-shape clarification are recorded in
`ARCHITECTURE.md`. No active semantic constant drifted.

The complete Phase 0--2 Greedy suite passes 58 tests and the selected unchanged
IBG/Hybrid compatibility suite passes 24 tests. Silent clean-directory
imports, changed-Python compilation outside the workspace, and
`git diff --check` pass. No HTTP/controller, container, manifest, launcher,
JSONL/CSV, Docker, kind, kubectl, cluster, traffic, commit, or push work was
performed. Phase 3 is next and has not started.

### Greedy Phase 3: add Greedy-owned Kernel adapters and controller

Status: complete locally on 2026-08-25.

Recommended intelligence level: `xhigh`. Persistent client ownership,
concurrent route execution, sequential policy state, telemetry correlation,
failure cleanup, and Pure/Kernel parity cross several asynchronous boundaries.

- Phase preparation (when related material exists): study
  `IBG_Hybrid/kernel_kubernetes_discovery.py`, `kernel_controller.py`,
  `kernel_route_execution.py`, `kernel_flow_generator.py`, the shared
  processor/forwarder services, and focused infrastructure/lifecycle tests.
  Document every reused lifecycle, pool, timeout, concurrency, request-count,
  and close-on-failure rule before implementing the Greedy-owned adapters.
  Populate those exact current values in the comparison matrix before editing.
- Add Greedy discovery, controller configuration, route execution, flow-
  generator, processor/forwarder adapters, and a finite controller CLI behind
  the pure runner's ports.
- Give the finite controller one persistent synchronous discovery client and
  one persistent synchronous flow-generator client across all slots. Give the
  flow-generator lifespan one persistent asynchronous first-forwarder pool;
  retain import-safe one-call fallback only for direct test callers and close
  every owned client exactly once on success, partial construction, or error.
- Preserve the private processor on 8081, public two-worker forwarder on 8080,
  selected two-hop routes, one concurrent flow-generator request per slot,
  readiness filtering, identity/load correlation, and fail-whole-slot errors.
- Keep processor hidden state and observation seeds outside controller inputs;
  prove traffic and telemetry cannot influence the already-completed choice.
- Add a captured-observation Pure/Kernel replay path for semantic validation,
  not as a policy option.
- Keep the `N` already-selected routes concurrent but all placement/load
  decisions sequential. Add controller/discovery, admission/dispatch,
  data-plane-wait, and feedback timing boundaries without changing the request
  count, payload, timeout, or failure contract.

Gate: local service tests cover health/warmup, budgeted two-hop routing,
arbitrary valid stage pairs, bypass absence, concurrency, pair counts, failure
propagation, selected-only telemetry, and
zero-drift pure replay without Kubernetes.

Phase 3 result: added Greedy-owned public Kernel contracts, exact Ready
discovery, arbitrary-K two-hop route/telemetry schemas, concurrent route
execution, flow-generator/processor/forwarder service boundaries, public
controller configuration, a finite stateful controller, and explicit captured
Pure/Kernel replay. The controller makes one unchanged sequential policy call
per slot before traffic, sends one complete slot request, and the generator
sends exactly one concurrent first-forwarder request per flow while preserving
ordered hops and complete `K-2` bypass absence.

One persistent synchronous discovery client and one persistent synchronous
flow-generator client span the finite controller. One persistent asynchronous
first-forwarder pool spans the flow-generator lifespan; direct executor tests
alone may use a one-call ephemeral client. Public forwarders retain distinct
local-processor and 30-second downstream clients. Normal completion,
construction/start failure, request/slot failure, and repeated shutdown have
idempotent exactly-once cleanup coverage. Active matched timeouts remain
10/30/10 seconds for discovery, controller-to-generator, and selected-route
requests.

Complete telemetry validation precedes selected-only learning and belief
commit. Phase 2 physical/observation separation, exact likelihood, physical
realized utility, raw pair/reference metrics, strict raw 80-ms SLA and
unrounded excess, Jain fairness, strict `<0.04` equilibrium, and finite
one-experiment stopping remain unchanged. Captured replay performs no HTTP or
stochastic redraw and ordinary controller execution does not invoke it.

The audit used repository HEAD
`19229c274038db440f3cfdd62ed2102ea4c2c545`; exact Phase 3 Hybrid/shared
source locations, blobs, classifications, resources, payload semantics,
timeouts, worker/client ownership, and request counts are recorded in
`ARCHITECTURE.md` and `Greedy/comparison.py`. No relevant value drifted.

The complete Greedy Phase 0--3 suite passes 102 tests. The focused unchanged
compatibility selection passes 32 tests. Clean-directory silent imports,
changed-Python compilation outside the workspace, and `git diff --check`
pass. No image, manifest, launcher, JSONL/CSV, Docker/kind/kubectl, network, or
live-cluster work was performed. Phase 4 is next and has not started.

### Greedy Phase 4: create isolated images and Kubernetes resources

Status: complete locally on 2026-08-25.

Recommended intelligence level: `high`. The policy is unchanged and the work
is bounded by established image, manifest, RBAC, security, resource, and
offline-render contracts.

- Phase preparation (when related material exists): study the active
  `deploy/hybrid-kubernetes` Dockerfiles/base manifests, the one-worker kind
  config, offline-wheelhouse checks, resource-preflight code, and focused
  manifest/security tests. Extract policy-neutral patterns only; establish
  Greedy names and the Hybrid-matched Greedy controller resource envelope
  explicitly. Read values from current manifests and focused render tests;
  fail preparation if they disagree with the recorded matrix.
- Add Greedy-owned lean service/controller images with reproducible offline
  dependency inputs and no Hybrid solver/MC dependencies in the service image.
- Add the `greedy-testbed` namespace, namespace-scoped discovery RBAC, one
  flow-generator Deployment, generated headless Service/StatefulSet resources
  for contiguous stages, generated profile/controller ConfigMaps, and one
  finite controller Job outside the long-running base.
- Add the exact one-control-plane/one-worker kind definition and worker-only
  selectors for every Greedy workload. Preserve current accepted serving
  resources, probes, process counts, and keep-alive boundaries.
- Do not copy Hybrid's four-process controller. Give the sequential Greedy
  controller the same comparison resources as Hybrid—request `2 CPU/256Mi`,
  limit `4 CPU/1Gi`—and include them in allocatable-versus-request worker
  preflight. Preserve the current Hybrid serving resources exactly. Reject
  one-sided resource changes unless a new matched A/B profile is authorized.
- Add offline Kustomize/render and security checks for image ownership,
  service-account token scope, non-root containers, and absence of foreign
  namespaces/resources.

Gate: all supported static examples render and parse offline; tests reject
wrong namespace, labels, node placement, RBAC, image, profile mounts, stage
gaps, and a controller Job applied before serving readiness. No live cluster is
required or authorized by this phase.

Phase 4 result: `Greedy/kernel_infrastructure.py` now renders deterministic
dependency-free JSON/YAML for arbitrary explicitly supplied valid dimensions.
The long-running set contains only the Greedy namespace, namespace-scoped Pod
get/list RBAC, private runtime and public controller ConfigMaps, one
flow-generator Service/Deployment, and one headless Service/StatefulSet pair
per contiguous stage. The finite controller Job is a separate render that
requires an exact replica and flow-generator Ready token. Every workload is
worker-only, non-root, capability-dropped, read-only-root, and uses service
account tokens only where controller discovery requires one.

`deploy/greedy-kubernetes/` owns separate offline service/controller
Dockerfiles, exact Python 3.12/Linux AMD64 wheel locks/manifests, the explicit
canonical 10x3x5 render input, and the one-control-plane/one-worker kind
definition. The service image excludes Greedy policy/controller, Hybrid,
MILP, and legacy Greedy files; the sequential controller image excludes
service entry points and Hybrid policy/MC/process-pool sources. The matched
private/public/flow-generator/controller resources remain
`50m/128Mi -> 1 CPU/768Mi`, `25m/128Mi -> 1 CPU/256Mi`,
`50m/128Mi -> 1 CPU/768Mi`, and `2 CPU/256Mi -> 4 CPU/1Gi` respectively.
Worker preflight includes all serving requests plus the controller Job.

The Phase 4 audit used HEAD
`f2e0065204570d9631f26953c94729b451ff92b5`; exact locations, blobs, and
reuse/adapt classifications are recorded in `Greedy/comparison.py` and
`ARCHITECTURE.md`, with no relevant drift. The complete Greedy Phase 0--4
suite passes 117 tests and the focused unchanged static Hybrid compatibility
selection passes 21 tests. Image-source isolation, clean-directory imports,
offline example rendering/parsing, externalized bytecode compilation, and
`git diff --check` pass. No Docker, kind, kubectl, network, cluster, traffic,
launcher, JSONL, or CSV operation was performed. Phase 5 is next and has not
started.

### Greedy Phase 5: implement persistent lifecycle and dynamic topology

Status: complete locally on 2026-08-25. Phase 6 completed separately on
2026-08-26; Phase 7 is now next.

Recommended intelligence level: `xhigh`. Reconciliation must safely handle
bootstrap, no-op reuse, interrupted transitions, scale up/down, profile order,
resource refusal, and retained-Pod preservation without targeting other work.

- Phase preparation (when related material exists): study
  `scripts/run_hybrid_kernel_phase4.py`,
  `IBG_Hybrid/kernel_rollout.py`, runtime-profile expansion, dynamic-topology
  evidence, and the smallest skip-build/rollout tests. Write down applicable
  command ordering and the Greedy-specific differences for arbitrary stages;
  refresh CLI, rollout, Ready, build-state, and warm-state comparison rows from
  the active Hybrid launcher before editing.
- Add `scripts/run_greedy_kernel.py` with `run`, read-only `preflight`, and
  explicit `cleanup` actions. Production `run` requires explicit positive
  `--flow`, `--stage`, and `--replica` values, requires positive
  `--max-iterations` and nonnegative `--profile-seed`, and
  supports
  `--rollout-batch-size`, `--csv`, `--parity-replay`, and `--skip-build`.
  It creates exactly one controller Job/run and exposes no `--runs` option.
- Generate deterministic, versioned runtime profiles for any requested
  contiguous stage/replica shape and validate the deployed source before any
  transition. Keep hidden states fixed throughout one run.
- Implement flow-only reconciliation, append-only stage/replica expansion,
  bounded all-stage replica batches, safe high-ordinal replica scale-down, and
  safe highest-stage removal without contracting below two stages. Preserve
  retained Pod UIDs/restarts on the
  no-build path.
- Make equal topology/profile input a serving no-op. On normal bootstrap build
  both lean images; on a proven controller-only or service-only maintenance
  change, permit only the affected image to be rebuilt/loaded. `--skip-build`
  also skips offline-wheelhouse validation and never forces a serving restart,
  but still validates node-local image identities and reconciles state.
- Make cluster/context/namespace/image/node/resource inventory fail closed.
  Wait for both kind nodes on first bootstrap and exact Ready ordinal coverage
  after every mutation before the controller Job.

Gate: mocked command-order tests cover fresh bootstrap, equal reuse, flow-only
change, stage/replica up and down transitions, interrupted transition recovery,
resource refusal, profile drift, foreign ownership, missing images, and the
rule that `--skip-build` cannot bootstrap.

Phase 5 result: `scripts/run_greedy_kernel.py` now owns `run`, read-only
`preflight`, and explicit Greedy-only `cleanup`. The launcher keeps cluster
`greedy`, context `kind-greedy`, namespace `greedy-testbed`, and the exact
one-control-plane/one-worker inventory fail closed. It validates worker
requests before mutation, builds and loads only roles whose complete source
provenance changed, and creates exactly one controller Job only after exact
serving readiness. `--skip-build` rejects bootstrap, bypasses wheel/build/load,
validates retained local and node image identities, and does not force a
serving restart.

Greedy-owned profile and rollout modules materialize an arbitrary contiguous
`K>=2`/`M` environment, preserve every retained identity's hidden state and
observation seed, reject retained drift, and reconcile only high-suffix
replicas and highest contiguous stages. A versioned transition marker permits
safe continuation of an unambiguous interrupted supported transition; an
unmarked, noncontiguous, foreign, or otherwise ambiguous state is rejected.
Flow-only changes update public admission/controller configuration without Pod
replacement. Exact Ready coverage is required after each bounded replica or
stage mutation. Phase 5 carries validated `--csv` and `--parity-replay`
settings only; it emits no evidence and performs no replay/export.

The local gate passes 137 Greedy tests through Phase 5 and 20 focused unchanged
Hybrid lifecycle/profile/rollout compatibility tests. Import, externalized
bytecode compilation, and whitespace checks pass. All lifecycle tests use fake
executors; no Docker, kind, kubectl, network, cluster, traffic, JSONL, or CSV
operation was performed. Phase 6 is the next separately authorized phase.
That separately authorized Phase 6 is now complete below; this sentence records
the Phase 5 stopping boundary.

### Greedy Phase 6: add console, JSONL, and CSV evidence

Status: complete locally on 2026-08-26. Phase 7 is next and has not started.

Recommended intelligence level: `high`. Output work is schema-heavy but
bounded by the accepted Hybrid presentation, explicit Greedy provenance, and
golden lifecycle/CSV validation.

- Phase preparation (when related material exists): study Hybrid console,
  lifecycle persistence, CSV storage, control-plane footprint/wall-time
  summary code, launcher CLI help, and their golden/schema tests. Freeze a
  Greedy field-by-field compatibility table before changing output code. Fold
  it into the versioned matched-comparison matrix, including instrumentation
  flags and comparison-profile/source/image fingerprints.
- Match current Hybrid human output for launcher progress, initial/final belief
  tables, completed iteration metrics, and equilibrium status, using Greedy
  names and no hidden-state display.
- Emit one validated `GREEDY_SLOT_EVIDENCE=` record after every fully completed
  slot, then persist a host-side run-start/iteration/run-complete JSONL lifecycle
  under `runs/`.
- Implement `--parity-replay {0,1}` with default zero. Evidence records whether
  replay was requested and performed and records a result only when performed;
  validation commands force it on and fail closed on any mismatch.
- Implement `--csv 1` as post-validation host export to `figures/Greedy/` for
  time, end-to-end SLA count/excess, raw reference aggregate utility, fairness,
  identity-aligned belief tables, controller phase wall times, and compatible
  controller payload/message footprint. Keep default `--csv 0` JSONL-only.
- Include policy/dimension/profile/image/environment provenance and reject
  incomplete, mixed-version, arithmetically inconsistent, or duplicate-run
  evidence before writing reports.
- Persist every matched-comparison row, actual Pod resource specification,
  exact runtime-profile fingerprint, seeds/schedule versions, warm/build state,
  node allocatable resources, and actual controller CPU/RSS/throttling fields.

Gate: golden console tests, JSONL lifecycle/schema tests, atomic CSV tests,
unequal-run alignment, no-controller-volume checks, and CLI help/default/error
tests pass. Persistence must be behavior-neutral.

Phase 6 result: the finite controller now prints Greedy-labeled aligned belief
tables and completed-slot predicted, physical, raw reference, SLA, fairness,
timing, and equilibrium output. After every committed slot it emits one
validated `GREEDY_SLOT_EVIDENCE=` document. Default replay remains disabled
without a fabricated result; explicit replay recomputes the public policy,
captured selected-only learning, and metrics without HTTP or stochastic redraw
and fails closed on mismatch.

The host launcher privately projects machine evidence, persists one atomic
`run_started`/iteration/`run_completed` JSONL lifecycle, and optionally exports
the six accepted wide files plus controller phase, payload/message, CPU, RSS,
and cgroup-throttling footprint under `figures/Greedy/`. Validation covers the
complete sequential load chain, selected observations and pair records, all
utility aggregates, strict raw-latency SLA arithmetic, belief continuity,
complete matched-comparison rows, resources, source/image fingerprints, and
worker allocatable. Hidden state and stochastic seeds are excluded. Controller
Pods retain no result volume. Changed source now invalidates `--skip-build`
rather than relabeling an older image with new provenance.

The local gate passes 159 Greedy tests through Phase 6 and 35 focused unchanged
Hybrid console/replay/lifecycle/CSV/footprint compatibility checks. Clean
imports, externalized bytecode compilation, and whitespace checks pass. Tests
write output fixtures only under temporary directories. No Docker, kind,
kubectl, network, cluster, traffic, repository JSONL/CSV, or live parity action
was performed. Phase 7 local integration is the next separately scoped action.

### Greedy Phase 7: complete local integration and regression gates

Status: complete locally on 2026-08-27. Phase 8 remains separately authorized
and has not started.

Recommended intelligence level: `xhigh`. This phase must synthesize failures
across policy, state, HTTP lifecycles, manifests, topology, persistence, and
frozen-baseline compatibility without masking unrelated worktree changes.

- Phase preparation (when related material exists): reread the four current
  handoffs and the Greedy test/manifest inventory, then select the smallest
  phase-relevant frozen Exact/Hybrid compatibility groups. Re-read the active
  Hybrid sources/manifests named by the comparison matrix and verify every
  required row still agrees. Confirm prohibited files and live operations
  before running the local gate.
- Run the full Greedy suite, focused policy-neutral Exact/Hybrid compatibility
  selections, import/compile checks, all Greedy Kustomize renders, manifest
  security checks, JSONL/CSV round trips, and `git diff --check`.
- Exercise small shapes with two and multiple configured stages/replicas and
  explicit stage/replica scale transitions through fake executors.
- Prove persistent-client reuse and cleanup, bounded utility-cache behavior,
  concurrent-route/sequential-placement ordering, equal-topology no-op,
  no-build process preservation, default no-replay behavior, forced-replay
  equality, and exact wall-time/footprint aggregation with fake clocks.
- Run a local comparison-envelope gate proving required rows match current
  Hybrid fixtures and intentional policy rows are the only differences.
- Prove no source or evidence under frozen `IBG/`, `IBG_Hybrid/`, MILP,
  `Chart/`, `Tutorial.md`, `Report.md`, or `EVIDENCE_SUMMARY.md` changed as part
  of the Greedy implementation.

Gate: local verification is complete and `STATUS.md` records exact test counts
and limitations. This phase makes no live Kubernetes or performance claim.

Phase 7 result: `tests/test_greedy_phase7.py` adds a seven-test integration
layer for the full current comparison-envelope hash audit, explicit
`3x2x1`/`5x2x2`/`5x4x3` policy-and-render shapes, cached/uncached equality,
controller-resource measurement neutrality, malformed retained CSV refusal,
and aggregate clean-directory import safety. The existing detailed Phase 0--6
tests continue to cover fake bootstrap/reuse/scale/recovery/refusal ordering,
client ownership, route concurrency, replay, timing/footprint, JSONL/CSV, and
manifest security.

The complete Greedy Phase 0--7 gate passes 166 tests. A focused unchanged
policy-neutral Exact/Hybrid selection passes 61 tests. The audit verifies all
35 unique active source/manifest paths in the 45 Phase 3--7 source records at
HEAD `8e5114e6e9101057da48255962afa65900c6c8d0`, with no drift across 52
required comparison rows or the 11 explicit policy differences. Direct CLI
help and missing-required-argument behavior pass without entering lifecycle
execution. Clean imports, externalized bytecode compilation, whitespace, and
frozen-path status checks pass. No Docker, kind, kubectl, Kubernetes, network,
traffic, live evidence, repository result output, or performance operation was
performed.

### Greedy Phase 8: separately authorized small live Kernel gate

Status: complete on 2026-08-27 after separate live authorization.

Recommended intelligence level for the user: `high`; the user may prefer
`xhigh` if read-only preflight reveals drift or command redesign is needed. The
normal path is a small, explicitly authorized execution of an already locally
accepted plan.

- Phase preparation (required after live authorization): reread the current
  `STATUS.md`, Greedy launcher/preflight help, rendered resources, and Phase 7
  test evidence immediately before proposing exact commands. Re-read the
  active Hybrid comparison manifests, launcher arguments, and focused resource
  tests before accepting the rendered Greedy envelope. Inspect the live cluster
  read-only first; do not reuse a stale Hybrid command or assume the cluster is
  clean.
- Start from a clean or read-only-preflighted dedicated `greedy` cluster; never
  target or delete Exact, Hybrid, or MILP clusters.
- Perform one normal offline build/load/bootstrap at a small declared topology,
  suggested `3 flows x 3 stages x 2 replicas`, then run a finite experiment.
- Verify exact node/namespace ownership, worker-only placement, Ready coverage,
  complete routes/observations/pairs, zero restarts, console/JSONL completion,
  forced `--parity-replay 1`, phase wall times, and optional CSV export from
  the same validated trace.
- Verify rendered and live Greedy controller resources equal the active Hybrid
  comparison envelope and record actual CPU/RSS/throttling evidence. This is a
  configuration gate, not yet a cross-policy performance claim.
- Repeat unchanged with `--skip-build` and prove serving Pod/image preservation
  while replacing only the finite controller Job.

Gate: the small live run and no-build repeat pass every declared functional and
evidence check. This establishes a lightweight Kernel baseline, not multi-host,
line-rate, DPDK/VPP, or large-scale performance.

#### Greedy Phase 8 implementation result

The read-only preflight found no Greedy cluster and left the stopped `ibg` and
`ibg-hybrid` clusters untouched.  After validating compatible local offline
wheel manifests, the launcher built and loaded both Greedy images without
network access, created exactly one control-plane and one worker, labeled only
the worker, applied the owned namespace/resources, expanded `3x3x1` to the
declared `3x3x2` in batches of one, and started the finite Job only after exact
Ready coverage.

Live execution exposed and bounded three environment/schema defects:
non-integral-MiB Kubernetes `Ki` allocatable memory, Docker-versus-containerd
image identity, and rounded belief/source-fingerprint evidence validation.
Focused tests cover each correction.  Policy, learning, utility, SLA,
fairness, equilibrium, resources, routes, and manifests were not changed.

The accepted normal trace is
`runs/greedy-experiment-20260827T095759.183839Z.jsonl`: 14 slots, equilibrium,
forced parity true for every slot, complete 3/6/3 placement/observation/pair
cardinalities, both images built/loaded, and one controller Job.  The accepted
unchanged skip-build trace is
`runs/greedy-experiment-20260827T095942.447983Z.jsonl`: 10 slots,
equilibrium, parity true for every slot, no build/load, and one replacement
Job.  The second run preserved all seven serving Pod UIDs, their node image
IDs, and zero restarts.  CSV export validated 31 files, unique headers, two
unequal-length run columns with padding, and aligned replica identities.

Verification: 176 Greedy Phase 0--8 tests and 113 focused unchanged
Exact/Hybrid compatibility tests pass.  Live resources, security contexts,
RBAC, worker-only placement, processor-private profile mounts,
controller-public inputs, console completion, JSONL round trips, real resource
samples, and zero final serving restarts pass.  Initial connection-refused
readiness events occurred only while containers started; exact readiness later
passed.  Phase 9 remains separately authorized and has not started.

### Greedy Phase 8.1: offline removal of synthetic admission capacity

Status: complete on 2026-08-27; Phase 8.2 has not started.

Recommended intelligence level: `xhigh`. This is a cross-cutting policy
contract migration with backward-compatible evidence requirements, not a
one-line capacity deletion.

- Preparation: reread the four handoff documents and the targeted Greedy
  passages in `misc/vesal_tex.tex`, especially the sequential counts,
  congestion-sensitive utility, budgeted action, myopic Greedy, and baseline
  comparison sections. Revalidate the active Greedy policy/discovery/
  lifecycle/evidence paths and the smallest current Hybrid capacity sources
  before editing. Record exact source locations, HEAD, blobs, and drift.
- Freeze `pure-greedy-budgeted-l2-v2`: exactly two distinct increasing stages,
  immediate belief-driven scoring at `current_load+1`, sequential commits, no
  future-flow simulation, and no topology-derived admission ceiling.
- Remove `admission_capacity_per_replica`, `max_assigned_flows`, and
  `greedy.max-assigned-flows` from active v2 policy inputs, discovery
  validation, controller configuration, manifests, renderer, lifecycle state,
  comparison assumptions, and new evidence. Do not replace them with `N`, an
  effectively infinite sentinel, or another inferred default.
- Preserve Running/Ready and exact identity coverage as feasibility. Preserve
  Kubernetes worker resource preflight and all processor/forwarder/controller
  requests, limits, probes, ports, workers, security contexts, and ownership.
- Preserve all other policy and metric semantics: fixed `L=2`, complete routes,
  canonical ties, best feasible action even when non-positive, selected-only
  learning, separated jitter, physical/raw utilities, strict 80-ms raw SLA,
  Jain fairness, and strict belief equilibrium.
- Add transparent fixtures proving a high-valued replica may receive more than
  the former `ceil(N/M)` count, later real flows see the accumulated current
  load, and no decision includes simulated future load. Prove removal of the
  hard ceiling can expose reactive hot-spot behavior without removing
  congestion from expected utility.
- Keep old v1 traces immutable and readable through an explicitly
  version-bounded compatibility path. New v2 writers must not fabricate v1
  fields; retained CSV must refuse mixed policy-contract columns unless a
  separately specified migration format exists.
- Reclassify the active Hybrid capacity comparison row as an unresolved
  comparison mismatch, without editing `IBG_Hybrid/`. No same-admission or
  same-input performance claim is permitted until both policies use an
  explicitly accepted common rule.
- Run the complete Greedy local suite, the smallest unchanged Exact/Hybrid
  semantic and lifecycle selections, offline renders, clean imports, external
  bytecode compilation, and `git diff --check`. Update all four handoffs.
- Do not invoke Docker, kind, kubectl, Kubernetes, traffic, or create new
  repository JSONL/CSV evidence.

Gate: all offline v2 contract, migration, renderer, comparison-disclosure, and
regression tests pass. Record Phase 8.2 as next but do not start it.

#### Greedy Phase 8.1 implementation result

The active policy is `pure-greedy-budgeted-l2-v2`. Topology-derived
`ceil(N/M)` flow admission was removed from typed configuration/public state,
Ready discovery, controller inputs, rendered labels, rollout/lifecycle
reconciliation, comparison matches, and new evidence. Feasibility is exact
identity coverage plus Ready state. Actual projected load still enters the
unchanged expected-utility calculation and both selected loads still commit
before the next real flow. A transparent `5x2x2` test reaches load five on one
replica, above the former ceiling of three, without adding future-flow load.

Historical `pure-greedy-budgeted-l2-v1` Phase 8 traces remain immutable and
readable through explicit v1 evidence/JSONL validators. V2 schemas omit the
capacity field, CSV has a policy-version marker and separate v2 default path,
and mixed v1/v2 retained columns fail closed. The v2 comparison fixture now
discloses active Hybrid's retained `ceil(N/M)` rule as an unresolved mismatch.

Offline verification passed: 183 complete Greedy Phase 0--8.1 tests and a
19-test focused policy-neutral/Hybrid/render selection. Changed Python files
compiled with bytecode outside the workspace; clean imports remained silent,
file-free, and RNG-neutral; `git diff --check` passed. No Docker, kind,
kubectl, network, traffic, cluster mutation, or repository evidence generation
was performed. Phase 8.2 is the next separately authorized live gate.

### Greedy Phase 8.2: separately authorized live admission-correction gate

Status: planned after Phase 8.1 and requires explicit live authorization.

Recommended intelligence level: `high`, escalating to `xhigh` if preflight
finds ownership, profile, source, or image drift.

- Preparation: read the accepted Phase 8.1 contract/tests/status, current
  launcher help, rendered resources, affected Docker source inventories, and
  active Hybrid comparison envelope. Inspect the dedicated cluster read-only
  before proposing commands; never mutate Exact, Hybrid, MILP, or foreign
  resources.
- Choose a small explicit `N,K,M` and profile seed whose offline fixture
  deterministically exercises at least one selected replica above the former
  `ceil(N/M)` count. Record why the shape demonstrates the correction.
- Perform a normal offline rebuild/load because policy, shared contracts,
  manifests, and source provenance changed. Reconcile only owned Greedy
  resources and create exactly one finite Job after exact readiness.
- Run with forced captured replay and CSV enabled. Validate v2 contract
  identity, placements, sequential loads, selected observations, pairs,
  beliefs, utilities, SLA, fairness, equilibrium, timing, resources, redaction,
  zero serving restarts, and the above-old-cap load demonstration.
- Repeat unchanged with `--skip-build`; prove no build/load, retained serving
  Pod/image/profile preservation, and replacement of only the finite Job.
- Persist new v2 JSONL and version-compatible CSV separately from historical
  v1 output. Do not rewrite, relabel, or backfill Phase 8 evidence.
- Treat measured results as correction/operability evidence, not as a final
  Greedy-versus-Hybrid performance claim. Update all four handoffs and stop.

Gate: the corrected normal live run and unchanged skip-build repeat pass, with
an observed load above the removed ceiling and no future-load reasoning.

### Greedy Phase 9: separately authorized scale and final-baseline acceptance

Status: planned after Phase 8.2.

Recommended intelligence level: `xhigh`. Persistent-cluster transitions,
matched-input reasoning, performance evidence, and final comparison claims
require the strongest cross-phase analysis and provenance discipline.

- Phase preparation (required after separate scale authorization): study the
  accepted Phase 8.2 trace/status, current Greedy rollout/profile implementation,
  worker resource envelope, and the exact target comparison's input contract.
  Re-read the current Hybrid launcher, manifests, comparison trace provenance,
  and focused evidence validators. Record matched and unmatched inputs before
  proposing scale or A/B commands.
- Validate bounded replica scale-up and intentional scale-down on the persistent
  Greedy cluster, then validate one stage-count expansion and contraction while
  preserving retained lower identities and profiles.
- Run the intended final comparison shape, initially suggested to match an
  accepted Hybrid topology such as `10x3x5`, with recorded hidden-state map,
  flow/order seeds, keyed stochastic-input schedule, runtime versions, matched
  controller/serving resources, lifecycle state, and complete provenance.
- Report policy runtime, utility, end-to-end SLA count/excess, fairness,
  convergence, phase wall times, and control-plane evidence without claiming
  same-input Hybrid comparison unless the complete state and stochastic inputs
  are actually matched.
- Keep production parity replay off for timing runs after the forced-replay
  correctness gate. Do not add a Greedy process pool or change resources for
  only one baseline. Any resource variation requires a separately reviewed,
  versioned matched Greedy/Hybrid A/B with unchanged inputs and serving Pods.

Gate: scale transitions, repeatability, replay, and the declared final evidence
pass; documentation records the supported dimensions and any exploratory
larger runs separately. Optional robustness or new baseline-comparison features
require a new roadmap.
## Hybrid posterior-transmission mirror plan

Planned: 2026-08-31. This is a three-phase, opt-in measurement extension for
the paper's belief-update control-plane claim. It does not replace local belief
ownership or change Hybrid decisions.

1. **Phase 1: measurement contract and implementation — medium difficulty.**
   Inspect the existing learning-result boundary and define the canonical set
   and order of completed posterior updates. Add a versioned deterministic
   serializer, a lightweight validation/discard HTTP receiver, a worker-only
   Pod and ClusterIP Service, controller-side opt-in transmission, lifecycle
   provenance, and exact vector/body byte and message accounting. Disabled
   mode must render and execute no receiver or transmission. Add focused unit,
   manifest, serialization, arithmetic, failure, and semantics-neutrality
   tests, but do not mutate a live cluster.
2. **Phase 2: complete local verification and handoff completion — medium
   difficulty.** Run focused tests, the complete Hybrid suite in bounded
   groups, relevant frozen Exact regressions, changed-Python compilation,
   launcher checks, all applicable offline Hybrid renders, and
   `git diff --check`. Finalize validated JSONL/CSV and summary behavior if it
   is not already complete in Phase 1. Append actual results only after these
   gates pass.
3. **Phase 3: separately authorized live gate — medium difficulty.** Build and
   load the affected Hybrid image(s), run matched disabled/enabled experiments,
   prove the receiver obtains the exact bodies and counts recorded by the
   controller, and prove placement, beliefs, learning, utility, SLA, fairness,
   telemetry, and serving-Pod behavior are unchanged. Report payload-only
   results without wire-byte, NIC, multi-host, or operational distributed-
   learning claims.

Phase 1 is the next action. Phase 2 and all live work require later explicit
user authorization.

## Hybrid posterior-transmission mirror Phase 1 and Phase 2 complete

Completed locally: 2026-08-31. Phase 1 implemented the default-off receiver,
canonical serializer, persistent sender, strict evidence/provenance, resource
preflight, production option, lifecycle cleanup, and fail-before-commit
behavior. Phase 2 completed the three mirror CSVs, the Hybrid-only summary
command, integration coverage, and the requested offline verification.

Acceptance evidence:

- 104 focused posterior-mirror, evidence, CSV, summary, launcher, lifecycle,
  resource, packaging, and control-plane tests passed in the final focused run.
- The complete Hybrid suite passed in three memory-bounded groups: 162, 103,
  and 146 tests, for 411 passing tests total.
- Changed Python compilation with external bytecode, clean imports, launcher
  and summary help, all seven retained offline Kustomize renders, an additional
  enabled-receiver offline render, and `git diff --check` passed.
- IBG-Exact was not inspected, changed, or tested. No image build/load, Docker,
  kind, API-server, Job, Pod, traffic, cluster mutation, or live experiment was
  performed.

Phase 3 is next but remains blocked on separate explicit authorization. It must
perform a matched disabled/enabled live gate, verify exact receiver receipts and
semantic non-regression, and report only instrumented application-payload
evidence. It must not claim wire bytes, NIC behavior, multi-host behavior, or
that Hybrid operationally requires distributed belief exchange.

Pre-Phase-3 integration addendum: the first user-run preflight exposed a
fail-closed difference caused solely by a retained
`kubectl.kubernetes.io/restartedAt` Pod-template annotation. Reconciliation now
preserves non-netem annotations instead of removing them. The correction passed
65 focused network-impairment, topology, and infrastructure tests, compilation,
and `git diff --check`; no experiment was rerun by the implementation agent.

Receiver-startup addendum: the first enabled user attempt exposed that the
initial receiver manifest selected the Uvicorn-free controller image. The
receiver now selects the existing Uvicorn-equipped service image, and that
image copies only the self-contained mirror module in addition to its retained
service sources. Fifty-eight focused mirror, image-isolation, wheelhouse, and
netem tests pass with compilation and `git diff --check`. The agent did not
restart the Deployment or run traffic.

### Greedy Phase 8.2 rollout-timeout repair

Implemented locally: 2026-09-01. Two user-started `40x3x20` normal attempts
made steady ordered rollout progress but exceeded the former single
120-second command deadline before all 60 replica Pods converged. Each rollout
subsequently reached 20/20 Ready per stage, but the launcher had already exited
and created no controller Job. A following `--skip-build` attempt correctly
refused the pending service-image marker.

The readiness gate now uses a 120-second progress-reset stall timer plus a
separate topology-bounded total deadline. Focused lifecycle tests prove a
140-second progressing rollout succeeds and 122 seconds without verified
progress fails. The complete Phase 5 lifecycle file passes 21 tests; changed
Python compiles and `git diff --check` passes. The complete Greedy selection
has 183 passing tests and one comparison-audit failure caused by unrelated
current `IBG_Hybrid/kernel_controller.py` worktree drift. Phase 8.2 remains
incomplete: no corrected controller run/evidence exists, and the retained v1
capacity-label reconciliation issue remains to be closed before acceptance.

#### Greedy Phase 8.2 rollout-recovery substep result

Completed: 2026-09-01. The launcher now binds service Pod templates to exact
public source/image provenance, classifies a pending transition before
mutation, waits an exact in-progress revision without starting another, and
fails closed on partial or mismatched provenance. A required canonical apply
also removes the retired v1 capacity label; the former unconditional rollout
restart was removed so that correction produces one revision only. Focused
progress, stall, noise, churn, recovery, image-mismatch, stale-label, Job-order,
immutability, deterministic-executor, and import tests pass.

The authorized recovery command completed the interrupted `40x3x20`, one-slot
request. All three StatefulSets converged at 20/20 updated and Ready after a
162-second observed serving-Pod replacement window, the flow generator became
Ready, all 60 replica Pods and the generator used the exact target OCI config
image, and the stale capacity label was absent. Exactly one controller Job then
succeeded. The validated v2 trace is
`runs/greedy-experiment-20260901T163749.921241Z.jsonl`: one iteration,
40 placements, 80 observations, 40 measured pairs, no CSV, no replay, and no
build/load.

This substep closes interrupted-rollout recovery, not the complete Phase 8.2
gate. The requested `40x3x20` trace reached a maximum replica load of two and
did not enable forced replay or CSV, and no unchanged `--skip-build` repeat was
run. Phase 8.2 therefore remains incomplete until its separately specified
above-old-ceiling, replay/CSV, and unchanged-repeat acceptance evidence passes.
Phase 9 must not start.
