# IBG Testbed Expansion Roadmap

Work proceeds in order. A phase starts only after the previous phase's checks pass and `STATUS.md` records the result. This roadmap replaces the completed lightweight-migration roadmap as the active plan; it does not invalidate its Phase 6 simulation/Kubernetes parity evidence.

## Scope and terminology

The frozen baseline is the decoupled exact IBG testbed: the Python solver, utility grid, learning rule, equilibrium rule, FastAPI replica contract, flow-generator contract, and the supported three-flow/three-stage/five-replica validation remain the behavioral reference.

`Kernel` means the ordinary Linux socket/TCP/IP path already used by the HTTP workloads. The later comparison target is `dpdk-vpp`: VPP running in Linux user space with its approved DPDK I/O backend. VPP can also integrate with the Linux control plane or use non-DPDK interfaces, but that is not a third comparison arm in this roadmap. The immediate work is to make the Kernel baseline explicit; DPDK/VPP is a later target, not an implemented capability or a current validation claim.

In every mode, FastAPI remains responsible for `/health`, `/process`, replica identity, the selected-hop processing-latency signal and likelihood, and application-level latency/concurrency telemetry. A datapath may forward traffic and contribute transport telemetry, but it must not generate observations, update beliefs, alter the solver's final assigned load, or cause unselected replicas to emit samples. This preserves the paper's asymmetric and partial-observation requirement.

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

Status: in progress.

Suggested Codex reasoning: `high` — evidence must remain traceable to a reproducible run and must not silently turn synthetic testbed results into hardware or datapath claims.

- Help the user gather, inspect, summarize, and explain existing simulation and `kernel` evidence, including structured JSONL traces, host-side CSV exports, validation summaries, calibration results, and focused test outcomes.
- Preserve provenance for every reported figure or claim: record the source command/trace, seed, dimensions, image/mode, and whether a result is mathematical replay, modeled calibration, localhost FastAPI conformance, or live Kubernetes telemetry.
- Keep claims bounded: the HTTP/Kubernetes route is the validated `kernel` baseline; do not imply DPDK/VPP, SR-IOV, hugepages, hardware offload, line-rate, or real CNF validation.
- Treat report content as user-directed work. Do not read or edit `Tutorial.md`, `Report.md`, or `EVIDENCE_SUMMARY.md` unless the user explicitly requests that file in the current task. Do not rewrite generated evidence files; derive new summaries or figures only when requested.
- Answer user questions and add narrowly scoped reproducibility aids when needed, without changing the decoupled solver, processing-latency observation/likelihood boundary, hard 175 ms SLA, or one-of-M no-rejection behavior. The user explicitly authorized the Phase 4 recalibration from 250 ms to 175 ms using the recorded exploratory 12-flow end-to-end-latency distribution; it changes only SLA classification, not placement, utility, learning, admission, or datapath behavior. The user also authorized tightening the unchanged equilibrium check from strictly below 0.04 to strictly below 0.03 per belief entry; this changes only when an experiment stops. The later explicit forwarding/reporting authorization is limited to executing an already-selected route and correcting its post-placement pairwise deduction; it does not authorize pair-dependent selection.

Gate: the requested evidence is traceable to committed code and identified run artifacts, its scope/units/limitations are clear, the authorized forwarding/reporting correction is validated and version-bounded, and no solver, learning, admission, or unapproved datapath behavior has changed.

Initial curation result: `EVIDENCE_SUMMARY.md` identifies the accepted calibration command and supported Kernel traces, separates modeled, localhost, live-cluster, and replay claims, and is opt-in-only. The Phase 2 synthetic calibration reproduces under current code. The historical Phase 3 trace still passes its live telemetry gate but predates the belief-retention change from 0.6 to 0.8. Three fresh supported-size retention-0.8 Kernel runs (seeds 2050--2052) replayed exactly across 31 slots and 279 placements/observations under the then-active 0.04 equilibrium threshold. Their live server-overshoot results vary: seed 2050 records 89.90%, while seeds 2051 and 2052 each record 100%; the 96.42% pooled rate is descriptive and does not replace the existing per-trace 95% scheduling gate. Exploratory 10- and 12-flow/5-replica runs reached equilibrium and replayed exactly, but do not extend the formal three-flow gate. The 12-flow CSV run exposes an unresolved user concern: the exported aggregate-utility series subtracts volatile live transport overhead and can decline despite improved learned selections and processing utility. Five additional live repeats of the same 12-flow command at seed 2050 reached equilibrium in 7--11 slots; first-to-final realized end-to-end utility increased in four traces and fell 5.78% in one because its transport penalty increased more than its realized processing utility. Thus Total Realized End-to-End Utility is an actual-outcome metric, but it is not a per-run monotonic-learning metric. Phase 4 now adds `realized_end_to_end_utility.csv` as a backward-compatible export of the existing trace metric while retaining `aggregate_utility.csv` unchanged, and—under explicit user authorization—recalibrates the active SLA threshold from 250 ms to 175 ms using the exploratory 12-flow latency distribution and tightens the equilibrium stopping threshold to 0.03. The paper/implementation audit found that the former request-overhead deduction was not the paper-defined consecutive-replica cost. The user authorized the narrow correction described below; historical traces keep their former semantics, and fresh live/replay evidence is required before making current-implementation empirical claims. Transport-inclusive outcome claims must remain distinct from learning-only claims.

Implemented Phase 4 reporting correction: preserve the exact decoupled solver and all selection mathematics, but replace generator-mediated independent hop execution with forwarding along the already-selected stage route. Record one correlated communication/RPC-cost measurement for each consecutive selected pair, deduct only those `K-1` edge costs in reported end-to-end latency and utility, and keep broad flow-generator ingress overhead as separate telemetry. This is post-placement execution/reporting work only; pairwise costs do not influence placement, and coupled IBG remains out of scope. Focused validation passes; a fresh live run has not yet been collected. The subsequent code audit found four required hardening fixes before a new-schema trace can satisfy this phase: reject omitted pair/ingress fields instead of defaulting them to zero; validate each pair's source/target Pod and target endpoint; prove the pair-cost sum equals the per-flow metric deducted by the runner; and reject mixed historical/pairwise schemas in one run. These are validation/schema fixes only, not coupled behavior or new datapath work.

## Phase 5: Design and prove the DPDK/VPP integration boundary

Status: planned.

Suggested Codex reasoning: `xhigh` — DPDK resource ownership plus VPP topology, interfaces, lifecycle, routing, and failure handling must be specified before changing runtime workloads.

- Audit and reserve the required DPDK resources on the target host: NIC ownership, IOMMU/VFIO, hugepages, CPU/NUMA placement, container privileges, and Kubernetes device resources. Define a safe rollback procedure.
- Select and document the DPDK/VPP topology, its DPDK I/O backend, and the Linux-facing interfaces for this host (for example, VPP forwarding between the flow generator and selected FastAPI replicas). Keep Kubernetes Service discovery and FastAPI application endpoints intact.
- Define lifecycle, readiness, configuration, cleanup, and failure behavior for DPDK/VPP components and their Kubernetes resources. `kernel` mode must remain independently runnable.
- Specify how DPDK/VPP counters and per-hop transport timing are correlated to the existing slot/flow/stage/replica route identity without expanding the observation set. Add focused control-boundary tests before requiring a cluster deployment.

Gate: the host preflight and documented DPDK/VPP design demonstrate safe resource ownership and can forward only a selected, correlated route to its FastAPI endpoint, report a clear readiness/failure state, and preserve the Phase 1 latency-observation contract.

## Phase 6: Implement the DPDK/VPP-backed FastAPI route

Status: planned.

Suggested Codex reasoning: `xhigh` — this joins privileged DPDK resources, Kubernetes networking, VPP lifecycle, selected-route enforcement, and controller telemetry without authorization to alter IBG behavior.

- Add deployable DPDK/VPP resources and a `dpdk-vpp` traffic/telemetry adapter behind the existing complete-slot traffic port.
- Route each selected logical hop through the configured DPDK/VPP path and then to the same FastAPI `/process` contract. Do not replace FastAPI replicas with synthetic datapath observations.
- Preserve concurrent flows, sequential hops within a flow, route/identity validation, cleanup, and explicit failure rather than partial-success reporting.
- Emit DPDK/VPP-specific metadata only as supplemental telemetry, clearly separating it from the FastAPI processing-latency signal/likelihood, client latency, and concurrency fields.

Gate: a local and a small-cluster DPDK/VPP-mode run complete selected multi-hop routes, reject a DPDK/VPP or downstream failure cleanly, and retain complete per-hop correlation with no observations from idle replicas.

## Phase 7: Validate Kernel and DPDK/VPP modes against the IBG baseline

Status: planned.

Suggested Codex reasoning: `xhigh` — comparison must separate mathematical equivalence from genuine datapath timing and counter differences.

- Run controlled seeds at the supported three-flow/three-stage/five-replica configuration for simulation, `kernel`, and `dpdk-vpp` modes.
- Require replay parity for placements, utility grids, latency likelihoods, beliefs, utility, SLA, fairness, and equilibrium. Live runtime and datapath telemetry may differ and must be compared statistically rather than normalized away.
- Verify asymmetric/partial observation behavior directly: only selected replicas provide processing-latency observations in every mode.
- Publish a reproducible comparison command and a bounded evidence report; make no line-rate, hardware-offload, or DPDK claim from these results.

Gate: Kernel and DPDK/VPP modes are mathematically equivalent to the controlled simulation for the supported seeds, with explained and complete mode-specific telemetry and only the measured comparison claims supported by the hardware configuration.

## Future coupled-IBG track

Status: awaiting user requirements; not scheduled.

Coupled IBG is a separate mathematical and experimental scope. It must begin with an explicit problem definition, state/action and utility changes, observation and learning semantics, baselines, and acceptance fixtures. It must not be introduced as a datapath-mode option or silently alter the validated decoupled solver.
