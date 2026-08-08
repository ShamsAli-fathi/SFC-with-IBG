# Project Status

Updated: 2026-07-22

IBG-Hybrid scope updated: 2026-07-27

## Completed

- Reviewed the paper draft and its hybrid-testbed proposal.
- Read the Python files directly under `IBG/` and identified the active decoupled simulation path.
- Established the lightweight target architecture and migration boundary.
- Chose a native-Docker development toolchain instead of Docker Desktop.
- Created the native ext4 checkout at `/home/shams/projects/SFC-with-IBG` and preserved the existing unstaged `requirements.txt` change.
- Installed Docker Engine 29.6.1, kubectl 1.35.6, kind 0.32.0, and Helm 4.2.0 in the development environment.
- Added a reproducible three-node kind configuration and created cluster `ibg` with Kubernetes 1.35.0.
- Verified three Ready nodes, Ready system Pods, a two-replica HTTP deployment, Service DNS/networking, and cleanup of the temporary smoke-test namespace.
- Completed Roadmap Phase 0: created `.venv` with Python 3.12, installed the declared dependencies, verified active IBG imports, and compiled all Python sources without executing `IBG/main.py`.
- Completed Roadmap Phase 1: added eight initial deterministic characterization/equivalence tests and extracted one decoupled slot into an import-safe runner; the later `BR_EIBG` correction is recorded below.
- Reduced the reference entry point from 48 outer experiments to one by default and verified the existing small configuration (three stages, four replicas per stage, three flows) reaches equilibrium; smoke-test reports were written only under `/tmp`.
- Completed Roadmap Phase 2: defined discovery, traffic, observation, and result-sink ports; added simulation-backed implementations; and kept measured latency separate from the legacy belief signal.
- Expanded the suite to 18 passing tests, including explicit-adapter equivalence, legacy observation-update parity, contract validation, empty-discovery failure, and reference CSV sink behavior.
- Verified an adapter-driven small experiment reaches equilibrium and writes the expected metric and belief row counts under `/tmp`.
- Completed Roadmap Phase 3: implemented the configurable FastAPI/Uvicorn HTTP replica with `/health` and `/process`, stable identity, real concurrent-request accounting, latency telemetry, and the reference legacy observation model.
- Expanded the suite to 32 passing tests, including endpoint contracts, three-request overlap, exact tasting parity, request/config validation, and concurrency cleanup after failures.
- Verified a live localhost Uvicorn process returns HTTP 200 for both endpoints and shuts down cleanly.
- Completed Roadmap Phase 4: implemented a route-driven FastAPI flow generator that runs logical flows concurrently while preserving sequential three-stage execution within each flow.
- Added strict route, response, and replica-identity validation plus correlated per-hop concurrency, latency, Pod, endpoint, and legacy-observation telemetry.
- Added a shared non-root runtime image, a four-service Docker Compose topology, and a repeatable three-flow container-network smoke test.
- Expanded the suite to 42 passing tests, including selected-endpoint routing, inter-flow concurrency, intra-flow stage ordering, telemetry correlation, downstream failures, and identity/correlation mismatches.
- Verified the Phase 4 gate with three concurrent three-hop flows across the local container network; every flow returned stages 1, 2, and 3 in order and the stage-1 service reported admitted concurrency levels 1, 2, and 3.
- Added `Tutorial.md` as a user-directed beginner-friendly report, operating guide, and “IBG Exact” explanation of the Python reference logic.
- Replaced the provisional myopic policy in `IBG/claude.py` with exact memoized `BR_EIBG` continuation play over the formal one-replica-per-stage action space.
- Kept the existing sampled utility grid, embedding, observation, belief-update, equilibrium, metric, adapter, and testbed behavior around the corrected solver.
- Expanded the suite to 45 passing tests, including a non-myopic continuation fixture, a 56-state memoization check, and a three-flow/five-replica/three-stage integration case.
- Verified the seeded three-flow/five-replica/three-stage run completes all nine placements and observations; the measured local wall time was approximately 179 ms.
- Verified the default three-flow/four-replica/three-stage experiment still writes all reference reports and reached equilibrium in 23 iterations in one stochastic smoke run; outputs were isolated under `/tmp`.
- Removed the scaling phase and fixed the supported exact-testbed target at three stages, five replicas per stage, and three flows.
- Restored and verified the existing `ibg` kind cluster: all three nodes and system Pods are Ready, and a disposable in-cluster check resolved Service DNS and completed Pod-to-Service HTTP.
- Completed Roadmap Phase 5: added three headless Services, three two-replica StatefulSets, deterministic shared profiles, the flow-generator Deployment and Service, the controller Job, and namespace-scoped discovery RBAC.
- Added readiness-filtered Kubernetes discovery that maps StatefulSet ordinals to solver replica IDs and retains stable Pod, node, and endpoint metadata without changing `BR_EIBG`.
- Added complete-route slot execution through the flow generator and converted its correlated telemetry into the existing observation contract before unchanged belief, equilibrium, metric, and reporting logic.
- Expanded the suite to 49 passing tests, including deterministic profile loading, ordinal discovery, incomplete-readiness failure, complete-route execution, and Kubernetes telemetry-to-observation coverage.
- Verified the Phase 5 cluster gate with three stages, two replicas per stage, and three flows. The controller Job completed successfully with nine placements, nine selected observations, complete three-hop telemetry, real replica contention, and updated beliefs and metrics.
- Verified controller RBAC allows only Pod `get`/`list` for discovery and denies Secret reads and Pod creation.
- Completed Roadmap Phase 6: expanded all three StatefulSets to five replicas and added deterministic profiles for all 15 supported replica identities.
- Corrected the cross-backend observation boundary so the preserved legacy model uses final assignment congestion while admitted HTTP concurrency remains separate measured telemetry.
- Added request-stable observation sampling, controlled simulation summaries, Kubernetes result summaries, and a repeatable three-seed comparison tool.
- Expanded the suite to 57 passing tests, including final-load observation semantics, seeded observation stability, supported profile coverage, comparison parity, and discrepancy detection.
- Verified three repeated supported-size Kubernetes runs for seeds 2050, 2051, and 2052. All 27 placements, utility-grid values, observation signals/likelihoods, beliefs, utility metrics, SLA results, Jain fairness values, and equilibrium results matched the controlled simulation exactly.
- Verified all three Kubernetes runs returned nine complete correlated hops with Pod, node, endpoint, concurrency, and latency metadata. Seeds 2051 and 2052 observed admitted concurrency of 2.
- Quantified the expected runtime discrepancy: Kubernetes averaged 0.309 seconds per slot versus 0.051 seconds in-process, approximately 6.04 times longer; no mathematical discrepancy remained.
- Prevented controller traffic from racing workload updates by separating the controller Job from the base Kustomization and applying it only after all rollouts complete.
- Added a bounded multi-slot Kubernetes experiment loop that preserves one evolving replica/belief state until the existing equilibrium rule succeeds.
- Added structured run-start, per-iteration, and run-completion events containing flow order, placements, observations, belief changes, metrics, and initial/final replica state.
- Added `scripts/run_experiment.py` as a one-command operator entry point that creates/reuses kind, rebuilds and loads the image, deploys and waits for workloads, launches a fresh experiment Job, prints readable live progress, and saves the detailed trace under versionable `runs/`.
- Switched slot-duration measurement to a monotonic clock after the first observable run exposed a host wall-clock jump in one iteration.
- Expanded the suite to 63 passing tests, including equilibrium-loop state retention, iteration bounds, belief-delta tracing, launcher environment overrides, readable rendering, and watcher-free log polling.
- Verified the final one-command launcher live with seed 2050: all 15 replica Pods and the flow generator rolled out, the fresh controller Job reached equilibrium in 9 iterations, corrected slot durations ranged from approximately 0.307 to 0.394 seconds, and an 11-event JSONL trace captured run start, every iteration, and final state.
- Added `--flow`, `--stage`, and `--replica` launcher dimensions with plural aliases, dynamic deterministic profiles, generated stage Services/StatefulSets, stale-stage cleanup, and matching controller configuration.
- Generalized complete-route execution from exactly three hops to any shared positive contiguous stage sequence beginning at stage 1.
- Expanded the suite to 73 passing tests, including generated four-stage/seven-replica resources, deterministic profile extension, singular/plural CLI flags, dimension propagation, stale-stage cleanup, and two-/three-/four-stage Kubernetes routes.
- Verified a live non-default run with two flows, four stages, and two replicas per stage. The launcher generated eight replica Pods and a new Stage 4 Service/StatefulSet, completed all eight placements and observations per slot, and reached equilibrium in 4 iterations.
- Restored the default three-flow/three-stage/five-replica topology through the same CLI, verified stale Stage 4 resources were removed, and reproduced equilibrium in 9 iterations with the validated final beliefs.
- Added `Report.md`, a repository-evidence-based comparison of the paper draft's hybrid container testbed and the implemented lightweight HTTP/Kubernetes testbed.
- Made `Report.md` opt-in-only: it must not be read or edited unless the user explicitly requests it in the current task.
- Added optional `--csv 1` host-side export to `scripts/run_experiment.py`. A completed Kubernetes JSONL trace is converted into `time.csv`, `sla_violations.csv`, `aggregate_utility.csv`, `jain_index.csv`, and `replica_results.csv` under the repository-local ignored `figures/` directory; omitting the option retains JSONL-only behavior.
- Expanded the suite to 76 passing tests, including CSV option parsing, complete legacy report generation, initial/per-iteration belief snapshots, and appending a new experiment column to existing metric reports.
- Recreated the disposable `ibg` kind cluster after its stopped node containers returned with an unusable API following a host-environment interruption, then reloaded the existing local runtime image.
- Verified `./scripts/run_experiment.py --csv 1 --flow 4 --stage 3 --replica 3 --max-iterations 100 --skip-build` live. All nine replica Pods and the flow generator became Ready, the controller Job reached equilibrium in 8 iterations, the JSONL trace completed, and all five requested CSV files were written successfully.
- Created and maintained the repository handoff documents as implementation progressed.
- Reset the active roadmap for the next expansion: begin with controlled user-directed mathematical and parameter revisions, then make the resulting validated FastAPI/Kubernetes route the explicit `kernel` mode, plan the later comparison path as DPDK/VPP, and leave coupled IBG awaiting a separate user-defined scope.
- Completed expansion Phase 1: added a pure positive state/load-conditioned latency model with provisional ordered state curves; migrated active utility from inverse/double-congestion behavior to $R_k-\alpha_kq-c_k$; and made selected processing latency the continuous belief signal with load-aware likelihoods.
- Made FastAPI replica behavior causally depend on hidden state, final assigned load, effective capacity, congestion knee, and seeded jitter while keeping admitted concurrency and client/transport timing separate.
- Added per-flow processing, transport, and end-to-end latency plus realized linear utility; replaced active state-ID SLA with a configurable latency threshold; and retained legacy wire fields only as transition aliases.
- Expanded the suite to 82 passing tests, including provisional state ordering/zero crossings, seeded latency, state causality, replay parity, selected-only observations, transport deduction, realized utility, and latency SLA. Compiled all Python sources successfully.
- Completed expansion Phase 2 with the historical symmetric-jitter state table `(40,8,12,1,4)`, `(28,6,8,2,3)`, `(18,4,5,3,2)`, and `(10,2,2,5,1)` in `(base ms, ordinary ms, knee ms, capacity flows, jitter ms)` units over a 12-flow calibration horizon. The later completed Phase 4 nonnegative-jitter branch supersedes only its jitter law and scales.
- Initially fixed reward 100, stage cost 1, processing/link latency weights 1 utility unit/ms, SLA threshold 250 ms, target crossing bands 3--4/4--6/6--8/10--12, and center crossings 3/5/7/11. The active SLA threshold was later user-recalibrated to 175 ms in Phase 4; the other values remain synthetic testbed design values, not measured datapath-capacity claims.
- Added `IBG/calibration.py` and executable `scripts/phase2_calibrate.py` for state/curve ordering, zero crossings, low-load/supported-load feasibility, seeded classification, illustrative SLA probability, sensitivity, and optional live HTTP checks.
- Verified the full 5,000-sample/state/load seed-2050 calibration: minimum categorical accuracy was 94.42%; all $\pm10\%$ latency/weight and $\pm5\%$ reward scenarios retained ordered target crossings; homogeneous three-stage/load-3 modeled SLA probabilities were 1.0/0.0/0.0/0.0 for states 1--4 with zero transport.
- Verified 40 accepted localhost Uvicorn observations across all four hidden states at baseline and post-capacity loads. Every correlation/signal/likelihood/timing check passed, maximum scheduler overshoot was 6.78 ms within the declared 10 ms/10% bound, and minimum per-point categorical accuracy was 80%. No Kubernetes cluster calibration was claimed.
- Expanded the suite to 88 passing tests and compiled all Python sources successfully after Phase 2.
- Completed expansion Phase 3: named the existing Kubernetes HTTP path `kernel` across adapter, controller, flow-generator, hop telemetry, slot-result, validation-summary, manifest, and JSONL boundaries without changing the FastAPI replica `/process` payload, solver, observations, learning, utility, placement, or the then-active hard 250 ms SLA. Phase 4 later user-recalibrated only the threshold to 175 ms.
- Added explicit non-negative Kernel request-overhead telemetry per selected hop, runtime mode validation that rejects unimplemented datapaths, image/environment provenance, and selected-only mode/correlation checks.
- Added `scripts/phase3_kernel_baseline.py` and replay adapters. The validator checks mode provenance, complete selected-only observations, exact processing signals and likelihoods, transport correlation, load-1 state ordering, observed congestion response, classification, Kubernetes scheduling tolerance, equilibrium, and exact multi-slot mathematical replay.
- Rebuilt `ibg-testbed:kernel-phase3` and verified a supported three-flow/three-stage/five-replica seed-2050 run reached equilibrium in 9 iterations with 81 complete selected hops over loads 1--3.
- Verified load-1 mean processing latency remained ordered at 49.06/39.27/21.31/12.52 ms for states 1--4; state-3/state-4 congestion groups were non-decreasing; categorical accuracy was 83.95%; and 98.77% of hops passed the accepted $\max(10\text{ ms},10\%)$ overshoot bound.
- Measured processing latency mean/p50/p95/max of 16.33/13.13/36.59/52.60 ms, server overshoot 2.07/0.97/7.52/10.54 ms, and non-negative request overhead 6.85/6.43/11.31/17.87 ms. A preliminary cold single-slot request-overhead outlier reached 60.30 ms, so no deterministic transport ceiling is claimed.
- Replayed all 9 Kernel slots through the unchanged runner with the captured selected signals, likelihoods, and per-flow transport values. All 81 placements and observations matched and maximum mathematical drift across grids, beliefs, utility, latency, SLA, fairness, and equilibrium was zero.
- Expanded the suite to 93 passing tests and compiled all Python sources successfully after Phase 3.
- Began user-directed expansion Phase 4 evidence curation and added an opt-in-only `EVIDENCE_SUMMARY.md` provenance inventory without changing IBG or datapath behavior.
- Reproduced the Phase 2 seed-2050, 5,000-sample synthetic calibration under current code: the model gate passed with 94.42% minimum classification accuracy and the accepted crossings, SLA illustration, and sensitivity checks intact.
- Recomputed the live-telemetry portion of the accepted Phase 3 trace `runs/ibg-experiment-20260713T110905Z.jsonl`: all Kernel telemetry checks still pass for its nine iterations and 81 selected hops.
- Identified a version boundary in the replay evidence: that trace predates the global belief-retention change from 0.6 to 0.8. The current Phase 3 validator now stops at the first replay placement drift, so its former zero-drift replay result is historical evidence for the Phase 3 code version rather than current-HEAD parity. A fresh supported-size Kernel trace is needed to re-establish replay parity under retention 0.8.
- Ran one fresh supported-size `kernel` experiment at seed 2050 with the active belief-retention value 0.8: it reached equilibrium in 11 iterations and captured 99 selected hops under `runs/ibg-experiment-20260715T122305Z.jsonl`.
- Replayed all 11 fresh Kernel slots through the unchanged runner. Every placement and observation matched, with zero belief and mathematical drift, restoring current-HEAD replay parity under retention 0.8.
- The fresh run did not meet the separate live server-scheduling gate: 89.90% of hops met the required overshoot tolerance, below the accepted 95%. Its live telemetry is evidence, but it does not replace the historical accepted live Kernel baseline.
- Collected the remaining current-head supported-size runs at seeds 2051 and 2052 using the same dimensions and retention 0.8. `runs/ibg-experiment-20260715T123505Z.jsonl` reached equilibrium in 9 iterations with 81 selected hops; `runs/ibg-experiment-20260715T123533Z.jsonl` reached equilibrium in 11 iterations with 99 selected hops.
- Validated both new traces with `scripts/phase3_kernel_baseline.py`: every recorded live Kernel check passed, including 100% server-overshoot-tolerance rates, and every replayed placement/observation/belief/mathematical value matched exactly with zero drift. Across the three current-head traces, replay parity covers 31 slots and 279 hops; the pooled live overshoot rate is 269/279 (96.42%), while the individual seed-2050 trace remains below the per-trace 95% threshold at 89.90%.
- Ran the user-requested exploratory `./scripts/run_experiment.py --flow 10 --stage 3 --replica 5 --max-iterations 100 --skip-build` at default seed 2050. `runs/ibg-experiment-20260715T125302Z.jsonl` reached equilibrium in 10 iterations with 300 selected hops and replayed exactly with zero belief/mathematical drift. Its 286/300 (95.33%) server-overshoot rate and 95.67% classification meet those individual numerical checks, but the formal validator remains false because the configuration is outside the supported three-flow target, load-1 state ordering is incomplete, and the state-4 load-2/load-3 means are slightly non-monotonic. It is evidence of a successful exploratory run, not an expanded acceptance claim.
- Ran the user-requested 12-flow/5-replica Kernel experiment with `--csv 1`: `runs/ibg-experiment-20260715T133726Z.jsonl` reached equilibrium in 8 iterations, produced 288 selected hops, and replayed exactly with zero belief/mathematical drift. Its 100% scheduling-tolerance and classification checks passed; the formal Phase 3 gate remains inapplicable because 12 flows is outside the supported target and load-1 ordering is incomplete.
- Identified an unresolved user concern in that 12-flow CSV run. The learning signal/placements improved from iteration 1 to 8 (mean selected true state 2.67 to 3.39, state-1 selections 7 to 0, state-4 selections 11 to 19), and processing utility rose, but exported `aggregate_utility_total` fell 1631 to 1562 because its summed transport-overhead penalty rose 654 to 1077. The current CSV series is therefore not accepted as a standalone learning-improvement measure; no metric or behavior change has been made.
- Ran five further user-requested live repeats of `./scripts/run_experiment.py --flow 12 --stage 3 --replica 5 --max-iterations 100 --skip-build --csv 1`, all at default seed 2050 and `kernel` mode. Traces `runs/ibg-experiment-20260715T135835Z.jsonl`, `...T140306Z.jsonl`, `...T140346Z.jsonl`, `...T140411Z.jsonl`, and `...T140501Z.jsonl` reached equilibrium in 11, 11, 8, 7, and 8 slots respectively. First-to-final Total Realized End-to-End Utility increased in four traces by 13.20%, 34.26%, 14.52%, and 15.13%; it fell 5.78% in the first trace despite realized processing utility rising 2159.39 to 2793.92, because its transport penalty rose 707.14 to 1425.60. This confirms the metric measures actual end-to-end outcome, not a guaranteed monotonic learning trend. These are exploratory live repetitions outside the formal three-flow gate; no replay validation was run for them.
- Added `realized_end_to_end_utility.csv` to the optional host-side `--csv 1` reports. It exports each iteration's existing `realized_utility_total`—actual summed processing utility minus the measured transport/request-overhead penalty—without changing `aggregate_utility.csv`, trace schema, solver, learning, utility, SLA, or datapath behavior.
- Shortened newly generated metric-CSV experiment column identifiers from the full timestamp/configuration text to a deterministic six-character hexadecimal hash. The hash still covers timestamp, seed, flows, stages, and replicas; full provenance remains in JSONL, duplicate columns are rejected, and existing generated CSV data is not rewritten.
- Recalibrated the active end-to-end SLA threshold from 250 ms to 175 ms with explicit user authorization. The chosen value is near the 177.62 ms 75th percentile across 636 observed flow-iterations from six exploratory 12-flow Kernel traces, where 187 values (29.40%) exceed it; it replaces the uninformative 250 ms threshold that none exceeded. This changes SLA violation classification only.
- Tightened the user-directed equilibrium stopping tolerance from a strict per-entry belief change below 0.04 to below 0.03. The belief update, solver, placement, utility, SLA classification, and datapath are unchanged; future run iteration counts are not directly comparable with traces that used the former stopping condition.
- Changed the user-directed equilibrium stopping tolerance from a strict per-entry belief change below 0.03 to below 0.037. This changes only when an experiment stops; future iteration counts are not directly comparable with traces using either prior tolerance.
- Restored the user-directed equilibrium stopping tolerance from a strict per-entry belief change below 0.037 to below 0.04. This changes only when an experiment stops; future iteration counts are not directly comparable with traces using either temporary tolerance.
- Audited the paper's end-to-end-utility definition against the active implementation at user request. The paper deducts communication cost between consecutive selected replica hosts; the former `transport_overhead_ms` deduction was broad live request-minus-processing overhead rather than that pairwise cost. Historical traces retain their recorded semantics and must not be silently reinterpreted.
- Created repository-local `ibg backup/` before this correction and verified copies of all 15 Python scripts under `IBG/` against their pre-correction contents. The backup is an explicit snapshot and is not runtime input.
- Implemented the user-authorized correction without coupled placement. The flow generator now contacts only the selected first replica; selected replicas process and forward through the route in stage order. Each caller records one pair RPC measurement as `max(0, pair request duration - callee complete-route duration)`, producing exactly `K-1` correlated link records per flow. Only their sum supplies `link_latency_ms_per_flow`, end-to-end SLA latency, aggregate-utility deduction, and realized end-to-end utility deduction. Broad generator ingress/request overhead is separately labelled and excluded from the deduction.
- Preserved `/process` for compatibility and added `/process-route` only for execution of an already-selected route. At that revision, the exact decoupled solver, utility grid, route choice, selected-only processing-latency signal, likelihood/belief update, retention 0.8, no-rejection behavior, hard 175 ms SLA threshold, and then-active strict 0.03 equilibrium condition were unchanged. Pairwise measurements never enter placement.
- Updated the live/replay validators to accept historical request-overhead traces under their original schema and require complete, consecutive, formula-correct pair records plus separate non-negative ingress telemetry in new traces. At this pre-audit checkpoint, focused forwarding/adapter/validator checks and the then-complete 100-test suite passed; the later hardening and fresh trace are recorded below.
- Performed a complete post-implementation code audit without modifying behavior. The normal forwarding/deduction path and all 100 tests pass, but the audit proved four validation gaps: a pair-record sum can disagree with `link_latency_ms_per_flow` while the gate passes; wrong pair Pod/endpoint metadata is accepted; missing current-schema pair/ingress fields default to zero and can silently remove the deduction; and one trace can mix historical and pairwise schemas between iterations. Do not call the correction fully hardened or accept fresh new-schema evidence until these reporting/replay checks are fixed and tested.
- Closed all four reporting/replay audit gaps without changing the solver or datapath behavior: current route/flow pair and ingress fields are required, pair records are correlated to source/target Pods and normalized target endpoints, pair-cost sums must equal the deducted `link_latency_ms_per_flow`, and both baseline validation and replay reject mixed historical/pairwise schemas. Focused checks pass, the complete suite passes with 114 tests, all relevant Python sources compile, and `git diff --check` is clean.
- Rebuilt the local Kernel image and ran `./scripts/run_experiment.py --flow 3 --stage 3 --replica 5 --max-iterations 100` at seed 2050 from the hardening working tree based on commit `6023264`. Fresh trace `runs/ibg-experiment-20260715T171429Z.jsonl` reached the strict-0.03 equilibrium condition in 23 slots and contains 207 selected hops plus 138 pair records. Pair/ingress completeness, pair formula and metadata correlation, pair-sum/metric equality, and one-schema consistency all pass; all 23 slots replay with zero placement, belief, or mathematical drift. Its overall live Phase 3 gate is false because classification was 73.43% (required 80%) and only 77.78% of hops met the server-overshoot tolerance (required 95%). Treat this as successful reporting/replay evidence but failed live timing/classification evidence.
- Rebuilt after restoring the strict-0.04 equilibrium threshold and reran the same supported-size command at seed 2050. Trace `runs/ibg-experiment-20260715T173555Z.jsonl` records all 100 permitted slots but did not reach equilibrium, so the controller exited nonzero and it is not an accepted completed experiment. Its pairwise reporting checks and 100-slot replay pass with zero mathematical drift. Its exploratory live rates improved to 79.11% classification (still below 80%) and 82.56% server-overshoot tolerance (still below 95%) over 900 selected hops. Keep those rates distinct from acceptance because the run is incomplete.
- Investigated the latest trace with targeted configuration, hop, placement, timing, concurrency, state, load, and belief fields. The seeded modeled latencies classify at 99.89%, versus 79.11% from measured processing latency. Classification is 95.42% when the server-overshoot check passes but only 1.91% when it fails. Failures cluster at forwarding route positions and concurrency: stage 1/2/3 overshoot pass rates are 69.33%/80.00%/98.33%, while concurrency 1/2/3 rates are 92.68%/54.63%/33.33%. Load 1/2/3 rates are 95.09%/77.92%/72.59%. The first cold slot contributes nine failures but does not explain the 148 later failures; worker-node results are close, no replica Pod restarted, and sampled cgroup CPU-throttling counts are isolated and not stage-correlated.
- Localized the non-convergence mechanism without changing behavior. `ReplicaRuntime.process` measures wall elapsed time around `asyncio.sleep` and uses that value for likelihoods, so Python/OS coroutine wake-up delay enters the belief signal. Under pairwise forwarding, stage 1 and 2 Pods also create downstream HTTP clients and perform forwarding on the same Uvicorn event loop; terminal stage 3 does not. The additional scheduling delay pushes selected true-state-4 replicas toward state-3/state-2 likelihoods, after which corrective and noisy observations keep beliefs moving. Stage 1 replicas 1/5 or stage 2 replica 3 produced the largest belief delta in 94/100 slots; the smallest slot maximum was 0.041, so strict `<0.04` was never met. Historical same-seed generator-mediated execution reached equilibrium in 11 slots, while the new route traces reached 23 slots once and failed at 100 once, consistent with live scheduling sensitivity rather than solver drift.
- Disambiguated the late-iteration SLA concern. Three-flow trace `runs/ibg-experiment-20260715T173555Z.jsonl` has zero violations at iteration 100 and only six total flow-violations across three exceptional slots; 97/100 slots have none. Twelve-flow trace `runs/ibg-experiment-20260715T172332Z.jsonl` does have five violations at iteration 100, with every violating flow crossing 175 ms only after adding its measured pairwise link cost. The sole current `sla_violations.csv` column, hash `212f1e`, maps to the other 12-flow trace `runs/ibg-experiment-20260715T172851Z.jsonl`; that run stopped at iteration 49 with six violations and the CSV contains 49 data rows. The active 175 ms threshold was calibrated from pre-forwarding historical request-overhead traces, not the current pairwise schema, so current-schema SLA counts are exploratory until separately calibrated; no threshold change is authorized.
- Confirmed the user's broader before/after SLA concern with comparable late-slot evidence. Across the final five slots, two pre-forwarding 12-flow/5-replica traces under the 175 ms rule average 1.0 and 3.0 violations, while the two pairwise-forwarding traces average 5.4 and 5.0. Link-cost means did not rise; they fell from 89.33/103.02 ms to 83.31/82.57 ms. Mean per-flow processing rose from 68.80/65.11 ms to 87.84/88.06 ms because mean measured-minus-modeled overshoot rose from 0.87/1.20 ms per hop to 7.84/7.89 ms. In the new path the late-window overshoot is about 13 ms at stage 1, 9 ms at stage 2, and 1.2 ms at terminal stage 3. Thus the forwarding execution is contaminating local processing timing and causing the SLA regression. Reporting/replay remains correct, but the new path is not accepted live processing/SLA evidence until an explicitly authorized correction isolates forwarding work from the processing measurement.
- Implemented that authorized narrow correction in the uncommitted Phase 4 worktree. Each replica Pod now has a private processor on port 8081 and a public forwarder on port 8080. The processor alone measures selected processing and emits the likelihood; the forwarder only executes the controller-selected route and records pair telemetry. Processor readiness invokes a discarded sample through the same deterministic path, so first-use initialization is outside the measured signal without producing a controller observation or advancing the seeded experiment stream.
- Verified the correction with focused processor/forwarder isolation and reporting tests, then the complete suite: 120 tests passed. Relevant Python sources compiled, `docker compose --file deploy/local/compose.yaml config --quiet` passed, and the local container smoke test completed three concurrent three-hop flows with stage-1 concurrency `[1, 2, 3]`.
- Rebuilt and ran the supported command from the uncommitted correction worktree: `./scripts/run_experiment.py --flow 3 --stage 3 --replica 5 --max-iterations 100`. Fresh Kernel seed-2050 trace `runs/ibg-experiment-20260715T182717Z.jsonl` reached strict `<0.04` equilibrium in 10 slots. The Phase 3 baseline validator accepted it: 90 selected hops, 60 pair records, 98.89% categorical accuracy, 100% server-overshoot tolerance pass rate, complete pair/ingress/metadata/schema checks, and exact ten-slot replay with zero mathematical drift. This is accepted live evidence for the corrected route-forwarding runtime at the formal three-flow boundary.
- The first post-correction 12-flow attempt was deliberately interrupted and remains unusable. Its fresh replacement, `runs/ibg-experiment-20260715T183453Z.jsonl`, ran `./scripts/run_experiment.py --flow 12 --stage 3 --replica 5 --max-iterations 100 --skip-build` in Kernel mode at seed 2050. It reached equilibrium in eight slots; its 288 selected hops and 192 pair records replay exactly with zero mathematical drift. The final five slots average 69.99 ms processing/flow, 22.60 ms pair cost/flow, 0.0 SLA violations/slot, 1.39 ms processing overshoot/hop, and 98.89% state-classification accuracy across 180 hops. These are exploratory post-correction evidence only. Compared with the recorded pre-forwarding late windows (65.11--68.80 ms processing/flow, 89.33--103.02 ms link cost/flow, 1.0--3.0 SLA violations/slot, and 0.87--1.20 ms overshoot/hop), they show the prior forwarding-timer regression is absent while preserving a separately measured pair cost. The general baseline validator's `gate_passed=false` is expected: 12 flows is outside the formal supported configuration and incomplete load-one groups cannot meet that formal ordering check; classification, overshoot, pairwise integrity, schema consistency, equilibrium, and replay pass.
- Set the user-directed strict per-entry equilibrium tolerance from `<0.04` to `<0.033`. This affects only stopping time; it does not change the solver, placements, utility, selected processing signal, likelihoods, belief update, SLA classification, or forwarding behavior. Existing trace iteration counts remain tied to their recorded threshold.
- Added `--runs N` to `scripts/run_experiment.py`, defaulting to `1`. The launcher builds/deploys once, then starts N fresh controller Jobs with the requested same seed/configuration, records a distinct JSONL trace for each (using a run suffix when N is greater than one), and appends a distinct CSV column for each when `--csv 1` is used. Focused characterization/launcher tests pass (22 tests), Python compilation passes, and `--help` confirms the new option.
- Recalibrated the active end-to-end SLA classification threshold from 175 ms to 105 ms with explicit user authorization. The analysis used the final five slots of the ten newest completed forwarding-isolated 12-flow Kernel traces: 600 flow-iterations average 88.84 ms, with p90 108.46 ms and p95 113.78 ms. The former 175 ms rule flags 0/600; the new 105 ms rule flags 82/600 (13.67%). This changes SLA classification only; existing traces retain their recorded 175 ms classification.
- Set the active end-to-end SLA classification threshold to 110 ms with explicit user authorization. From the same 600 late-slot samples, 47 (7.83%) exceed 110 ms. This changes only future SLA classification; existing trace classifications remain historical.
- Corrected selected Kubernetes Pod endpoints to use an absolute headless-Service FQDN with a trailing DNS root label. The former non-absolute name could fail from a forwarding Pod because the resolver applied its search list; the correction is route-addressing only and does not change selection, solver, utility, learning, SLA, or telemetry semantics. Focused adapter/forwarder/validation/launcher checks passed (38 tests), as did the full suite (123 tests).
- Recreated the local `ibg` kind cluster after its control-plane node became unavailable following a network restart, then ran the normal build/deploy path at the supported three-flow/three-stage/five-replica configuration. Fresh trace `runs/ibg-experiment-20260718T104706Z.jsonl` reached the active strict `<0.033` equilibrium rule in 11 slots. The Kernel baseline validator accepted it: 99 selected hops, 66 pair records, 95.96% categorical accuracy, 100% server-overshoot tolerance pass rate, complete pairwise/ingress/schema checks, and exact eleven-slot replay with zero belief or mathematical drift.
- Implemented the Phase 4 `control_plane_v1` measurement branch without changing solver or datapath behavior. Each completed Kubernetes slot now separates discovery/admission/feedback active control work from selected-route wait, records monotonic-wall and controller-CPU time, and counts only controller-boundary HTTP application payloads/messages. Forwarder-to-forwarder RPCs remain excluded. `scripts/control_plane_summary.py` validates traces and reports per-run median/p95 values. Deterministic focused checks and the full suite pass (127 tests). After a normal rebuild, supported trace `runs/ibg-experiment-20260718T115336Z.jsonl` passed the live Kernel gate and exact 11-slot replay. Five independent supported repeats `115438-run001` through `115510-run005` also passed the Kernel gate with 96.67--98.99% classification, 100% overshoot-tolerance rates, and zero replay drift; every slot recorded eight controller-boundary messages.
- Added the separate `learning_signal_v1` logical footprint to the completed Phase 4 measurement branch. It canonically projects only stage, flow, selected replica, assigned load, selected processing-latency signal, and four-state likelihood; diagnostic route/transport fields remain part of the independently measured full `selected_telemetry_rx` response. Validation requires exactly `flows * stages` records and reproduces the footprint from trace observations. The metric is a canonical application-schema size, not current HTTP or TCP/IP wire bytes and not a raw-telemetry savings comparison. Focused checks and the full suite pass (132 tests). Final-code normal-build supported trace `runs/ibg-experiment-20260718T123226Z.jsonl` equilibrated in 11 slots, passed every Kernel gate with 98.99% classification and 100% overshoot compliance, and replayed with zero drift. Each slot recorded nine selected signals; median logical footprint was 1,861 bytes (206.78 bytes/selected hop), while the separately measured full selected-telemetry response median was 8,810 bytes.
- Added `logical_learning_footprint.csv` to the optional host-side `--csv 1` reports. For a complete `learning_signal_v1` trace it appends one deterministic run-ID column containing `logical_payload_bytes` for each completed slot, alongside the existing metric columns. Old traces with no learning-signal block keep their historical CSV set; traces that mix presence across slots fail rather than synthesize values. This is reporting-only and retains the logical-size—not HTTP/wire-byte—meaning. Focused exporter tests pass; the current full suite passes (138 tests).
- The user marked the bounded control-plane/learning-signal measurement branch complete and resumed Phase 4 for the remaining reporting curation. This does not complete Phase 4 overall or authorize Phase 5, DPDK/VPP, host preflight, coupled IBG, rejection, or any solver/datapath change.
- The user marked the first legacy-chart compatibility refresh final. `Chart/jain/` is self-contained: `jain.py` discovers exactly one sibling `*_IBG.csv` run-column input as IBG-Exact, or requires explicit `--input` when none or several match; it writes its default image beside the script and no longer reads shared `figures/`. Its original visual design/theme and embedded text are preserved unless the user explicitly requests a change: the IBG series is orange, DRL green, Greedy red, MILP uses the original default line style, the figure is 12x6 with a lower-right legend, and the grid uses alpha 0.5. Same-folder `jain_index_milp.csv`, `jain_index_drl.csv`, and `jain_index_greedy.csv` remain optional modular legacy baselines, while explicitly supplied files retain their prior semantics. The title is a `--title` runtime setting because report names can change. Absent baselines do not block the current plot. Focused tests pass; every other Chart script remains opt-in and must be explicitly named.
- The user marked SLA-small version 2 final. `Chart/sla-small/2/sla-small.py` is self-contained: it discovers one sibling `*_IBG.csv`, accepts current headered run columns, preserves the original orange IBG line, 12x6 layout, labels, title form, integer timeslot axis, five-slot moving average, and first-50-timeslot view, and writes its PNG beside the script. The legacy MILP file is optional; when present, it retains the original forced-zero reference-line behavior. This figure is due to and scoped to the small-scale experiment, not a large-scale/general SLA claim. Its focused tests pass.
- The user marked utility-small final. `Chart/util-small/util-small.py` is self-contained: it discovers `realized_end_to_end_utility_IBG.csv` beside the script, preserves the original orange IBG mean and standard-deviation band, applies a trailing five-timeslot moving average, forces integer timeslots, uses a 2,500--3,500 y-axis, and writes `realized_end_to_end_utility.png` beside the script. Its title is `Aggregated Realized End-to-End Utility of IBG-Exact on small-scale topology`; its optional local MILP series is omitted cleanly when unavailable. Focused tests pass.
- Implemented the user-authorized physical/observation jitter separation in the Phase 4 side branch. Physical selected processing remains `half-normal-additive-v1` with state scales 6/5.25/4/3.25 ms and alone supplies processing utility and SLA latency. The selected-only learning signal now adds independent nonnegative `half-normal-observation-v1` noise with state scales 7.2/6.3/4.8/3.9 ms; its likelihood is the exact convolution of the physical and observation half-normal laws. Runtime, adapters, traces, replay, and validators correlate modeled/measured physical latency, observation jitter, and noisy signal separately. The seed-2050 5,000-sample calibration passes with 81.38% minimum categorical accuracy and 87.74% mean load-1 accuracy under the declared 80% minimum/90% low-load maximum, unchanged 3/5/7/11 crossings and sensitivity bands, and an unchanged physical-only modeled SLA gate. The full suite passes with 162 tests and all Python sources compile. Fresh normal-build supported live validation and exact replay are still pending; `runs/ibg-experiment-20260719T125810Z.jsonl` remains version-bounded to the superseded 8/7/5.5/4.5-ms physical profile.
- Investigated a new exploratory 15-flow/8-replica runtime regression without changing behavior. Runs `runs/ibg-experiment-20260721T130536Z-run001.jsonl` and `...T130912Z-run002.jsonl` reached equilibrium but ended with 10/15 and 13/15 SLA violations. Their final physical processing means were 67.01/70.74 ms per flow and pair-cost means 50.95/60.36 ms, yielding end-to-end means 117.96/131.10 ms; no final flow exceeded 110 ms before pair cost was added. A pre-observation-jitter 15x8 trace already had 14/15 final violations and 74.39 ms mean pair cost, so the separated model is not a proven direct cause. The new likelihood adds only about 0.0035 ms per call locally and is excluded from SLA/utility, though its beliefs can affect routes indirectly. The same traces average 14.79/15.11 s per slot versus 8.09/8.12 s in good same-size runs; control-plane data attributes the difference to controller admission CPU (about 14.65 vs 7.89 s), not selected-route wait (about 0.42 vs 0.23 s). Selected forwarder cgroup snapshots show 39--47 CPU-throttling events and 1.54--2.16 s cumulative throttled time under their 500m limit, versus negligible processor throttling. This is a plausible pair-RPC residual cause, not proof: next work must collect per-run/per-slot deltas and run a same-environment A/B before changing resources or the model.
- Completed that controller-runtime diagnosis and repair without altering IBG behavior. A 15x8 exact stage has 490,314 memoized load states; the recursive `lru_cache` wrapper held each completed policy's table through a self-cycle, accumulating roughly one full cache per stage until the 1 GiB controller limit OOM-killed both prior runs after five slots. The exact policy now uses a compact load-state cache key and clears its memo table in a `finally` block immediately after placement. This preserves the recurrence, candidate set, utility grid, placement order, and tie rule. Local tests prove all stage caches clear from 490,314 to zero; `runs/ibg-experiment-20260721T144252Z.jsonl` completed 19 15x8 slots after a normal build/deploy, had zero controller OOM events at about 207 MiB observed memory, and exact-replayed with zero drift. Its median elapsed/admission/controller-CPU time was 10.41/10.06/9.91 s.
- Completed the prescribed selected-forwarder cgroup/learning-mode A/B. The separated-mode diagnostic trace had zero selected-forwarder throttling deltas across 299 samples; the physical-only diagnostic had one 6.104 ms delta that did not align with a high pair cost. The probes add route-wait work, so a clean no-probe control was retained. The forwarder-throttling hypothesis is not confirmed; do not apply the proposed 100m/1-CPU forwarder-resource change. Pair-RPC residuals remain high in the repaired trace (59.05 ms all-slot mean, 111.01 ms p95; final 71.04/62.06/133.10 ms physical/pair/end-to-end mean and 14/15 SLA violations), which is a separate unresolved exploratory runtime question.
- Fresh current-image supported trace `runs/ibg-experiment-20260721T145856Z.jsonl` was taken after the successful normal build/deploy, then with `--skip-build` only as permitted. It reached strict `<0.033` equilibrium in 16 slots, passed the Kernel gate with 86.11% classification and 97.22% overshoot compliance, and exact-replayed all 16 slots with zero drift. The full suite now passes: 172 tests.
- Recorded a concise exploratory Kernel 15x8 comparison baseline in `baselines/kernel_15x8_latency_baseline_20260721.txt`. The two same-image, same-seed clean traces (`runs/ibg-experiment-20260721T154817Z-run001.jsonl` and `...T154949Z-run002.jsonl`) finished with 0/15 SLA violations, 20.75/21.54 ms final mean pair cost per flow, 87.49/87.45 ms final end-to-end mean, and 3142.69/3143.25 realized utility. A separately labeled cgroup-diagnostic run (`...T161704Z`) also reached 0/15 final SLA violations: across 420 selected pairs it had 48.10% same-worker and 51.90% cross-worker routes, and its 259 selected-forwarder snapshots recorded zero CPU-throttling deltas. This demonstrates that the current system can produce healthy 15x8 results; it is a comparison snapshot, not a new formal support gate or an explanation for prior transient pair-route variance.
- Recorded a provisional post-reboot kind-cluster recovery incident. In the persisted `ibg` cluster, controller readiness intermittently failed with `Temporary failure in name resolution`, while fresh route attempts could fail at flow-generator with `ReadTimeout`; all replicas could nevertheless be Ready and directly health-reachable. CoreDNS and kindnet had restarted after the reboot. Rebuilding the runtime image and restarting workloads did not cure the incident. Deleting exactly the three disposable kind node containers via `kind delete cluster --name ibg`, then letting the launcher recreate the cluster, restored operation. This is an evidence-backed workaround, not a confirmed root cause; reproduce and capture Docker/kindnet/CoreDNS/kube-proxy/node DNS and cross-node route evidence next time before deletion.
- Hardened the controller's flow-generator endpoint to the absolute namespace FQDN with a trailing root label and retained exception class plus `repr` in flow-generator/forwarder HTTP failure reports. These diagnostics do not change solver, route selection, telemetry, learning, utility, SLA, or equilibrium semantics. The full suite passed (148 tests).
- After recreating the cluster, `./scripts/run_experiment.py --flow 3 --stage 3 --replica 5 --max-iterations 100 --skip-build` produced `runs/ibg-experiment-20260719T112850Z.jsonl`; it reached the active strict `<0.033` equilibrium rule in ten iterations. Treat this as successful post-recovery operational evidence pending the usual gate/replay curation.
- `ibg backup/` is a user-controlled pre-correction snapshot, ignored by Git. Do not read or inspect it unless the user explicitly requests that action.

## Environment facts

- Host hardware and operating-system details are not a stable project contract; record them with an individual experiment when they materially affect an interpretation.
- The active checkout for this workspace is `/home/vhakami/Desktop/projects/vesal/SFC-with-IBG`.
- Native Docker Engine is active and normal-user Docker access is configured.
- The `ibg` kind cluster is running Kubernetes 1.36.1 with one Ready control-plane node and two Ready workers. The `ibg-testbed` namespace currently has twenty-four Ready replica Pods, one Ready `kernel` flow-generator Pod, and a successfully completed exploratory 15x8 diagnostic experiment Job.
- The current project root is a Git repository on branch `IBG`, with `origin` configured for `ShamsAli-fathi/SFC-with-IBG`.
- Docker Hub returned HTTP 403 for the initial Python base-image pull, so the local runtime image uses the official Azure Linux Python 3.12 base from Microsoft Container Registry. This is a packaging workaround, not a change to runtime behavior.
- `Chart/` is a user-controlled, currently untracked legacy plot-script area. It is opt-in: future work may inspect only its `.py` scripts when explicitly requested, may edit them only on explicit request, and must not stage, commit, or push them without separate explicit approval.

## Current state

Expansion Phase 3 remains implemented locally. Phase 4 is in progress for reporting curation; its bounded `control_plane_v1`/`learning_signal_v1` and separated-jitter branches are complete, while Phase 4.1 Kernel-forwarder-concurrency diagnosis remains open. Actual selected processing uses the supported `half-normal-additive-v1` physical state scales 6/5.25/4/3.25 ms. Belief learning retains its independent selected-only `half-normal-observation-v1` noise exactly at 7.2/6.3/4.8/3.9 ms with the matching convolved likelihood. Observation noise never enters any outcome metric. Because the raw pair residual remains unresolved, the user authorized the reversible `physical-only-v1` outcome contract: observed selected physical processing supplies active realized utility and the 110-ms SLA. Raw pair cost, raw end-to-end latency, and physical-plus-pair utility remain logged; `physical-plus-pair-v1` restores the prior outcome behavior. This may be temporary or permanent and needs a fresh normal-build live run plus replay; no experiment is to be run by the agent for this change. Current-image supported trace `runs/ibg-experiment-20260721T145856Z.jsonl` remains formal evidence for its previous, version-bound contract. The 15x8 controller-memory regression is repaired by immediate exact-policy cache disposal after stage placement. Phase 4.1 now runs two Uvicorn workers only in each public forwarder, with 25m/1-CPU request/limit and 128/256 MiB memory; each private processor remains single-worker and unchanged. The existing Kubernetes HTTP path remains the explicit `kernel` baseline. Pairwise reporting/replay hardening and private-processor/public-forwarder isolation remain intact. The exact decoupled solver and placements are unchanged, pairwise costs cannot influence selection, and retention 0.8, strict per-entry equilibrium tolerance below 0.033, no rejection, and the formal three-flow support boundary remain fixed. DPDK/VPP and coupled IBG remain unimplemented and unclaimed.
Expansion Phase 3 remains implemented locally. Phase 4 is in progress for reporting curation; its bounded `control_plane_v1`/`learning_signal_v1` and separated-jitter branches are complete, while Phase 4.1 Kernel-forwarder-concurrency diagnosis remains open. Actual selected processing uses the supported `half-normal-additive-v1` physical state scales 6/5.25/4/3.25 ms. Belief learning retains its independent selected-only `half-normal-observation-v1` noise exactly at 7.2/6.3/4.8/3.9 ms with the matching convolved likelihood. Observation noise never enters any outcome metric. Because the raw pair residual remains unresolved, the user authorized the reversible `physical-only-v1` outcome contract: observed selected physical processing supplies active realized utility and the 110-ms SLA. Raw pair cost, raw end-to-end latency, and physical-plus-pair utility remain logged; `physical-plus-pair-v1` restores the prior outcome behavior. This may be temporary or permanent and needs a fresh normal-build live run plus replay; no experiment is to be run by the agent for this change. Current-image supported trace `runs/ibg-experiment-20260721T145856Z.jsonl` remains formal evidence for its previous, version-bound contract. The 15x8 controller-memory regression is repaired by immediate exact-policy cache disposal after stage placement. Phase 4.1 now runs two Uvicorn workers only in each public forwarder, with 25m/1-CPU request/limit and 128/256 MiB memory; each private processor remains single-worker and unchanged. The existing Kubernetes HTTP path remains the explicit `kernel` baseline. Pairwise reporting/replay hardening and private-processor/public-forwarder isolation remain intact. The exact decoupled solver and placements are unchanged, pairwise costs cannot influence selection, and retention 0.8, strict per-entry equilibrium tolerance below 0.033, no rejection, and the formal three-flow support boundary remain fixed. DPDK/VPP and coupled IBG remain unimplemented and unclaimed.

The opt-in `solver_resource_v1` branch is complete behind `--memory 1`. Every completed enabled slot records current controller RSS before admission, a 5-ms sampled active-slot peak, RSS after feedback, peak incremental working-memory bytes, exact-policy peak/residual memo-entry counts, and per-stage cache records. Default runs emit no solver-resource block. Validation rejects incomplete/inconsistent mode/schema combinations, replay validates the captured resource block without comparing nondeterministic RSS to simulation, and `scripts/solver_resource_summary.py` reports bytes/MiB separately from cache entries. Deterministic fixtures prove the cache is still cleared and seeded placement/outcome results are unchanged; the complete non-Chart suite passes with 171 tests. User-run normal-build exploratory trace `runs/ibg-experiment-20260722T112356Z.jsonl` completed 13 15x8 slots with valid data: 490,314 peak memo entries per stage, zero post-clear residual entries, 255.5 MiB maximum controller RSS, and 97.44 MiB maximum incremental memory. It is an Exact reporting baseline under the shared schema, not a supported-size Kernel gate. No heuristic implementation is authorized now.

The user-authorized forwarding-path diagnostic is implemented and has fresh normal-build live evidence. `--forwarding-path-diagnostics` emits opt-in `forwarding_path_v1` values for each selected pair: source-to-target-handler, target-handler, and target-finish-to-source durations, derived from shared Unix-epoch boundaries. It leaves `link_cost_ms` and every mathematical/runtime input unchanged. Exploratory trace `runs/ibg-experiment-20260721T180604Z.jsonl` completed 23 slots and exact-replayed all 23 with zero placement, observation, belief, or mathematical drift using the deterministically expanded 15x8 profile set. Its 690 pair records validate under `scripts/forwarding_path_summary.py`: mean source-to-target-handler time was 18.18 ms (p95 40.11), versus 4.71 ms (p95 11.36) from target finish to source receipt. These two segments sum to the mean 22.89-ms pair deduction; target-handler time is deliberately excluded from that deduction.

The authorized diagnostic-only follow-up is implemented as `forwarding_path_v2`. It keeps the three v1 aggregates and adds target application ingress/dispatch, private-processor request/ingress/handler/work/response, optional downstream-route wait, handler completion, and source local-response-to-outbound-request timing. The existing `--forwarding-path-diagnostics` flag enables it; ordinary runs do not carry these fields. Current flow-generator and Kubernetes adapters reject incomplete/stale diagnostic responses, while `scripts/forwarding_path_summary.py` remains compatible with historical v1 traces and reports v2 components globally and per stage pair. Pair cost, processing latency, routing, solver, learning, utility, SLA, and equilibrium calculations are unchanged. Focused checks pass (76 tests), and the complete non-Chart suite passes (173 tests).

A no-controller fixed-route diagnosis establishes the metric-level cause of the residual: concurrent requests queue in the existing public-forwarder HTTP path. From `stage-1-0`, sequential two-hop calls had a 4--5 ms pair cost on both same-worker and cross-worker routes. Fifteen simultaneous calls reproduced 23--38 ms first-wave pair costs, primarily before the destination handler began. At the actual selected-target fan-in range, six simultaneous calls produced 9.46, 21.07, and 24.50 ms mean pair costs across three waves, compared with 3.99--6.10 ms for one request. Direct concurrent health/cgroup probes also queued with separate HTTP clients, so HTTP connection-pool sharing is not established as the sole cause. The established cause is instead application-level concurrent HTTP/1.1 scheduling/queueing across single-Uvicorn-worker public forwarders and their co-located processor calls; the current pair metric intentionally includes that real selected-route work. The behavior occurs both within and across workers, is unrelated to an internet/DNS outage, and was not accompanied by proven CFS throttling. Do not normalize it out, change the solver, or alter SLA/utility/pair semantics. This is a same-clock Kernel diagnosis, not a wire or cross-host latency claim.

The explicitly authorized Phase 4.1 runtime correction is implemented but remains open. A one-worker forwarder peaked at 52.4 MiB. Public forwarders now run two Uvicorn workers; private processors remain single-worker. Forwarder memory request/limit is 128/256 MiB. The initial two-worker test retained the 500m CPU cap and exposed correlated quota stalls, so measured A/B evidence justified a 1-CPU limit while preserving the 25m request. At the accepted resources, 30 fixed-route waves recorded zero source/target throttle deltas; five-wave same-/cross-worker means were 6.57/5.75 ms at concurrency six and 7.73/8.01 ms at concurrency fifteen. Maximum observed forwarder memory was about 141 MiB, with no pressure event, OOM, or Pod restart.

Normal-build diagnostic trace `runs/ibg-experiment-20260721T191126Z.jsonl` completed 17 slots with forwarding-path and cgroup diagnostics and recorded zero selected-forwarder route-time throttle deltas. Clean same-image trace `runs/ibg-experiment-20260721T191634Z.jsonl` completed 12 slots with only forwarding-path diagnostics. Against the one-worker diagnostic trace `runs/ibg-experiment-20260721T180604Z.jsonl`, its all-slot pair mean/p95 fell from 45.78/80.09 to 36.81/63.22 ms per flow, while source-to-target-handler mean/p95 fell from 18.18/40.11 to 13.65/31.72 ms. Its final physical/pair/end-to-end means were 67.71/27.58/95.29 ms; it ended at 0/15 SLA violations and realized utility 3025.72. Exact replay matched all 12 slots with zero drift. Later cgroup-plus-forwarding trace `runs/ibg-experiment-20260721T193017Z.jsonl` ended at 0/15 final SLA violations but was not stable: slot 6 had 15/15 violations and 67.81 ms pair cost per flow, while slots 6/9 had source-to-target-handler means 25.19/20.30 ms and target-handler means 88.87/77.38 ms. Its cgroup deltas were still zero in every slot, and selected-target fan-in did not exceed four in the worst slot. Therefore the remaining residual is not proven to be CPU quota throttling or replica concentration; the current timestamps cannot distinguish source-forwarder, destination-forwarder, and private-processor waiting. Focused checks pass (50 tests), Compose resolves, and the complete non-Chart suite passes (171 tests); the user-controlled Chart test was excluded under its repository guardrail. Earlier one-worker healthy traces still have lower final pair means (20.75/21.54 ms), so Phase 4.1 remains an incomplete mitigation, not a universal performance guarantee or a formal 15x8 gate.

The first normal-build live v2 trace is `runs/ibg-experiment-20260721T202043Z.jsonl`. It completed 15 slots with 450 complete v2 pair records and exact-replayed with zero belief and mathematical drift. Every selected-forwarder cgroup delta was zero; all 24 replica Pods remained Ready with zero restarts. All-slot pair cost was 44.24 ms/flow mean and 73.80 ms p95. The final physical/pair/end-to-end means were 65.41/33.37/98.78 ms, with 2/15 SLA violations and realized utility 2973.26. Per selected link, source local-response-to-request preparation averaged 0.10 ms, source request to target ASGI ingress 13.48 ms (p95 34.55), target ingress-to-handler dispatch 2.97 ms (p95 9.45), and target-handler finish to source response 5.68 ms (p95 15.07). Same-worker and cross-worker link means were effectively equal at 22.06/22.18 ms. The observed pair volatility is therefore concentrated in HTTP/runtime admission and response boundaries outside the modeled private work, not in CFS throttling or cross-worker locality. The dominant source-request-to-target-ingress boundary still combines source HTTP-client waiting, Kernel/network transit, and pre-ASGI target admission, so Phase 4.1 remains open.

The diagnostic split is complete with active `forwarding_path_v3` and `http_client_path_v2`. Normal-build trace `runs/ibg-experiment-20260721T205120Z.jsonl` completed 14 slots with 420 complete links; 418 opened new TCP connections. HTTP pool wait averaged 2.63 ms (p95 7.80) and connect averaged 7.31 ms (p95 19.14), within a 13.23-ms request-to-target-ingress mean. Inter-slot idle gaps were consistently 7.74--8.08 seconds, while HTTPX client keep-alive expiry and Uvicorn server keep-alive timeout were then both 5 seconds. Thus nearly all connections expired before the next burst, directly explaining repeated connection setup and much of the pair variance. The matched 30-second downstream client/server keep-alive A/B is active; local processor calls use a separate processor-compatible default HTTPX pool. Its normal-build trace `runs/ibg-experiment-20260721T210935Z.jsonl` completed 14 slots and 420 links, but opened only 243 TCP connections (42.14% reuse). Mean request-to-target-ingress fell from 13.23 to 11.38 ms, confirming the predicted connection reuse. The all-slot pair mean changed only from 43.22 to 42.19 ms/flow and its upper tail remained unstable, so the correction is incomplete. The original shared client caused a local stale-connection `ReadError`; normal-build same-shape validation trace `runs/ibg-experiment-20260721T213938Z.jsonl` completed all 18 slots without it and reached equilibrium. Every cgroup throttle delta in the A/B remained zero; all 24 replica Pods were Ready with zero restarts. The complete non-Chart suite passes with 177 tests before this split; the updated focused suite passes 51 tests.

On 2026-07-22, a no-controller warm-connection fixed-route probe used the live flow-generator Pod to call the fixed public route `stage-1-0 -> stage-2-0` with v3 telemetry; it made no deployment or model change and is not a controller trace. Twelve discarded warm requests left 11 reused downstream connections and had a 6.27-ms pair mean. Three subsequent six-request waves reused every connection and measured 6.70, 9.82, and 5.38-ms pair means (maximum 14.82 ms). The first fifteen-request wave created 8/15 connections and measured 13.54 ms mean/33.44 ms maximum, with 4.29 ms mean connect time. The next two fifteen-request waves reused all connections and measured 9.44/7.59-ms means with 16.87/11.41-ms maxima. This confirms that reconnects drive the initial high-concurrency tail; it also retains a smaller reused-connection residual spread over pool wait, ingress, target admission, and response return. Every replica Pod remained Ready with zero restarts afterwards. No runtime, resource, solver, learning, SLA, utility, jitter, or pair-cost change is justified by this one route.

The 2026-07-22 placement matrix repeated the same warm protocol across two same-worker and two cross-worker fixed routes. Every second/third fifteen-request wave reused all 15 downstream connections. Same-worker `stage-1-0 -> stage-2-2` measured 9.43/8.36-ms pair means and `stage-1-1 -> stage-2-0` measured 7.47/6.15 ms; cross-worker `stage-1-0 -> stage-2-0` measured 8.52/11.21 ms and `stage-1-1 -> stage-2-2` measured 7.83/13.05 ms. The last cross-worker wave peaked at 29.07 ms despite complete reuse, with elevated pool/ingress/return means of 3.38/6.02/5.11 ms. Thus Pod locality does not explain the residual: both placement classes can be low or elevated. All four Pods stayed Ready with zero restarts. The next authorized diagnostic adds request-correlated public-forwarder worker-process identity to distinguish per-Uvicorn-worker scheduling from broader shared runtime variation, while preserving the v3 boundaries and all metrics. If it is inconclusive, collect only read-only host/runtime scheduling, Docker/kind, and relevant network/conntrack observations during the same warmed fixed-route probes; this is not host preflight and must not change host configuration.

On 2026-07-27, that worker/runtime diagnostic completed without a mitigation change. `forwarder_runtime_v1` adds correlated public-forwarder worker PIDs, active diagnostic handler/request counts, bounded 5-ms event-loop scheduling-lag windows, and best-effort source socket metadata to `forwarding_path_v3`; summary schema v4 keeps historical v1/v2/v3 support. Worker identity, sockets, locality, active application concurrency, zero cgroup throttle deltas, and the bounded read-only host CPU/IO-pressure/load, Docker/kind, and conntrack observations did not identify a single bad actor. Fixed warmed waves nevertheless showed real reused-connection spikes: a 15-request all-reused wave averaged 29.52 ms, with 8.51-ms mean source loop maximum lag. Fresh normal-build exploratory trace `runs/ibg-experiment-20260727T105911Z.jsonl` completed 18 slots and exact-replayed with zero drift. Across all 540 links, pair cost correlated 0.705 with source loop maximum lag; its 55 p90-tail links averaged 40.41 ms source loop maximum lag versus 7.95 ms in the lower half, and the association remained among reused sockets. This supports intermittent source public-forwarder scheduling/descheduling as a proximal contributor, but does not establish whether the delay is Python/ASGI event-loop work or OS/runtime descheduling. `pool_wait_ms` remains a historical label for source pre-transport time, not proof of a capacity-pool queue. Socket groups are scoped by source Pod, worker PID, and local port; the flow-generator and adapter now validate the full source-worker chain. Focused checks pass (52 tests) and the complete non-Chart suite passes (176 tests). All 15x8 results remain exploratory.

The bounded `netem_v1` robustness branch is complete. The launcher accepts opt-in `--netem 1` plus delay/jitter values; default runs deploy no impairment. Each enabled replica Pod applies a normal-distribution `tc/netem` qdisc to `eth0` through a completed `NET_ADMIN` init container, and the full configuration is present in every trace event. The runtime image includes `iproute-tc`; no host qdisc is changed. `scripts/network_impairment_summary.py` validates metadata and reports posterior, selected-state mix, prediction accuracy, utility, and SLA without changing any metric.

Normal-build exploratory trace `runs/ibg-experiment-20260727T122310Z.jsonl` used 10 flows, three stages, six replicas per stage, 10-ms delay, and 3-ms jitter. It reached equilibrium in 18 slots; mean true-state posterior rose from 0.362 to 0.833, selected Good/Excellent share rose from 80.67% in the first five slots to 100% in the final five, selected categorical accuracy was 92.04%, and the final slot had zero SLA violations. Matched no-netem trace `runs/ibg-experiment-20260727T122446Z.jsonl` reached equilibrium in 12 slots, raised mean true-state posterior from 0.361 to 0.807, and also reached 100% Good/Excellent selection over the final five slots. Both exact replays pass with zero mathematical and belief drift; their overall formal Phase 3 gate is intentionally not claimed at this exploratory 10x6 size. The focused netem/configuration/launcher suite passes 34 tests, the complete non-Chart suite passes 210 tests, byte-compilation passes, and `git diff --check` is clean. Packet loss remains deferred because a dropped route currently fails the slot.

## Next action

All DPDK/VPP work is now deferred until further notice. The dormant `dpdk_vpp_preflight_v1` and `--datapath dpdk-vpp` launcher choice remain as future reference only; do not invoke, extend, test, or document them further without explicit user authorization. Kernel remains the only deployable/default mode. No host change, image build, deployment, DPDK traffic, or experiment was performed.

The current IBG-Exact chapter is temporarily frozen as the reproducible reference baseline. The next intended chapter is IBG-Hybrid, but it is not started and no heuristic/hybrid implementation is authorized until the user provides its design and scope. Preserve every Exact solver, learning, outcome, telemetry, runtime, and evidence contract unchanged. Separately, the next bounded Phase 4.1 diagnostic remains read-only per-worker scheduler/context-switch evidence and still requires explicit authorization. Report refinement remains user-directed; Report.md, Tutorial.md, and EVIDENCE_SUMMARY.md remain opt-in.

## Active IBG-Hybrid scope update

The preceding paragraph records the earlier handoff state. The user has now
provided and authorized the initial IBG-Hybrid scope. IBG-Hybrid is the active
development track; IBG-Exact remains frozen as its reproducible reference.

The authorized purpose is coupled/budgeted SFC placement using one complete
route per flow. Candidate pruning, limited lookahead, and Monte Carlo are
internal parts of one IBG-Hybrid algorithm. The starting configuration is 20
flows, 3 stages, and 10 replicas per stage.

Hybrid should directly reuse the current Exact latency model, separated
physical and observation jitter, exact convolved likelihood, selected-only
learning, retention 0.8, outcome/SLA contracts, adapters, structured
telemetry, private-processor/public-forwarder split, and Kernel Kubernetes
runtime. Only the coupled route-selection logic and Hybrid-specific solver
measurements/replay should differ. This reuse must not change Exact behavior
or invalidate Exact evidence.

The existing `IBG_Hybrid/` Python files are an old standalone revision. The
confirmed gaps are:

- It defaults to 50 flows and 80 replicas per stage.
- Its `budget` value is not enforced.
- It selects two replicas across two stages rather than one replica from all
  three stages.
- Its planner omits link coupling that is added later during reporting.
- Its synthetic link cost reads hidden true replica states.
- Its rollout counts the starting action's immediate value twice.
- Its Monte Carlo generator lacks experiment seed provenance.
- Its replica, utility, signal, belief, SLA, equilibrium, CSV, and output
  behavior predate the active Exact contracts.
- It has no adapter-based Hybrid runner or Kubernetes integration.

The next action is Hybrid Phase 0 in `ROADMAP.md`: freeze deterministic
paper-aligned meanings for action, budget, feasibility, pruning size,
lookahead value/depth, Monte Carlo continuation, activation rules, and seed
ownership, then add characterization fixtures before changing the solver.

Diagnosis-script compatibility is an explicit later phase after lookahead and
baseline Kernel integration. `netem_v1` is postponed until the core Hybrid
simulation and replay are stable.

The paper's bandit-based adaptation is recorded as optional Hybrid Phase 10.
It is deferred until the required pruning/lookahead/Monte-Carlo policy is
validated and must preserve the same selected-only information boundary.

### IBG-Hybrid budget-action correction

The active user-defined Hybrid model is `L=2`: each flow chooses exactly two
replicas from two distinct stages out of three and bypasses the remaining
stage entirely. The prior appended description of one complete three-stage
route and the statement that the old two-stage action was a gap are superseded
by this clarification. The old prototype still needs its budget enforcement,
link/coupling, rollout, latency/learning, adapter, and Kubernetes work.

`IBG_Hybrid/budgeted.py` now defines `HYBRID_STAGE_BUDGET = 2` as the
code-level source of truth. The current planner rejects another supplied value
until its two-stage action, embedding, traffic, replay, and tests are
deliberately generalized.

Because the Exact flow-generator contract currently requires contiguous stages
beginning at stage 1, Hybrid needs a versioned route-execution extension for
two selected stages that may be noncontiguous or begin after stage 1. The
private processor, public forwarder, and selected-only observation boundary
remain reusable.

The professor-directed Kernel robustness check is now available without altering that baseline: use `--netem 1 --netem-delay-ms D --netem-jitter-ms J` for replica-Pod egress delay/jitter and compare it with a same-shape `--netem 0` run. The initial 10x3x6 matched run is complete and favorable but exploratory. Do not add packet loss, retries, missing observations, or a new learning-noise interpretation without separate scope.

## New-thread handoff prompt

> Continue in `/home/vhakami/Desktop/projects/vesal/SFC-with-IBG` on branch `IBG`. First read `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`, and `STATUS.md`. Do not read or edit `Tutorial.md`, `Report.md`, `EVIDENCE_SUMMARY.md`, `ibg backup/`, or `Chart/` unless explicitly asked. Do not commit or push.
>
> Phase 4 reporting curation remains active. DPDK/VPP is deferred until further user notice; ignore its dormant preflight and launcher option unless the user explicitly reopens that scope. Preserve the exact decoupled solver, linear `u(q)=99-q`, selected-only learning, retention 0.8, no rejection, raw post-placement pair-cost measurement, and strict equilibrium `<0.033`. Do not begin coupled IBG, DPDK/VPP, host preflight, rejection, or another phase.
>
> A dormant `dpdk_vpp_preflight_v1` and launcher `--datapath {kernel,dpdk-vpp}` reference remain from a bounded assessment, but Kernel is the only deployable runtime and unchanged default. Do not invoke or modify those DPDK/VPP parts until explicit user authorization.
>
> The current IBG-Exact chapter is temporarily frozen as the reproducible reference baseline. The next intended chapter is IBG-Hybrid, but no hybrid/heuristic design or implementation is authorized yet: wait for the user's requirements, then turn them into a bounded architecture and measurement plan before changing code. Do not alter Exact solver behavior, cache disposal, learning, jitter/outcome/SLA contracts, telemetry, Kernel runtime, or evidence while preparing that plan.
>
> The two preceding Hybrid-prohibition statements are retained as historical handoff text. They are superseded by the active Hybrid scope recorded above and in the current `ARCHITECTURE.md`, `DECISIONS.md`, and `ROADMAP.md`.
>
> Current scope: IBG-Hybrid is the active development track. Implement it as a coupled complete-route decision engine with pruning, limited lookahead, and Monte Carlo inside one public algorithm, starting at 20 flows/3 stages/10 replicas. Reuse the frozen Exact latency, separated-jitter learning, outcome, adapter, telemetry, processor/forwarder, and Kernel Kubernetes contracts without changing Exact behavior or evidence.
>
> The bounded `netem_v1` robustness wrapper is complete and opt-in. `--netem 1 --netem-delay-ms D --netem-jitter-ms J` applies normal-distribution delay/jitter only to replica-Pod `eth0` egress through a `NET_ADMIN` init container; default `--netem 0` runs have no qdisc. It does not change the processor-generated learning signal, physical/observation jitter, exact solver, placement, utility/SLA inputs, or pair formula. `scripts/network_impairment_summary.py` validates matched traces. Normal-build exploratory 10-flow/3-stage/6-replica trace `runs/ibg-experiment-20260727T122310Z.jsonl` (10-ms delay, 3-ms jitter) converged in 18 slots and increased final-five Good/Excellent selection share to 100%; matched no-netem trace `runs/ibg-experiment-20260727T122446Z.jsonl` converged in 12 slots and also ended at 100%. Both exact-replay with zero drift. Packet loss is deferred because the current complete-route contract fails a slot on a dropped request.
>
> The completed physical/observation separation uses nonnegative physical `half-normal-additive-v1` sigma `[6, 5.25, 4, 3.25]` ms. The active outcome mode is `physical-only-v1`: observed selected processing supplies realized utility and the 110-ms SLA. Keep raw pair cost, raw end-to-end latency, physical utility, and physical-plus-pair utility logged. `physical-plus-pair-v1` is the modular switch that restores the historical pair-deducted outcome. The user took this temporary-or-permanent reporting route because the pair-runtime residual was not solved; it does not change selection, solver, or learning. The selected-only learning signal adds independent nonnegative `half-normal-observation-v1` sigma `[7.2, 6.3, 4.8, 3.9]` ms, and likelihood uses their exact convolution. Never feed observation noise into SLA/utility or change either scale table without explicit evidence and authorization.
>
> Current supported evidence is `runs/ibg-experiment-20260721T145856Z.jsonl`, obtained after a successful normal image build/deploy (then reused with `--skip-build` as permitted). It reached equilibrium in 16 slots, passed the Kernel gate with 86.11% classification and 97.22% overshoot compliance, and exact-replayed with zero drift. The current complete non-Chart suite passes 178 tests. `runs/` and `baselines/` are versionable evidence directories and should be included when the user asks for a commit; `figures/` remains ignored.
>
> The 15-flow/8-replica cache-lifetime regression is repaired. Each exact stage has 490,314 states; the recursive `lru_cache` wrapper retained a completed stage table through a self-cycle. `BREIBGPolicy` now uses an exact-equivalent packed state key and clears its memo table immediately after stage embedding. This is not an approximation or a solver replacement. Exploratory trace `runs/ibg-experiment-20260721T144252Z.jsonl` completed 19 slots without OOM, replayed with zero drift, and has median elapsed/admission/controller-CPU times 10.41/10.06/9.91 s.
>
> Phase 4.1 Kernel-forwarder-concurrency remediation remains in progress. Each public forwarder runs two Uvicorn workers with request/limit 25m/1 CPU and 128/256 MiB; every private processor remains one worker and untouched. Only the downstream public-forwarder HTTPX client and Uvicorn server use 30-second idle keep-alives. A separate local processor HTTPX client retains the processor-compatible default window, preventing stale local socket reuse after the processor's unchanged 5-second server timeout. This runtime-only configuration follows fixed-route, cgroup, and connection-lifetime A/B evidence. Do not retune resources, connection windows/limits, or raw pair semantics without new controlled evidence.
>
> Phase 4.1's diagnostic split is complete. Active `forwarding_path_v3` retains historical v1/v2 aggregates and adds source HTTP Core milestones through `http_client_path_v2`; `scripts/forwarding_path_summary.py` still accepts historical schemas. Pre-change normal-build trace `runs/ibg-experiment-20260721T205120Z.jsonl` had 418 TCP connects across 420 links and 13.23-ms mean source-request-to-target-ingress. Matched-keep-alive trace `runs/ibg-experiment-20260721T210935Z.jsonl` completed 14 slots and 420 links, reduced new TCP connections to 243 (42.14% reuse), and reduced that ingress mean to 11.38 ms. It did not establish stable pair behavior: all-slot pair mean was still 42.19 ms/flow versus 43.22 before, with an unstable upper tail. The original shared 30-second client caused a local stale-connection `ReadError`; normal-build same-shape trace `runs/ibg-experiment-20260721T213938Z.jsonl` completed all 18 slots and reached equilibrium after the local/downstream client split. A 2026-07-22 no-controller fixed-route warm probe (`stage-1-0 -> stage-2-0`) found first 15-wave reconnect tails but smaller all-reused residuals. Its same-/cross-worker placement matrix showed no locality pattern: fully reused second/third 15-wave means were 9.43/8.36 and 7.47/6.15 ms for the two same-worker routes, versus 8.52/11.21 and 7.83/13.05 ms for cross-worker routes; a fully reused cross-worker wave still peaked at 29.07 ms. Keep the downstream setting active. The next authorized work is request-correlated public-forwarder worker-process identity in v3, followed only if inconclusive by read-only host/runtime scheduling, Docker/kind, and relevant network/conntrack observations during the same warmed probes. This is not host preflight and must not change host configuration or runtime behavior. All 15x8 results remain exploratory; supported evidence stays `runs/ibg-experiment-20260721T145856Z.jsonl`. Do not normalize pair cost or change resources, SLA, utility, jitter, pair semantics, or the solver.
>
> Update: the worker-identity, warmed-wave, and bounded host/runtime steps are complete. The new additive `forwarder_runtime_v1` data did not isolate one worker, socket, route, throttle event, or global host-pressure signal; it did show source public-forwarder event-loop maximum lag moving with pair-cost tails, including reused connections. Fresh normal-build exploratory trace `runs/ibg-experiment-20260727T105911Z.jsonl` completed 18 slots and exact-replayed with zero drift. This is a scheduling/descheduling contributor, not a root-cause claim or a mitigation authorization. The next possible diagnostic, only with separate user approval, is read-only per-worker scheduler/context-switch evidence to distinguish event-loop occupancy from OS/runtime descheduling. Keep every metric and configuration unchanged.
>
> `control_plane_v1` records controller-boundary monotonic wall/CPU timing, payload bytes, and messages; selected-route wait is separate. `learning_signal_v1` is a logical selected-only footprint, not full selected telemetry or wire bytes. `scripts/control_plane_summary.py` validates/summarizes traces. Forwarder-to-forwarder RPCs are data-plane traffic and do not affect selection.
>
> `solver_resource_v1` is complete behind opt-in `--memory 1` and is off by default. It records current controller RSS before admission, a 5-ms sampled active-slot peak, post-feedback RSS, peak incremental bytes, and exact-policy peak/residual memo entries with per-stage records. `scripts/solver_resource_summary.py` validates and summarizes bytes/MiB separately from cache entries. The complete 171-test non-Chart suite passes. User-run normal-build trace `runs/ibg-experiment-20260722T112356Z.jsonl` gives exploratory 15x8 evidence: 13 slots, 490,314 cache entries per stage, zero residual cache entries, 255.5 MiB maximum RSS, and 97.44 MiB maximum incremental memory. It is not a formal supported-size gate. Phase 4's next user-directed work is report writing; read/edit only the report file explicitly named by the user and do not implement the future heuristic.
>
> Chart work is user-directed. Inspect/edit only explicitly named scripts; each authorized `Chart/<plot>/` folder is self-contained and uses sibling `*_IBG.csv` inputs. Two authorized, non-finalized control-plane scripts are `Chart/control-plane-runtime/control_plane_runtime.py` and `Chart/control-plane-payload/control_plane_payload.py`. With `--refresh-last-n N`, each captures the latest N completed matching Kernel 15-flow/3-stage/8-replica JSONL traces into its sibling CSV, then plots the mean per-timeslot admission runtime or total controller payload with a ±1-standard-deviation band. Their titles and presentation remain user-adjustable. Preserve original design/text unless explicitly directed otherwise. Preserve unrelated `.gitignore`, `EVIDENCE_SUMMARY.md`, and Chart changes.

## Historical handoff prompt (superseded; do not use)

> Continue in `/home/vhakami/Desktop/projects/vesal/SFC-with-IBG` on branch `IBG`. First read `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`, and `STATUS.md`. Do not read or edit `Tutorial.md`, `Report.md`, `EVIDENCE_SUMMARY.md`, or `ibg backup/` unless explicitly requested. Do not inspect `Chart/` unless explicitly directed; then read only `.py` files, and never stage, commit, or push Chart content without separate approval.
>
> Phases 1--3 are complete. Phase 4 is in progress for reporting curation; its bounded `control_plane_v1` and `learning_signal_v1` measurement branch is complete and validated. Preserve the exact decoupled solver, linear utility `u(q)=99-q`, selected-only learning, retention 0.8, no rejection, 110 ms SLA classification, and strict per-entry equilibrium rule `<0.033`. Do not begin coupled IBG, DPDK/VPP, host preflight, rejection, or another phase without explicit authorization.
>
> The implemented measurement branch records controller-boundary monotonic-wall/controller-CPU timing and application-payload bytes/messages in `control_plane_v1`. It separates discovery, admission/planning through route dispatch, feedback processing, and selected-route data-plane wait, and excludes forwarder-to-forwarder RPCs. Separate `learning_signal_v1` canonically projects only the selected learning record (stage, flow, replica, assigned load, noisy signal, and four likelihoods), requires exactly `flows * stages` records, and reports logical bytes per slot/hop. Physical processing and observation-jitter diagnostics are outside that logical projection. It is not the full `selected_telemetry_rx` response or a wire-byte/raw-telemetry comparison. `scripts/control_plane_summary.py` validates and summarizes both; `--csv 1` exports `logical_learning_footprint.csv` with one column per complete learning-signal run. Measurement-branch trace `runs/ibg-experiment-20260718T123226Z.jsonl` passed its supported Kernel gate and exact 11-slot replay and records nine signals/slot with a median 1,861-byte logical footprint, but it predates the separated-jitter model and is not current-model live evidence.

> The user-authorized separated-jitter side branch is now implemented locally. Actual selected processing uses nonnegative `half-normal-additive-v1` physical scales 6/5.25/4/3.25 ms and alone supplies realized utility and SLA. The selected-only learning signal adds independent nonnegative `half-normal-observation-v1` noise with scales 7.2/6.3/4.8/3.9 ms; belief likelihood is the exact convolution of both half-normal laws. The seed-2050 5,000-sample calibration passes with 81.38% minimum accuracy and 87.74% mean load-1 accuracy under the declared 80% minimum/90% maximum, unchanged 3/5/7/11 crossings, and an unchanged physical SLA gate. The full suite passes with 162 tests. Fresh normal-build supported live validation and exact replay are pending, so `runs/ibg-experiment-20260719T125810Z.jsonl` remains version-bounded to the superseded 8/7/5.5/4.5-ms physical profile. Do not change either scale table or feed observation noise into SLA/utility without explicit authorization and new evidence.

> Priority: diagnose and repair the exploratory 15-flow/8-replica runtime regression before further reporting. The newest runs, `runs/ibg-experiment-20260721T130536Z-run001.jsonl` and `...T130912Z-run002.jsonl`, ended with 10/15 and 13/15 SLA violations. Their final physical means were 67.01/70.74 ms per flow but post-placement pair-cost means were 50.95/60.36 ms, producing 117.96/131.10 ms end-to-end; no final flow exceeded 110 ms before pair cost. Do not change the SLA threshold. The separated observation model is not a proven direct cause: its likelihood adds only about 0.0035 ms/call and a pre-change 15x8 trace already had 14/15 final violations with 74.39 ms pair cost. It may still affect routes indirectly through beliefs, so require a same-environment A/B diagnosis rather than assuming either conclusion.
>
> There are two distinct symptoms. Slot time is 14.79--15.11 s versus 8.09--8.12 s in good same-size runs; `control_plane_v1` attributes this mainly to controller admission/exact-solver CPU (about 14.65 vs 7.89 s), not selected-route wait (about 0.42 vs 0.23 s). Do not approximate or replace the exact solver without explicit authorization. Separately, selected forwarder cgroup snapshots show 39--47 throttle events and 1.54--2.16 s cumulative throttling under their 500m limit, while processors are nearly unthrottled. This is a plausible pair-RPC residual hypothesis, not proof. First collect per-run/per-slot before/after throttling deltas and run the controlled A/B. If it holds, apply only the narrow forwarder resource correction—initially request 100m and limit 1 CPU—then rerun the same 15x8 comparison. Preserve the exact solver, physical/observation scale tables, selected-only boundary, post-placement pair-cost deduction, 110 ms SLA, retention 0.8, no rejection, and strict `<0.033` equilibrium rule.

> Chart compatibility is user-directed. Each explicitly authorized `Chart/<plot>/` folder must be self-contained: its `.py` plot script defaults to its primary and optional baseline CSV inputs from that same folder, never shared `figures/`. Preserve each original script's visual design/theme and embedded text unless the user explicitly requests a change. Once a plot script is authorized, perform iterative visual adjustments (ranges, titles, labels, styling) locally: do not reread or update handoffs unless the user explicitly asks to record the choice as final. Finalized refreshes are `Chart/jain/jain.py`, `Chart/sla-small/2/sla-small.py`, and `Chart/util-small/util-small.py`. The utility-small plot uses local `realized_end_to_end_utility_IBG.csv`, trailing five-timeslot smoothing, integer timeslots, and a 2,500--3,500 y-axis. Do not inspect or edit any other Chart content unless the user explicitly names its `.py` script. Preserve current metric semantics and do not make new datapath claims.
>
> The pairwise route-reporting boundary is hardened: only the `K-1` selected consecutive-pair RPC costs are deducted after placement; ingress is separate telemetry; pair metadata and pair sums are validated; current traces require pair/ingress data; mixed historical/current schemas fail; and historical request-overhead traces retain their original semantics. Every replica Pod has a public forwarder on port 8080 and a private processor on port 8081. The forwarder executes only the controller-selected route and records transport telemetry; the processor alone creates physical processing, observation-only jitter, the selected noisy learning signal, and its likelihood. Readiness primes the deterministic sampling path with a discarded sample, without an observation or seeded-stream drift.
>
> The supported command `./scripts/run_experiment.py --flow 3 --stage 3 --replica 5 --max-iterations 100` produced fresh seed-2050 Kernel trace `runs/ibg-experiment-20260715T182717Z.jsonl` from this uncommitted correction worktree. It reached equilibrium in 10 slots; the Phase 3 validator accepted its 90 selected hops and 60 pair records with 98.89% categorical accuracy, 100% server-overshoot tolerance pass rate, complete pairwise integrity, and zero-drift ten-slot replay. The full test suite passes (120 tests), as do Compose config and the local container smoke test. Earlier current-schema traces `171429`, `173555`, `181957`, and `182457` are version-bounded diagnostics, not accepted baseline replacements.
>
> The first post-correction 12-flow attempt was deliberately interrupted and remains unusable. Its fresh replacement is `runs/ibg-experiment-20260715T183453Z.jsonl`, produced by `./scripts/run_experiment.py --flow 12 --stage 3 --replica 5 --max-iterations 100 --skip-build` in Kernel mode at seed 2050. It equilibrated in eight slots and replays 288 selected hops and 192 pair records with zero mathematical drift. In its final five slots, mean processing was 69.99 ms/flow, pair cost 22.60 ms/flow, SLA violations 0.0/slot, processing overshoot 1.39 ms/hop, and classification 98.89% across 180 hops. Treat it as exploratory evidence only: the general validator's overall false gate is expected because 12 flows is outside the formal configuration and does not fully populate load-one ordering groups; the other integrity, timing, equilibrium, and replay checks pass. The active equilibrium rule is `<0.033`; `--runs N` now launches N independent controller Jobs after one setup, retaining separate trace files and CSV columns while keeping seed/configuration fixed. Do not alter thresholds, likelihoods, measurement boundaries, solver behavior, placement, or historical trace semantics without explicit authorization. Preserve unrelated user changes in `.gitignore`, `EVIDENCE_SUMMARY.md`, and `Chart/`; do not commit or push unless separately asked.

## IBG-Hybrid Phase 1 completion

Phase 1 is implemented as an import-safe Hybrid-only foundation. The old
`IBG_Hybrid/main.py` import-time four-run experiment, CSV/pickle activity, and
verbose output are removed from the import path. The executable module now
only reports that the production policy is deferred.

The new package boundary contains typed two-stage actions, the active
20-flow/3-stage/10-replica configuration, immutable global loads, explicit
feasibility results, and solver results. `HYBRID_STAGE_BUDGET = 2` remains in
`IBG_Hybrid/budgeted.py`; unsupported budgets fail configuration, prototype
planner, and prototype embedding validation. Actions contain two
stage/replica pairs in increasing distinct-stage order. Applying one action
increments exactly those two replicas, so the third stage is fully bypassed.

A tiny exhaustive coupled oracle is available only for deterministic tests.
It accepts injected value/feasibility rules, explores copied global load
states, uses canonical first-action tie behavior, and rejects the production
20x3x10 problem through hard size limits. It does not implement or validate
the future production pruning, limited-lookahead, Monte Carlo, bandit,
utility, link, learning, or Kubernetes behavior.

Local verification on 2026-07-27:

- 10 focused Hybrid Phase 1 tests passed.
- 23 unchanged Exact characterization, latency-model, and runner regression
  tests passed.
- Hybrid modules and the focused test module byte-compiled successfully.

No file under `IBG/` was changed. No Kubernetes, diagnostic, netem, DPDK/VPP,
image, deployment, experiment, result-data, or excluded-document work was
performed.

The next implementation phase is not yet authorized by this result. Before
Phase 2 candidate pruning begins, close the remaining Phase 0 production
definitions for feasibility units, belief/link route scoring, pruning size,
continuation objective, depth, Monte Carlo activation/kernel, deterministic
seed ownership, and trace provenance.

## IBG-Hybrid Phase 0 completion

The remaining Phase 0 contract decisions are complete in
`IBG_Hybrid/phase0_contract.py`; Phase 1 was not repeated or replaced.

The fixed initial policy is `C=5`, `D=2`, `S=50`, and rollout epsilon `0.10`.
`C` means replicas retained per stage, giving at most 75 complete actions for
the active 3-stage, exactly-2-selected-stage model. `D` means future flows
after the focal flow. The focal action is committed once and its own expected
two-stage utility is evaluated once at the loads projected after the greedy
continuation; future-flow utilities are not added.

Feasibility now has explicit units and inputs: selected replicas must be Ready
and remain within a declared assigned-flow-per-slot limit, and their directed
selected pair must have a configured nonnegative planning cost in
milliseconds. The budget is only the exact cardinality `L=2`. Hidden true
state, legacy replica cost, and post-placement measured pair residual are not
planner feasibility or scoring inputs. Existing Kubernetes Pod resource
requests are not multiplied by flow count; any future per-flow node resource
demand requires a separate versioned contract.

All decisions still belong to one Hybrid policy. Maximum normalized belief
entropy `>=0.75` activates MC first. Otherwise contention `>=0.70` or a
high-priority flow activates deterministic lookahead. Remaining decisions use
pruned joint greedy. Contention is maximum Ready-replica assigned load divided
by its declared flow limit; entropy is four-state Shannon entropy normalized
by `log(4)` over the feasible pruned pool.

The core MC continuation is epsilon-greedy over feasible pruned joint
actions, not bandit-based: bandit remains optional Phase 10. Flow ordering and
each candidate/sample rollout receive separate, reproducible BLAKE2b-derived
seeds from the root experiment seed. Future traces must retain contract
version, parameters, activation inputs/path/reason, flow order, seed
provenance, candidate identity, and sample count.

Nine focused Phase 0 tests pass together with the ten Phase 1 tests. No
production pruning, lookahead, Monte Carlo, bandit, runner, Kubernetes,
diagnostic, or netem implementation was added in this phase, and no Exact file
was changed.

The next action is IBG-Hybrid Phase 2: implement coupled feasibility,
belief/load-aware per-stage pruning, and enumeration/scoring of the at-most-75
complete `L=2` actions using this final contract. Phase 3 then adds the
deterministic `D=2` focal-value lookahead.

## IBG-Hybrid Phase 2 completion

Phase 2 is complete as a pure Hybrid-only policy boundary. Phase 0 and Phase 1
were retained; no import-safety, action, budget, seed, or oracle contract was
redone.

`IBG_Hybrid/policy.py` now provides `IBGHybridPolicy.select_greedy`. It
filters configured replicas through the Phase 0 Ready/assigned-flow-capacity
contract, computes belief-driven utility at `current_load + 1`, retains at
most `C=5` replicas per stage, enumerates every canonical complete `L=2`
action over those retained sets, applies required directed pair-link
feasibility, scores all surviving actions, and selects the strict best with
canonical exact-tie behavior.

The policy does not receive a replica true state, legacy replica cost, or a
measured runtime pair residual. Its belief expectation delegates each
state/load utility to the unchanged Exact
`IBG.latency_model.expected_state_utility`. The third stage bypass remains
complete: only the two selected replicas are present in the action and
incremented in the returned global load state.

The returned candidate accounting records available and locally feasible
replica counts per stage, all structural and complete pre-pruning-feasible
actions, retained replica identities, total and feasible pruned actions, and
rejection-reason counts. At the initial 3-stage/10-replica configuration the
fixture records 300 structural actions, 5 retained replicas per stage, and 75
feasible pruned actions. An infeasible pool raises
`NoFeasiblePrunedAction` with its accounting instead of returning a partial
or invalid placement.

Local verification on 2026-07-29:

- 26 combined Hybrid Phase 0/1/2 tests passed.
- 23 unchanged Exact characterization, latency-model, and runner regression
  tests passed in the same command; 49 tests passed overall.
- `IBG_Hybrid/` and the Phase 2 focused test byte-compiled successfully.
- `git diff --check` passed.
- `git diff --name-only -- IBG` remained empty.

No Exact file, runner, Kubernetes/container resource, traffic path, learning,
outcome/SLA behavior, telemetry, evidence, diagnostic, netem, generated data,
or excluded document was changed. No experiment, image build, deployment,
commit, or push was performed.

The next action is IBG-Hybrid Phase 3 only: add deterministic `D=2`
limited-lookahead over the Phase 2 greedy base, commit each focal candidate
once on a copied global state, simulate only the next `min(D, remaining)`
flows, evaluate focal utility once at projected loads, and prove no branch
leakage or immediate-value double counting. Monte Carlo remains Phase 4.

## IBG-Hybrid Phase 3 completion

Phase 3 is complete inside the existing pure `IBGHybridPolicy`. Phase 0,
Phase 1, and Phase 2 contracts and behavior were retained; in particular,
`select_greedy` remains the unchanged continuation policy.

`select_lookahead` enumerates the Phase 2 root-feasible pruned focal actions.
For each focal candidate it starts from the immutable pre-decision state,
commits that focal once, derives the actual remaining flows from the
configured slot and committed `L=2` assignment count, and simulates up to
`D=2` later arrivals. Every continuation calls Phase 2 again at its updated
branch-local loads, so Ready/capacity/link feasibility, pruning, scoring,
canonical ties, and candidate accounting are recomputed rather than reused
from the root.

Each completed branch is valued only by its focal action at the projected
final loads, with one configured planning link deduction. No immediate focal
value or continuation-player welfare is added. The selected solver result
commits only the focal action; projected future states are retained as
immutable inspection detail. Root and per-continuation Phase 2 accounting,
requested/effective depth, ordered future actions, and dead-end branch
accounting are exposed for deterministic validation. Inputs and sibling
branches are unchanged.

Local verification on 2026-07-29:

- 39 combined Hybrid Phase 0/1/2/3 tests passed.
- 23 unchanged Exact characterization, latency-model, and runner regression
  tests passed in the same command; 62 tests passed overall in 6.88 seconds.
- Hybrid modules and the Phase 3 focused test byte-compiled successfully.
- `git diff --check` passed.
- `git diff --name-only -- IBG` remained empty.
- No Markdown file exists under `IBG_Hybrid/`.

The default 20x3x10 pure boundary was measured over five identical local
calls with uniform state-4 beliefs, zero planning-link costs, Ready replicas,
capacity 20, `C=5`, and `D=2`. Calls took 1.462995, 1.356253, 1.557856,
1.377547, and 1.412557 seconds (mean 1.433442 seconds). All returned
`(stage 1, replica 1) -> (stage 2, replica 1)`, objective
172.813750354781, 75 completed focal evaluations, and two continuation steps
per branch. This is local solver evidence, not a latency guarantee.

No Exact file, Monte Carlo, activation path, flow-order randomization, slot
runner, traffic, learning, metrics, replay, Kubernetes/container resource,
diagnostic, netem, bandit, generated-data, or excluded-document change was
made. No experiment, image build, deployment, commit, or push was performed.
The next action is Hybrid Phase 4: seeded Monte Carlo inside the same public
policy, preserving this focal-only objective and Phase 2 greedy continuation.

## IBG-Hybrid Phase 4 completion

Phase 4 is complete inside the existing pure `IBGHybridPolicy`. The Phase 2
greedy and Phase 3 deterministic-lookahead methods remain unchanged.
`select_monte_carlo` evaluates every feasible pruned focal action through
exactly `S=50` candidate-specific samples by default. Each sample owns a
`RolloutSeedKey`, derived BLAKE2b seed, local RNG, focal commit, and immutable
continuation branch.

At every future arrival, the sample recomputes the Phase 2 boundary at its
updated loads. A step is canonical greedy with probability `0.90`, or a
uniform seeded draw from the same feasible-pruned action tuple with
probability `0.10`. Every step records its mode, greedy and selected action,
feasible pool, Phase 2 accounting, pre-state, and post-state. No exploration
action can bypass Phase 2 readiness, assigned-flow capacity, pruning,
canonical action shape, or directed planning-link feasibility.

Samples evaluate only their focal action at the projected final loads and
subtract its configured planning link once. Immediate focal utility and
continuation-player welfare are not added. Candidate values are means of
completed sample focal values only. Failed rollouts and all-failed
candidates retain deterministic seed/state/accounting detail; no partial
placement is fabricated. The returned solver state commits only the selected
focal action.

Local verification on 2026-07-29:

- 57 combined Hybrid Phase 0/1/2/3/4 tests passed.
- 23 unchanged Exact characterization, latency-model, and runner regression
  tests passed in the same command; 80 tests passed overall.
- Hybrid modules and the Phase 4 focused test byte-compiled successfully.
- `git diff --check` passed.
- `git diff --name-only -- IBG` remained empty.
- No Markdown file exists under `IBG_Hybrid/`.

The default 20x3x10 pure Monte Carlo boundary used `C=5`, `D=2`, `S=50`,
epsilon `0.10`, root seed 2050, slot 4, decision position 2, flow 17, uniform
state-4 beliefs, zero configured planning-link costs, Ready replicas, and
capacity 20. The quiet focused test completed in 68.03 seconds. A second
instrumented call took 68.556997 seconds and returned
`(stage 1, replica 1) -> (stage 2, replica 1)`, mean focal objective
172.813750354781, 75 candidate evaluations, 3,750 completed samples, zero
failed samples, and 702 seeded exploration steps among 7,500 continuations.
This is local solver evidence, not a latency guarantee.

No Exact file, automatic activation, flow-order randomization, slot runner,
traffic, learning, metrics, replay, Kubernetes/container resource,
diagnostic, netem, bandit, generated-data, or excluded-document change was
made. No experiment, image build, deployment, commit, or push was performed.
The next action is Hybrid Phase 5: integrate the completed greedy, lookahead,
and Monte Carlo paths into a complete reproducible simulation slot with
selected-only learning, shared metrics, and compact per-slot output.

## IBG-Hybrid Phase 5 completion

Phase 5 is complete as an import-safe pure-Python simulation slot.
`IBG_Hybrid/runner.py` now orchestrates one slot through the unchanged
`IBGHybridPolicy`; it does not embed placement mathematics. One derived local
flow-order stream is used across all coupled decisions. Activation uses the
current feasible pruned pool and preserves Monte Carlo over lookahead over
greedy precedence. Every real state transition is exactly one selected focal
`L=2` action; projected lookahead and rollout continuations remain detail
only.

`IBG_Hybrid/simulation.py` provides the in-process execution adapter. After
all placements, it generates only selected observations at final assigned
loads with independent physical/observation seeds and unchanged Exact
latency, separated-jitter, convolved-likelihood, and state-estimate helpers.
The runner requires two observations and one separately named measured pair
per flow, validates the complete set before learning, and keeps hidden true
state inside the adapter.

The complete observation batch is passed once to unchanged
`IBG.learning.apply_observations` and frozen Exact local
posterior/aggregation methods. Selected-only retention remains `0.8`.
Metrics reuse Exact linear utility, physical-only outcome selection,
`SLA_v`, Jain fairness, and strict `<0.033` equilibrium. Expected planning
link, simulated measured pair, physical latency, observation jitter, noisy
learning signal, raw end-to-end latency, and reference utility are separately
retained. A skipped stage contributes no load, request, observation, utility,
latency, SLA, or learning.

`IBG_Hybrid/slot_contracts.py` retains immutable configuration, flow order and
seed provenance, priorities and activation reasons, actions/skipped stages,
loads before/after, objectives and candidate accounting, full selected policy
detail, final loads, selected observations, beliefs before/after, and all
metrics. `run_hybrid_slot` is silent and in-memory; only the explicit wrapper
prints one compact completed-slot line. Imports and runs create no CSV,
pickle, or result file.

Local verification on 2026-07-29:

- The final combined command passed 116 tests in 78.02 seconds: 79 Phase
  0/1/2/3/4/5 Hybrid tests and 37 relevant unchanged Exact characterization,
  latency-model, runner, adapter/selected-learning, and learning-footprint
  tests.
- Hybrid and Phase 5 test byte-compilation, silent imports,
  `git diff --check`, the empty `IBG/` diff check, and the
  no-Markdown-under-`IBG_Hybrid/` check passed.
- The completed low-entropy 20x3x10 fixture retained `L=2`, `C=5`, `D=2`,
  `S=50`, epsilon `0.10`, root seed 2050, slot 1, Ready capacity 20, and all
  default dimensions. It completed in 0.857269 seconds with 20 greedy
  decisions, 20 actions, 40 observations, 20 measured pairs, and 40 final
  assignments.
- That slot recorded aggregate expected utility 3382.319661, physical-only
  realized utility 2701.635551, total physical/pair/raw latency
  1258.364449/30.8/1289.164449 ms, raw reference utility 2670.835551, zero
  physical-only 110-ms SLA violations, Jain fairness
  0.9999997995824625, maximum belief change 0.198, and no first-slot
  equilibrium.
- A separate uniform-initial-belief default attempt correctly activated full
  `S=50` Monte Carlo but remained non-terminal at the local command session's
  1,000-second lifetime. No completed runtime is claimed for it and no
  accepted policy parameter or detail was reduced.

No file under `IBG/` was changed. No HTTP, container, Kubernetes, replay,
diagnostic, netem, DPDK/VPP, bandit, generated evidence, excluded document,
image build, deployment, experiment, commit, or push work was performed.
Phase 6 is next: reuse the existing Kernel container/Kubernetes architecture
and add the versioned two-selected-stage route execution/replay boundary.

## IBG-Hybrid activation status correction

Paper validation found an activation-policy error in the completed Phase 5
slot runner: it currently treats entropy `>= 0.75` as sufficient for Monte
Carlo. Fresh uniform beliefs therefore route all 20 flows into the expensive
`S=50` method; the manually terminated over-15-minute default attempt exposed
that behavior. It was a real current-policy execution, not test overhead,
but it is not representative of the intended normal Hybrid algorithm.

The next task is a bounded activation correction, before Phase 6. It will add
an explicit slot-level uncertainty-event input, default false, and require
both that event and high entropy for Monte Carlo. Without the event, high
contention/high priority selects lookahead and all other decisions select
greedy. No solver-method, `L=2` action, `C/D/S/epsilon` parameter, Exact
component, or infrastructure change is authorized in that correction.

### Correction to the correction: default Hybrid path

The immediately preceding next-task description was still wrong in one
important respect. After rereading the paper's *A Catalog of Approximation
Heuristics* and *Pruned Lookahead Rollout*, the active Hybrid algorithm is
the pruned lookahead variant: `C=5` pruning followed by `D=2` lookahead for
each normal feasible focal decision. Greedy supplies the simulated future
players' base policy; it is not the normal final decision path. The paper's
low-contention greedy commit is an optional dynamic fast path and is deferred
for this project.

The bounded correction before Phase 6 must therefore do two things: prevent
uniform entropy alone from selecting Monte Carlo, and make pruned `D=2`
lookahead the default decision method. Monte Carlo remains reserved for an
explicit uncertainty/churn event with high entropy. No policy-method
mathematics or Exact/infrastructure behavior is authorized to change.

### Revised next work: core Hybrid before MC

The work is now deliberately split. Immediate work is only the core
IBG-Hybrid Lookahead correction: default `C=5` pruning plus `D=2` lookahead
for every feasible focal flow, with greedy reserved for simulated future
flows. Automatic MC is disabled while this is completed and validated at the
default 20x3x10 configuration.

Monte Carlo is deferred to a separate redesign phase. Its present
implementation can execute up to 75 focal candidates times 50 rollouts per
real decision, measured at roughly 68 seconds for one such decision. It is
not an acceptable production fallback and must not be automatically enabled
until a separately accepted scalable design and runtime evidence are in
place. No implementation work was performed by this documentation update.

### Core Hybrid correction completion

The immediate core-lookahead correction is complete. The active contract is
now `ibg-hybrid-policy-contract-v2`. A slot always uses the existing pruned
`D=2` lookahead decision; greedy is used only by projected continuation
flows, and the explicit MC method is unreachable from automatic
orchestration. Uniform startup entropy no longer changes that path.

Default uniform-belief 20x3x10 evidence at root seed 2050 and slot 1:

- Three deterministic runs took 4.670068, 3.950284, and 4.080329 seconds
  (mean 4.233560 seconds).
- Every run recorded 20 deterministic-lookahead paths with effective depths
  `[2 x 18, 1, 0]`.
- Every run completed 20 focal actions, 40 final replica assignments, and
  exactly 40 selected observations.
- The measured slot retained aggregate expected utility 2687.391,
  physical-only realized utility 2701.636, zero 110-ms SLA violations, Jain
  fairness 0.999994, maximum belief change 0.150, and no first-slot
  equilibrium.

Semantics-preserving structural reuse and belief-value/load utility
memoization reduced this corrected path from the first measured 27.456696
seconds to a 4.233560-second three-run mean. This remains local pure-Python
evidence, not a millisecond or real-time guarantee.

All 80 Hybrid Phase 0--5 tests pass in 18.61 seconds. The 37 relevant frozen
Exact regressions also pass. Monte Carlo redesign is the next separate
algorithm phase; it has not begun and the current explicit Phase 4 method
remains disabled from automatic slots.

For direct local inspection, `scripts/run_hybrid_iterations.py` runs the
default pure-Python 20x3x10 Hybrid simulation across successive slots,
prints one compact line per iteration, carries learned beliefs forward, and
stops at equilibrium or a user-selected slot limit. It is a no-file-side-
effect convenience runner; it does not invoke Kubernetes, containers, or
traffic.

The current user-selected manual check changes the default lookahead depth
from `D=2` to `D=3` under `ibg-hybrid-policy-contract-v3`. The normal runner
now projects three future flows where available; automatic MC remains
disabled. Earlier `D=2` runtime and equilibrium evidence remains historical.

The professor has supplied the authoritative MC scalability direction. The
current exhaustive Phase 4 method is reference/test-only. Production MC will
first select canonical top `Q=10` complete actions from the feasible pruned
set, then run all `S=50` seeded rollouts for each retained candidate. Its
future flows use greedy, never deterministic lookahead or Bandit; current
`D=3` is only the stochastic greedy-continuation horizon. MC remains
unreachable from automatic slots until that redesign is implemented and
measured.

The user has restored the active depth to `D=2` under
`ibg-hybrid-policy-contract-v4`; the preceding `D=3` records are historical
manual-check evidence only. This restoration applies to core lookahead and to
the planned top-`Q` MC continuation horizon.

## Active workstream switch: MILP baseline

Updated: 2026-08-01.

IBG-Hybrid and Monte Carlo work is temporarily paused at the preceding state.
The completed default `C=5`, `D=2` core-lookahead path, its pure simulation
runner, all Hybrid tests/contracts, and the still-unimplemented
professor-directed top-`Q=10`, `S=50` MC redesign are preserved for later
resumption. No `IBG/` or `IBG_Hybrid/` code was changed for this switch.

The active next chapter is the centralized coupled/budgeted MILP baseline.
Flow count, stage count, and replicas per stage will be run-time variables;
the initial default profile is 15 flows, 3 stages, 10 replicas per stage (30 total),
and exactly `L=2` selected distinct stages per flow. The three-stage profile
fully bypasses its third stage; a `K`-stage run bypasses `K-2` stages. The MILP sees perfect true replica state and the complete slot, as
specified by the paper's baseline description, and maximizes aggregate
final-load social welfare. It is not an IBG/SPNE solver and does not use
belief learning, pruning, lookahead, Monte Carlo, bandit logic, or equilibrium
as a stopping rule.

The audit covered `misc/vesal_tex.tex` and every Python file in the newly added
`MILP/` folder. The old revision is not a valid baseline yet:

- `milp_main.py` executes fifty experiments, prints replica state, and writes
  reports from its import path.
- It defaults to the decoupled branch and declares 30 replicas per stage,
  although the paper's stated MILP topology uses 30 replicas total.
- Its `budget` variable never reaches the budgeted solver. That solver
  hard-codes `B=20`, uses random legacy replica costs, permits arbitrary stage
  skipping, and does not enforce exact `L=2` cardinality.
- The formulation has no selected-pair link term, Ready constraint, or
  declared assigned-flow-capacity constraint.
- It uses the obsolete two-state inverse utility, old likelihood/learning,
  retention 0.7, state-ID SLA, and threshold 0.02 instead of the active shared
  physical/metric contracts.
- It shuffles global RNG state, treats a feasible incumbent like an accepted
  solution without bound/gap provenance, and does not distinguish paper
  Gurobi results from local CBC behavior.
- The budgeted caller loops over stages, receives `(assignment, counts)`, and
  passes that tuple to the old per-stage `update` function, so that execution
  path is structurally broken.
- OR-Tools is imported but not declared in `requirements.txt`.

No MILP code was changed during this planning audit. `MILP/` remains untracked
prototype material. Existing user changes in `EVIDENCE_SUMMARY.md` and the
user-controlled untracked `Chart/` directory were not inspected or modified.

The next action is MILP Phase 0 in `ROADMAP.md`: freeze the exact variables,
constraints, final-load social-welfare objective, perfect-state boundary,
`L=2` action, planning-link semantics, capacity units, solver/backend and
optimality-status contract, and deterministic mismatch fixtures before
replacing the prototype solver. Suggested model: GPT-5 Codex. Suggested
reasoning level: xhigh.

The MILP runtime contract now additionally requires a user-controlled
`--cutoff SECONDS` option for every run. It must accept a finite positive
number of seconds, propagate that value to the solver backend, and record the
requested limit, actual solve time, termination, incumbent, best bound, and
gap. A placement returned at the cutoff is feasible evidence only unless
optimality was proven before termination.

## MILP Phase 0 completion

Updated: 2026-08-01.

MILP Phase 0 is complete. `MILP/phase0_contract.py` now provides the pure,
import-safe `milp-coupled-phase0-contract-v1` boundary; the unsafe legacy
`milp_main.py` was characterized but never imported, executed, or repaired.

The frozen contract uses one-based runtime-configurable flow, stage, and
per-stage replica indices; its initial default is 15 flows, three stages, and
ten replicas per stage (30 total). Exact `L=2` remains fixed. Every canonical action selects
one replica from each of two distinct stages and fully bypasses the third.
Complete whole-slot feasibility requires valid IDs, Ready status, declared
assigned-flow-per-slot capacity, and a finite nonnegative configured cost for
every possible lower-stage/higher-stage directed pair. The initial topology
therefore requires 300 planning-link coefficients.

The future formulation uses binary per-flow placement `x`, stage-selection
`y`, final-load indicator `z` including load zero, and linearized directed-
pair `p` variables. Its objective is aggregate final-load physical utility
under perfect true-state knowledge minus exactly one configured planning
link per flow. Beliefs, private signals, learning, equilibrium, flow order,
observation-only jitter, measured pair outcomes, and HTTP/Kubernetes telemetry
are excluded from the planner. The paper states the centralized
perfect-state/Gurobi 10.0 baseline and the `15x3x30-total` envelope but does
not provide this full linearization; the detailed `L=2` model is explicitly
the project contract.

Cutoff and result semantics are also frozen. A run accepts only a finite
strictly positive cutoff in seconds and retains the requested value, build
and solve durations, backend/version, termination reason, incumbent, best
bound, normalized absolute/relative gaps, and supported model counts. Proven
optimal, timed incumbent, timeout without incumbent, infeasible, unbounded,
and solver/configuration error are distinct. A timed incumbent never sets the
optimality-proof flag.

Local backend inspection installed nothing. The project `.venv` contains
SciPy 1.18.0 with `scipy.optimize.milp` backed by HiGHS 1.12.0; a trivial
one-binary-variable smoke solve returned an optimal objective of 1.0. This is
the candidate later development backend, not Gurobi evidence. Gurobi,
OR-Tools/CBC, PuLP, python-mip, highspy, Pyomo, GLPK, and standalone HiGHS are
not locally available. OR-Tools also remains absent from `requirements.txt`
despite the legacy import.

Local Phase 0 verification:

- 27 focused positive and prototype-characterization tests pass.
- Silent import and no-result-file-side-effect checks pass for the new module.
- The local SciPy/HiGHS development-backend smoke solve passes.

No Exact or Hybrid file, test, behavior, runtime, evidence, generated data,
excluded document, image, cluster, or host configuration was changed. No
dependency was installed, and no commit or push was performed.

The next action is MILP Phase 1 only: establish the replacement import-safe
package and immutable input/result contracts, add a tiny exhaustive
centralized oracle, gate the declared development backend, and expose the
validated per-run `--flow`, `--stage`, `--replica`, and `--cutoff SECONDS`
options. Production MILP construction and solving remain Phase 2; simulation,
scale validation, Kernel Kubernetes reuse, and replay/diagnostics remain
Phases 3--6.

## MILP Phase 1 completion

Updated: 2026-08-01.

MILP Phase 1 is complete under `milp-coupled-phase1-boundary-v1`. `MILP/` is
now an import-safe package. Immutable contracts retain runtime dimensions,
the exact requested cutoff, complete clairvoyant true-state/admission/link
inputs, canonical whole-slot placements and final loads, the Phase 0 welfare
breakdown, and the unchanged Phase 0 status/gap provenance.

The guarded command accepts `--flow`, `--stage`, `--replica`, and required
`--cutoff SECONDS`. Flow/stage/replica values must be positive integers,
stage count must be at least two, and cutoff must be finite and strictly
positive. Defaults are 15 flows, 3 stages, and 10 replicas per stage; they
are not limits. The uniform replica option constructs one count per supplied
stage. Exact `L=2` is not configurable, so a `K`-stage run bypasses `K-2`
stages.

The free-backend gate reports the already installed SciPy 1.18.0
`scipy.optimize.milp` capability and embedded HiGHS 1.12.0. Detection does
not build or solve a model. Its missing-backend path is an explicit helpful
configuration error. No package was installed, and this local backend fact
is not Gurobi 10.0 or paper-runtime evidence.

The new exhaustive oracle is test-only. It enumerates canonical actions,
applies Phase 0 Ready/capacity/link feasibility, and evaluates centralized
final-load social welfare with canonical exact ties. It refuses fixtures
above four flows or 100,000 complete placements and explicitly rejects the
default 15x3x10 target. Production solving is still absent.

The old `milp_main.py` fifty-experiment import behavior is gone; it is now a
guarded compatibility entry point. The invalid legacy budgeted solver is a
retired explicit failure rather than an OR-Tools/CBC path. The remaining
legacy header imports without OR-Tools, and all supported MILP imports are
silent, do not consume global RNG state, and create no files. Phase 0's
twelve mismatch records remain preserved as historical characterization.

Local verification:

- 55 combined MILP Phase 0 and Phase 1 tests pass in 2.54 seconds.
- Every supported MILP module and both focused test modules compile.
- A separate supported-module import check is silent and file-safe.
- `python -m MILP --cutoff 2.5` accepts the 15x3x10/L=2 configuration,
  reports SciPy 1.18.0/HiGHS 1.12.0, and explicitly says the production solve
  is deferred.
- No solver model was built or solved, and no package, output report, image,
  cluster resource, real traffic, commit, or push was created.

The next action is MILP Phase 2: implement the pure coupled `x/y/z/p` model
and SciPy/HiGHS adapter, apply the exact requested cutoff, normalize every
termination status and bound/gap, and compare controlled tractable optima to
the tiny oracle. Simulation, 15x3x10 scale validation, Kernel/Kubernetes
reuse, and replay/diagnostic work remain MILP Phases 3--6.

## MILP Phase 2 completion

Updated: 2026-08-01.

MILP Phase 2 is complete. `MILP/model.py` now constructs the pure immutable
`milp-coupled-phase2-model-v1` `x/y/z/p` formulation, and `MILP/solver.py`
adapts it to the already installed SciPy/HiGHS family under
`milp-coupled-phase2-solver-v1`. The public entry point is
`MILP.solve_coupled_milp`.

The model enforces exact `L=2`, one replica in each selected stage, Ready
availability, assigned-flow capacity, a zero-inclusive final-load indicator,
exact load reconstruction, all directed-pair AND inequalities, and exactly
one selected configured pair per flow. It calls the frozen Exact
`expected_state_utility` for perfect-state/final-load coefficients. Beliefs,
learning, observation jitter, measured pairs, Hybrid policy, and runtime
telemetry are absent.

The solver sends the exact user cutoff to the primary SciPy native time-limit
option, requests zero relative MIP gap, reconstructs maximization bounds from
SciPy's minimization convention, and retains Phase 0 status/gap provenance.
Proven optima receive objective-preserving lexicographic secondary solves
within the remaining cutoff. Every returned vector is independently checked
for binary bounds, integrality, all model rows, exact action shape, Phase 0
feasibility, final loads, and objective agreement before it becomes an
incumbent.

The constructed default 15x3x10 boundary contains 5,475 binary variables and
14,115 constraints, including 4,500 directed-pair variables. It was not
solved or timed in Phase 2. That evidence belongs to the Phase 4 scale gate.
The CLI now reports that the solver API is ready while complete CLI problem
input and slot execution remain deferred to Phase 3; it does not invent a
true-state/admission/link profile.

Local verification:

- 73 combined MILP Phase 0/1/2 tests pass in 3.36 seconds.
- A controlled two-flow/three-stage SciPy/HiGHS solve agrees with the tiny
  exhaustive oracle on centralized final-load welfare and canonical action.
- Native `time_limit` receives the requested cutoff unchanged and
  `mip_rel_gap` is zero.
- Proven optimal, timed incumbent, timeout without incumbent, infeasible,
  unbounded, backend error, and invalid-solution behavior are covered.
- Exact utility reuse, joint planning-link choice, Ready/capacity rejection,
  `K-2` bypass, model counts, deterministic repeated ties, and import safety
  are covered.
- No package was installed; no CSV/pickle/output data, image, deployment,
  real traffic, commit, or push was produced.

The next action is MILP Phase 3: build a pure simulation-slot runner around
the solver, run only the selected two-stage routes with final-load
conditioning, retain observations as telemetry without learning, and reuse
the common Exact physical-only utility/SLA/fairness contracts. Phase 4 will
then establish explicit cutoff/optimality evidence at increasing sizes and
the 15x3x10 boundary. Kernel/Kubernetes and replay/diagnostics remain Phases
5--6.

## MILP Phase 3 completion

Updated: 2026-08-01.

MILP Phase 3 is complete under `milp-coupled-phase3-slot-v1`. The new pure
runner invokes the public Phase 2 solver and executes only a proven optimum or
a validated timed feasible incumbent. A timed incumbent stays unproven; a
timeout without an incumbent, infeasibility, unbounded result, solver error,
or invalid placement fails before simulation with no fabricated route.

The in-process adapter runs only the selected exact-`L=2` routes after the
whole-slot placement is complete. Physical processing and exact convolved
likelihoods use final assigned loads. Every flow returns exactly two selected
observations and one selected-pair outcome, while `K-2` bypassed stages and
all unselected replicas contribute nothing. Independent BLAKE2b-derived local
streams own physical jitter, observation-only jitter, and measured-pair
sampling; Python and NumPy global RNG state is unchanged.

The slot result retains all contract versions, configuration/cutoff and
solver provenance, root seed/slot ID, placement/bypasses/final loads,
observations, pair outcomes, expected planner objective components, physical
realized and raw pair-reference metrics, per-flow latency/utility, physical-
only 110-ms SLA, Jain fairness, and build/solve/simulation/total timing.
There is no belief update, equilibrium calculation, flow order, Hybrid
policy, HTTP, Kubernetes, or file output. The pure runner is silent and the
explicit wrapper prints exactly one compact line.

Local verification:

- 89 combined MILP Phase 0/1/2/3 tests pass.
- A real controlled tiny SciPy/HiGHS slot solve executes end to end.
- The default 15x3x10 runner shape passes with a supplied validated incumbent:
  15 actions, 30 selected assignments/observations, and 15 measured pairs.
- 27 unchanged Exact characterization, latency-model, learning-signal, and
  runner regression tests pass.
- Imports are silent, file-safe, and global-RNG neutral. No report, package,
  image, deployment, real traffic, commit, or push was produced.

The next action is MILP Phase 4: measure controlled solve behavior across
increasing dimensions up to the default 15x3x10 boundary using explicit
cutoffs, and retain honest status/incumbent/bound/gap/runtime evidence. This
Phase 3 default-shape test is not scale evidence. Kernel/Kubernetes reuse and
replay/diagnostics remain Phases 5--6.

## MILP Phase 4 completion

Updated: 2026-08-01.

MILP Phase 4 is complete under `milp-coupled-phase4-scale-v1`. A separate
guarded benchmark now constructs the declared deterministic
`milp-scale-synthetic-profile-v1`, calls the unchanged Phase 2 solver once,
and uses the Phase 3 simulation slot only when the solver returns a validated
incumbent. It records cutoff, backend/version, status/proof, incumbent, bound,
gap, model counts, build/solve/simulation/total timing, and process-lifetime
peak RSS without writing a report.

The free local backend is SciPy 1.18.0 with embedded HiGHS 1.12.0. No second
backend is installed, so backend parity is unavailable and no Gurobi/paper
runtime claim is made. With a one-second native cutoff in isolated processes:

- 1x2x1, 2x3x2, and 5x3x4 proved optimal.
- 10x3x6 timed out with feasible incumbent 1421.08, bound 1448.69, and
  relative gap 0.0194227.
- 15x3x10 timed out with feasible incumbent 1628.29, bound 2281.98, and
  relative gap 0.401463. It used 5,475 variables and 14,115 constraints,
  reported 0.140502 seconds model build, 1.210599 seconds solve-call duration,
  2.458909 seconds total wall time, and 182.141 MiB process peak RSS.

The default case is executable but unproven and is not labelled optimal. A
second isolated run reproduced its status, incumbent, bound, and gap while
timing and peak memory varied slightly. The native cutoff is a backend limit,
not a hard process kill, so total wall time includes build, imports, result
normalization, and simulation and can exceed one second.

Local verification includes 12 focused Phase 4 tests, including an actual
cutoff-bound 15x3x10 solve, tiny-oracle parity, deterministic profile/RNG
safety, no-incumbent behavior, memory/provenance validation, import safety,
and compact output. No dependency, report file, image, deployment, real
traffic, commit, or push was produced; `IBG/` and `IBG_Hybrid/` remain frozen.

The next action is MILP Phase 5: reuse the frozen Kernel container/Kubernetes
architecture through a MILP-specific controller and versioned two-selected-
stage route contract. Do not alter the MILP formulation, measured scale
evidence, Exact/Hybrid behavior, or current runtime resource/keep-alive
settings. Replay and diagnostic compatibility remain Phase 6.

### MILP Phase 4 verbose-output update

Updated: 2026-08-01.

`python -m MILP.benchmark` now accepts `--verbose`. The flag prints an
immediate start banner and enables native HiGHS progress; without it, the
benchmark retains the single compact completion line. A controlled 2x3x2 run
showed presolve, branch-and-bound incumbent/bound/gap, node/LP-iteration, and
timing output followed by the unchanged summary. Additional verbose blocks
after a proven primary optimum are the existing deterministic
objective-preserving canonicalization solves. This display-only option does
not change the model, cutoff, placement, status, metrics, or stored evidence.

## MILP Phase 5 completion

Updated: 2026-08-01.

MILP Phase 5 is complete under `milp-coupled-phase5-kernel-v1`. The new path
is isolated under `MILP/`, `deploy/milp-kubernetes/`, and
`scripts/run_milp_kernel.py`; no file under `IBG/` or `IBG_Hybrid/` changed.

The versioned `milp-two-selected-stage-route-v1` contract executes exactly
two increasing selected stages per flow while accepting noncontiguous routes
and routes that begin after stage 1. All other `K-2` stages are absent. The
controller requires a complete Running/Ready ordinal snapshot, deterministic
true-state/capacity profiles, and complete configured directed planning links
before it builds the model. It calls the completed solver once, preserves the
cutoff/status/incumbent/bound/gap contract, and sends traffic only for a
validated optimum or timed incumbent. All non-incumbent statuses fail before
traffic with no fallback.

The unchanged Exact private processor/public forwarder split supplies Kernel
execution. The processor remains one worker on 8081. The forwarder remains
two workers on 8080 with its current resources, separate local/downstream
clients, and 30-second downstream keep-alive. The MILP-specific flow generator
runs complete selected routes concurrently and validates exactly two selected
observations and one measured pair per flow. True state remains private;
there is no learning or equilibrium loop.

The outcome-policy audit against Hybrid Phase 5 found parity for final-load
physical latency, separate physical/observation half-normal jitter, exact
convolved likelihood, physical-only realized utility and 110-ms SLA,
configured planning versus measured pair separation, raw physical-plus-pair
reference utility, and expected-per-flow Jain fairness. Kernel results use
those unchanged definitions and retain build, solve, traffic, and total time
separately. No Hybrid algorithm code is imported.

Local verification:

- 129 combined MILP Phase 0--5 tests pass in 11.96 seconds.
- 109 relevant unchanged Exact latency, learning-signal, runner, processor,
  forwarder, flow-generator, Kubernetes-adapter, and dynamic-resource tests
  pass in 6.10 seconds.
- MILP Phase 5 modules, all MILP focused tests, and the launcher compile.
- Silent import, global-RNG neutrality, no-file-side-effect, Kustomize render,
  no-Hybrid-import, no-Markdown-under-MILP, and frozen Exact/Hybrid tree checks
  pass.
- The default 15x3x10 Kernel boundary passes with a supplied validated
  incumbent: 15 routes, 30 selected assignments/observations, and 15 measured
  pairs. This is contract evidence, not a live deployment result.

The existing `kind-ibg` cluster has three Ready nodes, but the isolated
`milp-testbed` namespace and `milp-testbed:kernel-phase5` image are not
present. No image was built and no Kubernetes resource was changed during
validation. Therefore no live Kernel solver/traffic result or 15x3x10 live
runtime is claimed. A live run requires explicit execution of the launcher
with a user cutoff and planning-link value after reviewing whether 30
two-container replica Pods fit the local cluster.

The next planned phase is MILP Phase 6 replay and diagnostic compatibility,
only when explicitly authorized. Netem, forwarding-path/cgroup evidence,
DPDK/VPP, bandits, Hybrid policy, belief learning, Gurobi claims, CSV/pickle,
and new calibration remain deferred.

## MILP Phase 6 completion

Updated: 2026-08-01.

MILP Phase 6 is complete under `milp-coupled-phase6-trace-v1`,
`milp-coupled-phase6-replay-v1`, and
`milp-coupled-phase6-diagnostics-v1`. The trace is immutable and JSON-safe,
retains complete pure or Kernel solver/placement/outcome provenance, and keeps
clairvoyant true state only inside an explicitly private planner-input/replay
section. No true state is added to observations.

Ordinary replay calls no solver. It validates exact-`L=2` placement,
readiness, capacity, planning links, bypasses, and final loads; reconstructs
the final-load known-state social-welfare objective; checks status/cutoff/
bound/gap provenance; validates exactly two observations and one measured
pair per flow; and reconstructs physical-only utility, the 110-ms SLA, raw
physical-plus-pair latency/reference utility, and Jain fairness. Corruption
fixtures detect action, load, coefficient, objective, status, observation,
pair, utility, SLA, and fairness drift. Optional solver replay requires
canonical equality only for proven optima; timed incumbents remain unproven.

The diagnostic audit classifies Kernel HTTP, forwarding-path, and cgroup
concepts as algorithm-neutral compatible; adapts controller timing, logical
payload counts, and MILP model/process resources; and rejects Exact memo
cache, learning footprint, beliefs/equilibrium, and Hybrid candidate/rollout/
sample diagnostics as inapplicable. Collection is opt-in and cannot change
placement, traffic, metrics, or RNG state.

Local verification:

- 144 combined MILP Phase 0--6 tests pass in 13.69 seconds.
- 108 relevant unchanged Exact/runtime regressions pass in 4.95 seconds.
- The 15 focused Phase 6 tests include controlled in-process pure/Kernel
  parity, JSON safety, true-state privacy, corruption rejection, optional
  solver replay, diagnostic opt-in behavior, silent imports, no file side
  effects, and global-RNG neutrality.
- The live `kind-ibg` cluster remains Ready but has no `milp-testbed`
  namespace. No image was built and no Kubernetes resource was deployed.

There is no live Phase 6 Kernel result. The default 15x3x10 topology would
require 30 two-container replica Pods and was not assumed safe without a
separate capacity review, so it remains contract-tested rather than live-
executed. The bounded MILP Phase 0--6 roadmap is now complete; there is no
automatic Phase 7. Netem, new forwarding/cgroup instrumentation, DPDK/VPP,
bandits, resumed Hybrid work, Gurobi, new calibration, and file reporting
remain deferred until explicitly authorized.

### MILP Kernel live-attempt addendum

Updated: 2026-08-01.

The user authorized one small live verbose Kernel attempt at 2 flows, 3
stages, 2 replicas per stage, `L=2`, a 10-second solver cutoff, and a uniform
2-ms configured planning-link coefficient. The isolated
`milp-testbed:kernel-phase5` image was built (639 MiB) and loaded into the
existing `kind-ibg` cluster. The `milp-testbed` namespace now has six running
two-container replica Pods and one running MILP flow-generator Pod.

No live MILP result exists. Two controller Jobs from the initial attempt and
one retry failed before model construction, solver invocation, or traffic.
Their common terminal error is
`MILPKernelAdapterError: MILP flow generator did not become Ready: [Errno -3]
Temporary failure in name resolution` while the controller waits on its
configured flow-generator service URL. The flow-generator Pod itself reports
healthy on localhost and the ClusterIP Service exists. Thus the current
blocker is controller-Pod DNS/service reachability, not a 10-second MILP
cutoff, solver scalability, placement, utility, SLA, or telemetry failure.

The small running testbed and failed controller Job logs are retained for the
authorized narrow live-Kernel DNS/runtime repair. Do not claim any live
utility, SLA, fairness, bound, gap, or replay result until that repair has a
successful controller slot. The 15x3x10 live topology remains unreviewed and
must not be deployed as part of this repair.

### MILP Kernel live-repair continuation

Updated: 2026-08-01.

Focused in-Pod checks proved the initial error was broader than the URL:
trailing and non-trailing flow-generator names, `kubernetes.default`, the
kube-dns Service, and cross-node replica traffic all failed. The kind nodes'
current internal IPs no longer matched the old host-network `kindnet` and
`kube-proxy` Pods, and new MILP Pods received addresses from the wrong node
PodCIDRs. The two failed controller Job logs were captured and those two Jobs
were then deleted.

With explicit user authorization, only the `kindnet` and `kube-proxy`
DaemonSets were restarted. Only the isolated MILP StatefulSets and flow-
generator Deployment were recycled. Their addresses now match the worker
PodCIDRs; the original absolute trailing-root-label Service URL resolves to
the flow-generator ClusterIP, `kubernetes.default` resolves, and an in-Pod
connection to a replica on the other worker succeeds. No Exact workload was
deleted or changed.

The exact requested verbose command was retried at 2 flows, 3 stages, 2
replicas, cutoff 10 seconds, and planning-link cost 2 ms. Readiness succeeded.
The primary 60-variable/112-constraint SciPy 1.18.0/HiGHS 1.12.0 solve proved
the maximization incumbent 333.62750071 optimal in approximately 0.02 seconds;
the additional verbose HiGHS blocks were deterministic canonicalization
passes inside the one public solver invocation.

Traffic did not complete. The selected placement included the valid MILP
two-stage route stage 1 to stage 3. The MILP flow generator accepted it, but
the reused Exact public forwarder returned HTTP 502 with `next forwarded stage
must be 2, got 3`. Therefore the live result has no complete observations,
measured pairs, utility, SLA, fairness, traffic time, total time, trace, or
replay and must not be reported as a completed slot.

The required fix is a separate MILP forwarder in the isolated MILP image/path
that accepts exactly one strictly later selected hop while reusing the same
private processor and preserving ports, workers, clients, keep-alive,
resources, latency/jitter, telemetry, utility, and SLA policies. Exact and
Hybrid remain frozen. This fix is documented but not yet implemented; the
current failed retry Job is retained for its controller transcript. The next
action is focused implementation/tests followed by the same small live retry,
not a 15x3x10 deployment.

### MILP Kernel live repair completed

Updated: 2026-08-01.

The isolated MILP route-forwarder fix is implemented. The shared Exact
forwarder now exposes only a behavior-preserving next-hop validation hook and
runtime-injection seam; its default still rejects noncontiguous routes. The
new `MILP.kernel_route_forwarder:app` overrides only that validation to accept
one strictly later selected stage. `MILP/kernel_resources.py` changes only the
MILP StatefulSet forwarder command. The live command confirms the forwarder
container uses two workers on port 8080 with the existing 30-second keep-alive;
the private processor, resources, clients, telemetry, and latency/utility/SLA
policies are unchanged.

The controller also runs the completed Phase 6 trace/replay boundary against
its live in-memory result before reporting success. A focused correction
canonicalizes only the optional trailing HTTP root slash introduced by
Pydantic while retaining all substantive endpoint and identity validation.
The final replay returned `replay=ok`.

Final live command:

```text
./.venv/bin/python scripts/run_milp_kernel.py --flow 2 --stage 3 --replica 2 --cutoff 10 --planning-link-ms 2 --timeout 300 --verbose
```

The final controller Job completed. Its primary model had 112 rows, 60 binary
variables, and 282 nonzeros. One public solver invocation performed the
primary optimization plus deterministic objective-preserving canonicalization
passes. SciPy 1.18.0/HiGHS 1.12.0 proved incumbent 333.62750071 optimal with
the same bound and zero gap under the requested 10-second cutoff.

Final compact result:

```text
MILP-Kernel scale=2x3x2 slot=1 cutoff=10s status=proven-optimal optimal=1 incumbent=333.628 bound=333.628 gap=0 routes=2 observations=4 pairs=2 expected-stage=337.628 planning=4.000 social=333.628 realized=338.040 physical-ms=57.960 measured-pair-ms=14.045 raw-ms=72.005 reference=323.995 sla=0 jain=0.999997 solve=0.033037s traffic=0.074069s total=0.111500s replay=ok
```

This proves two complete selected routes, four selected processor observations,
two measured pairs, physical-only utility/SLA, and configured-planning versus
measured-pair separation at the small live boundary. It is not 15x3x10 scale
evidence or a Gurobi/paper-runtime claim.

Final local verification has 150 MILP Phase 0--6 tests and 95 relevant
unchanged Exact/runtime tests passing. Compilation, import safety, global-RNG
neutrality, no-file-side-effect tests, `git diff --check`, frozen `IBG/` and
`IBG_Hybrid/`, no Markdown under `MILP/`, and no Hybrid algorithm import under
`MILP/` pass. The small namespace remains deployed with six Ready two-
container replica Pods, one Ready flow generator, and successful controller
Jobs. No larger topology or deferred feature was run.

### MILP Kernel launcher progress and current oversized rollout

Updated: 2026-08-01.

The MILP launcher now prints automatic pre-solver progress: requested scale,
Pod/container/worker footprint, cutoff and planning coefficient, capacity
notice, nodes, image mode, per-stage rollout waits, Ready snapshot, and
controller Job wait. `--verbose` remains the switch for native HiGHS output.
Focused launcher coverage passes, along with Python compilation and
`git diff --check`.

The user then requested 15 replicas per stage on the small live cluster.
That means 45 replica Pods / 90 containers / roughly 135 serving workers, not
15 flows. The three StatefulSets are currently only 2/15 Ready; many added
Pods are restart-looping after failed health checks, so no new controller Job
or MILP solve has started. This is a capacity/rollout condition, not a solver
stall. Stop that launcher invocation and rerun a smaller topology, for
example 2 flows x 3 stages x 2 replicas, or use 15 flows with only 2 replicas
per stage. No automatic scale-down was performed during diagnosis.

### MILP same-input parity repair completed

Updated: 2026-08-01.

The 14x3x7 pure/Kernel runtime discrepancy was an input mismatch, not a
Kubernetes speedup. Phase 4 used its documented heterogeneous synthetic
state/link profile with flow-count capacities. The earlier Kernel command used
different runtime-profile states, legacy capacity values 2000--5000 as
assigned-flow limits, and a uniform 2-ms link. Equal dimensions produced equal
model counts but different objectives and branch-and-bound work.

`milp-experiment-profile-v1` now lets pure and Kernel share and fingerprint
dimensions, cutoff, exact `L=2`, true states, Ready flags, assigned-flow
capacities, all directed planning links, separate pure measured-pair profiles,
and source/mode provenance. Capacity is explicitly
`assigned-flows-per-slot`; default is flow count per replica and
`--assigned-flow-capacity FLOWS` overrides it. Legacy Exact capacity is
ignored. The default is not calibrated paper or cluster evidence.

Same-input commands are:

```text
PYTHONPATH=. ./.venv/bin/python -m MILP.experiment --flow 2 --stage 3 --replica 2 --cutoff 10 --planning-link-ms 2
./.venv/bin/python scripts/run_milp_kernel.py --flow 2 --stage 3 --replica 2 --cutoff 10 --planning-link-ms 2 --timeout 300 --verbose
```

Both produced fingerprint `011001de78293ceefae74d4c52a330a5`, proven-optimal
incumbent/bound `333.62750071`, and zero gap. Kernel retained two routes, four
observations, two pairs, expected-stage welfare 337.628, planning deduction
4.000, social welfare 333.628, physical realized utility 336.274, physical
latency 59.726 ms, measured-pair latency 24.605 ms, raw latency 84.331 ms,
reference utility 311.669, zero physical-only SLA violations, Jain fairness
0.999997, solve 0.055337 seconds, traffic 0.107148 seconds, total 0.169889
seconds, and `replay=ok`.

Verification: 158 MILP Phase 0--6/parity tests and 127 relevant unchanged
Exact/runtime tests pass. The isolated namespace is scaled back to 2x3x2.
Phase 4 remains unchanged synthetic scale evidence. No 15x3x10 capacity,
Gurobi/paper-runtime, calibration, Hybrid, learning, report-file, commit, or
push claim was added.

### MILP planning-latency follow-up

Updated: 2026-08-01.

The same-input pure/Kernel parity repair is complete, but the default uniform
`--planning-link-ms 2` control is not an adequate latency-aware experiment:
with exact `L=2`, it is the same one-time deduction for every flow regardless
of the selected pair. Actual live pair latency is measured after placement and
does not currently steer the MILP solve.

The next requested priority is a complete deterministic heterogeneous directed
planning-latency profile shared by pure and Kernel inputs. It must affect
pair choice before placement, retain profile/fingerprint provenance, and stay
strictly separate from the actual post-placement measured-pair outcome. No
such profile has been implemented yet, and no claim of latency-aware route
selection should be made for uniform-link runs.

### MILP Kernel rollout-scalability work opened

Updated: 2026-08-03.

The user has paused the planning-latency-profile follow-up and wants to work
on safely supporting more MILP replicas. No resource or algorithm change is
authorized yet.

The current replica Pod has two containers: private processor request 50m CPU
and 128Mi memory (limits 1 CPU and 768Mi); public forwarder request 25m CPU
and 128Mi memory (limits 1 CPU and 256Mi). A replica Pod therefore requests
75m CPU/256Mi and can use up to 2 CPUs/1Gi. The next action is to measure node
and Pod scheduling/resource behavior during controlled rollouts before deciding
whether resource specifications, topology, or cluster capacity should change.

The persistent kind node containers were configured with Docker restart policy
`no` and then stopped at the user's request. No Kubernetes resource was
deleted. A future live investigation must explicitly start `ibg-control-plane`,
`ibg-worker`, and `ibg-worker2` first.

### MILP deployment ownership separation complete

Updated: 2026-08-03.

MILP now owns its resource manifest, runtime profile file, labels,
ConfigMap/mount path, and Kubernetes Ready discovery. The baseline resource
shape and worker counts are unchanged: this prevents future MILP rollout
changes from modifying IBG, rather than attempting a tuning change now. The
focused MILP Phase 0--6 and input-parity suite passes (159 tests), compilation
and `git diff --check` pass, and no IBG/IBG_Hybrid file changed.

An already-running MILP deployment created before this separation uses the old
IBG-labelled immutable StatefulSet selector. Remove `milp-testbed` before the
first post-separation MILP deployment, then run once without `--skip-build` to
build/load the updated isolated MILP image. Later unchanged-image runs may use
`--skip-build`.

### MILP lean service image built locally

Updated: 2026-08-03.

The new service image built and imported `MILP.kernel_flow_generator` without
loading SciPy or pandas. Its local Docker image size is 79,393,189 bytes,
versus 150,312,729 bytes for the former single MILP image; the new controller
image is 146,283,157 bytes and retains the solver dependencies. These image
sizes are local build evidence only, not Pod-RSS evidence. No image was loaded
into kind and no Pod was deployed during this validation. The next safe test
is one fresh MILP-only rollout without `--skip-build`, followed by measured
resource comparison at the same dimensions.

The fresh MILP-only 12x3x6 rollout completed after the image split: all 18
replica Pods were Ready with zero restarts and used
`milp-testbed:kernel-service-phase5`. The sampled private processors used
40.6MiB on average, unchanged from the prior broad image; sampled two-worker
forwarders used 119.7MiB on average, down from 175.5MiB (55.8MiB or 31.8% per
forwarder). Worker-node Docker snapshots were 1.784GiB and 1.720GiB, but they
are not a direct before/after lean-image comparison because the unrelated IBG
deployment was also removed. The forwarder still recorded startup/traffic CPU
throttling under its unchanged one-CPU limit; no resource adjustment is
authorized by this measurement alone.

### MILP processor right-sizing and batched rollout completed

Updated: 2026-08-03.

MILP-only resource declarations now set the private processor to 50m CPU/64Mi
request and 1 CPU/256Mi limit. The public forwarder remains exactly 25m
CPU/128Mi request and 1 CPU/256Mi limit with two workers; the processor remains
one worker. `--rollout-batch-size` is positive, defaults to two replicas per
stage, and implements bounded all-stage rollout targets before the controller
is created.

Fresh validation removed and recreated only `milp-testbed`, rebuilt/loaded the
two MILP images, and ran:

```text
./.venv/bin/python scripts/run_milp_kernel.py --flow 6 --stage 3 --replica 3 --cutoff 60 --planning-link-ms 2 --rollout-batch-size 2 --timeout 300 --verbose
```

It applied/waited the `2 -> 3` per-stage rollout. All nine replica Pods reached
2/2 Ready with zero container restarts, used
`milp-testbed:kernel-service-phase5`, and each StatefulSet ended desired=3,
ready=3. The controller made one completed slot and reported:

```text
MILP-Kernel scale=6x3x3 slot=1 cutoff=60s status=proven-optimal optimal=1 incumbent=963.087 bound=963.087 gap=0 routes=6 observations=12 pairs=6 expected-stage=975.087 planning=12.000 social=963.087 realized=965.573 physical-ms=222.427 measured-pair-ms=99.771 raw-ms=322.198 reference=865.802 sla=0 jain=0.999795 solve=0.288494s traffic=0.127412s total=1.401264s profile=milp-experiment fingerprint=ab24dfb2bcb099ae8e9142aed8b2fb11 link-mode=uniform-objective-constant replay=ok
```

Post-run cgroup samples were processor 40.61/40.45MiB with a 256MiB cgroup
maximum, and forwarder 120.26/119.15MiB with its unchanged 256MiB maximum.
The two sampled forwarders had zero throttling counters in this short run; this
does not invalidate the earlier longer/larger forwarder-throttling evidence.
The current MILP-only worker-node Docker snapshots were 999.2MiB and 1.077GiB
(control plane 769.1MiB). These are current small-topology snapshots, not a
same-scale RSS comparison with the 12x3x6 result.

Focused rollout/resource tests plus all MILP Phase 0--6/parity tests passed
(170), and 32 unchanged Exact runtime/latency/forwarder tests passed. Python
compilation, import-safety/no-global-RNG/no-file-side-effect coverage,
`git diff --check`, frozen IBG/IBG_Hybrid, no MILP Markdown, and no Hybrid
algorithm import checks pass. No MILP planning-latency, solver, route,
utility/SLA, jitter, replay, diagnostic, Exact, or Hybrid behavior changed.

### MILP existing-replica batching bug corrected

Updated: 2026-08-03.

Code review found that the initial batching implementation applied the first
batch target even when MILP StatefulSets already existed. Thus an existing
three-replica deployment would have become two before growing to a requested
six. This was corrected without changing resources or solver/runtime policy:
the launcher now reads all existing per-stage desired counts, requires them to
be complete and consistent, and uses that count as the scale-up starting
point. The tested plan for existing three, target six, batch two is exactly
`3 -> 5 -> 6`; no scale-to-two command is emitted. Fresh deployments retain
their `2 -> 4 -> 6` behavior. A requested lower target still scales down by
design.

Live follow-up ran a completed 6x3x3 slot after the intentional 16-to-3
scale-down, then requested 10x3x5 with the default batch. It printed
`preserving 3 existing replicas/stage`, waited at three, and scaled only to
five; all three StatefulSets finished 5/5 Ready. However, applying the changed
5-replica profile also changed the `milp.profile-hash` Pod-template annotation,
which rolled the existing three Pods before adding ordinals 3 and 4. Thus the
fix preserves existing replica *count*, not existing Pod-process identity.
The 10x3x5 controller completed proven-optimal with social objective 1601.744,
zero gap, 10 routes, 20 observations, 10 pairs, zero SLA violations, solve
time 1.805920s, traffic 0.132834s, total 2.955081s, and replay success. A
future non-disruptive scale-up requires separate profile-distribution work;
it is not implemented by this batching correction.

### MILP non-disruptive append-only scale-up repaired

Updated: 2026-08-03.

The profile-refresh cause was the global `milp.profile-hash` annotation in all
MILP StatefulSet Pod templates. Appending profile entries for replica 4/5
changed that hash and Kubernetes correctly rolled every existing Pod. The
launcher now removes that global trigger and validates existing runtime-profile
identity values before ConfigMap application: unchanged existing identities may
remain running while new profile entries are appended; changed existing
identities fail explicitly and require a deliberate refresh/redeployment.

The change required a one-time 10x3x5 migration run to remove the old template
annotation; that expected run rolled the existing five Pods per stage. The
post-migration 10x3x6 validation used `--skip-build`, printed
`preserving 5 existing replicas/stage`, waited at five, then created only
ordinal 5 per stage. The recorded ordinal 0--4 Pod UIDs in every stage were
identical before and after; the three new ordinal-5 Pods had new UIDs. All
three StatefulSets ended desired=6/ready=6 with zero container restarts and no
`milp.profile-hash` annotation. The controller completed proven-optimal:

```text
MILP-Kernel scale=10x3x6 slot=1 cutoff=60s status=proven-optimal optimal=1 incumbent=1632.138 bound=1632.138 gap=0 routes=10 observations=20 pairs=10 expected-stage=1652.138 planning=20.000 social=1632.138 realized=1625.433 physical-ms=354.567 measured-pair-ms=132.740 raw-ms=487.307 reference=1492.693 sla=0 jain=0.999973 solve=2.468263s traffic=0.129483s total=3.628297s profile=milp-experiment fingerprint=eeaa0dd4a03ba4f0105090ef589c698c link-mode=uniform-objective-constant replay=ok
```

Focused Phase 5 tests cover hash removal, append-only existing-profile
validation, explicit profile-drift rejection, and existing-Pod batch targets.
The full MILP Phase 0--6/parity suite passed 177 tests and 32 unchanged Exact
runtime/latency/forwarder tests passed before live validation. No image build,
IBG/Hybrid file, solver/outcome policy, worker, or resource change was needed
for this repair.

### MILP heterogeneous planning-link profile repair completed

Updated: 2026-08-03.

The explicit `--planning-links PATH` path is now a strict, versioned,
dimension-matched planning input rather than merely a permissive JSON adapter.
It validates all increasing-stage replica pairs exactly once, rejects invalid
IDs/directions/duplicates/incomplete coverage/nonfinite or negative costs, and
retains link source, `milp-planning-links-v1`, link mode, and the canonical
experiment fingerprint in pure and Kernel structured/compact provenance.

The uniform option remains unchanged:

```text
PYTHONPATH=. ./.venv/bin/python -m MILP.experiment --flow 1 --stage 3 --replica 2 --cutoff 5 --planning-link-ms 2
```

An explicit deterministic example can be generated deliberately, then used by
either execution path:

```text
PYTHONPATH=. ./.venv/bin/python -m MILP.planning_links --stage 3 --replica 2 > /tmp/milp-planning-links-3x2.json
PYTHONPATH=. ./.venv/bin/python -m MILP.experiment --flow 1 --stage 3 --replica 2 --cutoff 5 --planning-links /tmp/milp-planning-links-3x2.json
./.venv/bin/python scripts/run_milp_kernel.py --flow 1 --stage 3 --replica 2 --cutoff 5 --planning-links /tmp/milp-planning-links-3x2.json --timeout 300 --verbose
```

The generated source is explicitly named
`deterministic-heterogeneous-example-v1-not-calibrated`. It is suitable for
repeatable tests/demos, not empirical latency claims. A focused coupled solve
proved heterogeneous coefficients can change the chosen pair from canonical
`(1,1) -> (2,1)` to `(2,2) -> (3,2)`. A separate fixture proved measured-pair
outcomes cannot change the configured coefficients or placement.

Verification: 192 MILP tests and 40 relevant unchanged Exact latency/
processor/forwarder tests pass. Pure uniform and explicit smoke runs both
proved optimal at 1x3x2 and emitted the new provenance fields. Compilation,
silent imports, global-RNG neutrality, `git diff --check`, frozen
`IBG/`/`IBG_Hybrid/`, no Markdown under `MILP/`, and no Hybrid algorithm
import under `MILP/` pass. No live Kernel run, image build, deployment,
calibration, solver/formulation, resource, batching, utility/SLA, or outcome
policy change was performed.

### Future common state-seed feature

Requested: 2026-08-03. Deferred; nothing implemented yet.

The user wants a general --seed option, default 2050, across IBG-Exact,
IBG-Hybrid, MILP, and future baselines. It will generate a replica hidden-state
map once per experiment, preserve it across all iterations, and record the
seed/map for reproducibility and fair same-state comparisons. This is separate
from post-placement physical/observation/flow-order randomness. Current active
IBG Kernel and MILP instead load fixed state values from their runtime profile
files, so a state-seed implementation will require deliberate pure/Kernel
parity and safe Pod state-profile refresh work when reopened.

### MILP temporary synthetic-scale comparison mode

Updated: 2026-08-03. Code/test gate complete; no live run performed.

The user observed a Phase 4 benchmark consuming its cutoff while a
same-dimension Kernel run with a deterministic example link file solved in
about 0.1 seconds. Dimensions alone do not identify one MILP instance: the
benchmark owns its complete synthetic state/capacity/link table, while normal
Kernel mode uses deployed runtime states plus separately supplied links.

`--planner-profile synthetic-scale --profile-seed 20260801` now constructs the
benchmark table verbatim for pure and Kernel paths and prepares matching Pod
states. Focused tests prove pure/Kernel profile equality, benchmark problem and
measured-pair equality, matching runtime states, and rejection of mixed
synthetic/link flags. Normal runtime mode is unchanged. A live comparison is
pending user execution; no solver-runtime conclusion is claimed yet.

### MILP profile-difficulty finding

Updated: 2026-08-03.

User validation of the opt-in synthetic-scale Kernel run now matches the
benchmark's expected long-running solve behavior. The normal runtime profile
was confirmed materially different: at 3x10 it repeats a five-replica state
pattern and has abundant state-4 replicas, while the Phase 4 synthetic profile
at seed 20260801 has only four state-4 replicas, none at stage 2, plus 292
distinct directed link values across 300 links. Assigned-flow capacity remains
the flow-count default in both cases. This supports the profile/input
explanation, not a claim that Kubernetes improves solver speed.

The available temporary remedy is `--planner-profile synthetic-scale` with a
matching `--profile-seed`, which gives pure and Kernel paths the benchmark's
complete planner table and matching Pod states. Normal mode remains untouched;
the generated/deterministic tables are not calibrated real network latency.

## IBG-Hybrid rollout/resource feasibility evaluation

Updated: 2026-08-06. Analysis complete; implementation not started.

The MILP rollout/resource work can inform a future Hybrid Kernel path, but no
MILP deployment or controller behavior should be copied wholesale. Recommended
reuse is: Hybrid-owned deployment resources, a lean service/controller image
split, the existing one-worker processor/two-worker forwarder boundary,
bounded all-stage rollout batches, existing-replica preservation, and strict
append-only profile validation.

Hybrid-specific adaptation is mandatory for the L=2 route contract,
noncontiguous routes, routes beginning after stage 1, skipped-stage bypass,
belief-private sequential placement, belief retention across slots, and the
controller's lookahead cost. MILP's clairvoyant one-solve/one-slot lifecycle and
SciPy/HiGHS dependency are not transferable.

The 64Mi request/256Mi limit for each private processor is only a candidate.
It needs Hybrid-image cgroup and live traffic evidence. The public forwarder
baseline remains two workers, 25m CPU/128Mi request, and 1 CPU/256Mi limit.

Future work is now split into separately authorized phases: ownership/reuse
contracts; L=2 route execution; Hybrid-owned Kubernetes resources; lean image
split; a first small live gate; bounded rollout; append-only profiles;
Hybrid-specific resource evidence; and incremental scale validation. No final
scale readiness gate is pre-authorized. Each phase must pass before the user
chooses the next one. Evidence must cover Ready ordinal completeness, rollout
time, Pod UID preservation, profile-drift rejection, restarts/OOM/eviction,
cgroup CPU/memory, controller time/memory, exact two-hop telemetry,
skipped-stage absence, belief retention, and unchanged Hybrid placement,
learning, utility, and SLA semantics.

This evaluation changed only the four top-level handoff files. It performed no
build, cluster start, deployment, live traffic, image, manifest, runtime,
resource, algorithm, or outcome change.

## IBG-Hybrid MC professor-baseline update

Updated: 2026-08-06. Next task: pure MC redesign only.

The old future production-MC `Q=10` shortlist is superseded by the professor's
top-five complete-route shortlist. Existing `C=5` stays as per-stage pruning;
after that pruning yields the complete feasible route pool, MC ranks it by
immediate joint score and retains only the canonical top five roots. Each
retained root receives `S=50` independent rollouts. `D=2` remains unchanged.
Future simulated flows use seeded epsilon-greedy Phase 2 choices—normally
greedy and occasionally a random current feasible/pruned action. That action
randomness is the intended MC noise. The focal flow's final projected utility
is averaged; automatic MC remains disabled.

The historical all-feasible-root MC remains reference/test-only. The corrected
production MC path has not yet been implemented or runtime-measured.

## IBG-Hybrid rollout/resource work postponed

All Hybrid rollout/node optimization phases are postponed while the pure MC
correction is completed. No Hybrid image split, Kubernetes manifest, namespace,
controller, resource tuning, batching, append-only-profile, cluster, node, or
traffic work is authorized now. Those phases will be revisited during later
Hybrid Kubernetes/node implementation, one phase at a time.

### IBG-Hybrid MC-depth correction

Updated: 2026-08-06. Pending implementation.

The prior shared MC `D=2` statement is superseded. Normal Hybrid remains
`D_LOOKAHEAD=2`. MC receives its own `D_MC=10`: the first ten later simulated
flows use updated-state seeded greedy-with-epsilon-noise selection. Any still
later branch flows use pure canonical greedy only, without noise, lookahead,
or recursive MC; their load still affects the focal flow's projected value.
Both configured and effective depths require distinct provenance and tests.

## IBG-Hybrid professor-baseline MC correction complete

Updated: 2026-08-06.

The active pure policy contract is now `ibg-hybrid-policy-contract-v5`.
Production MC preserves Phase 2 per-stage `C=5` pruning, ranks the resulting
complete feasible roots, and runs exactly 50 independent rollouts for only the
canonical top five routes. At the default boundary this means 75 roots are
accounted for, five sampled, and 70 excluded.

Normal lookahead remains `D_LOOKAHEAD=2`. MC independently uses `D_MC=10` for
its seeded epsilon-greedy window and then pure updated-state greedy for every
remaining branch flow. The structured result records root ranking/scores,
sampled/excluded roots, depths, tail, seeds, steps, Phase 2 accounting, and
failures. The former all-root truncated MC is reference-only. Automatic slot
orchestration remains deterministic lookahead and cannot select MC.

Validation currently passes 82 Hybrid Phase 0--5 tests and 45 relevant
unchanged Exact characterization, latency, runner, adapter, Kubernetes-adapter,
and learning-signal regressions. The seeded sequential 20x3x10 explicit MC
boundary selected route `(1,1)->(2,4)`, reported focal objective `170.813750`,
and completed locally in 11.489301 seconds with 10 noisy and nine pure-greedy
tail actions per completed branch. This is local evidence only.

No work occurred under `IBG/` or `MILP/`, and no Kubernetes, container, image,
node, rollout, traffic, learning, latency, utility, SLA, diagnostics, replay,
netem, or reporting behavior changed. Hybrid infrastructure optimizations,
automatic MC activation, and parallel MC remain deferred.

## IBG-Hybrid explicit full-slot MC and bounded parallel rollout status

Updated: 2026-08-06.

The MC selector is now reachable through the pure iteration launcher only when
the user supplies `--policy mc`; normal invocations still use lookahead. The
mode runs a complete slot (all real focal placements, then unchanged
simulation/learning/metrics) and emits one compact line after each completed
slot. MC root rollout groups can run through `--mc-workers N`; the current
default is three workers on the four-CPU host. Fixed seeds and input-order
collection preserve the sequential selector's result while reducing wall-clock
work. A default-scale single MC decision completed in 5.470199 seconds with
three workers (75 accounted roots, five sampled, S=50); full-slot time remains
local hardware evidence and must be measured separately. IBG, MILP, all Hybrid
Kubernetes/node work, automatic MC activation, and algorithm semantics remain
unchanged.

The user has confirmed manual MC runs work. MC remains manually activated only
with `--policy mc`; automatic activation is not planned in the current Hybrid
scope.

The three-worker local process pool now lives for one explicit MC placement
phase and is reused across all real focal flows, then closes before simulation
and learning. It is a pure-Python controller optimization only, not a
Kubernetes/node change.

## Reframed Hybrid Kernel work

Updated: 2026-08-06. Planning complete; implementation not started.

The detailed Hybrid Kernel Phase 0--8 roadmap is the active merged sequence:
it applies each image, rollout, append-only-profile, and resource optimization
with the relevant Kube implementation phase. No separate replacement roadmap
exists. No resource reduction, rollout change, image, deployment, or cluster
operation is authorized by this clarification alone.

## IBG-Hybrid Kernel Infrastructure Phase 0 complete

Updated: 2026-08-06.

The Hybrid Kernel ownership/reuse boundary is now implemented as pure,
import-safe contracts in `IBG_Hybrid/kernel_infrastructure_contract.py` and is
exported through the Hybrid package. The active namespace is
`ibg-hybrid-testbed`; Hybrid controller, discovery, flow-generator, ConfigMap,
selector, and image identities are isolated from Exact and MILP. Separate
future service/controller image responsibilities are frozen without building
images.

The runtime-profile contract contains complete canonical replica identity,
hidden state, and observation seed only. Beliefs remain controller-private and
persistent; capacity and planning-link metadata remain separate controller
inputs. The Ready-discovery snapshot requires exact Hybrid-owned Running/Ready
ordinal coverage. The controller lifecycle requires complete placement before
traffic, complete telemetry before selected-only learning, no hidden-state
policy access, and no automatic MC activation.

The existing one-worker processor on 8081 and two-worker forwarder on 8080,
split HTTP clients, and 30-second public-forwarder keep-alive are recorded as
reused frozen infrastructure. No L=2 route executor, Kubernetes adapter,
manifest, image, deployment, resource adjustment, cluster operation, or live
traffic was added.

Validation passes: 108 Hybrid Phase 0--5 plus Infrastructure Phase 0 tests and
77 relevant unchanged Exact/runtime tests. Compilation, import safety,
`git diff --check`, the empty `IBG/` and `MILP/` diff check, and the absence of
Markdown under `IBG_Hybrid/` pass. Existing unrelated user changes remain
untouched.

The next unimplemented phase is Infrastructure Phase 1, the versioned Hybrid
L=2 two-hop route execution contract. It is not authorized by this completion
record and requires a separate user instruction before implementation.

## IBG-Hybrid Kernel Infrastructure Phase 1 complete

Updated: 2026-08-06.

The versioned Hybrid L=2 Kernel route boundary is implemented in
`IBG_Hybrid/kernel_route_contracts.py`, with pure execution in
`IBG_Hybrid/kernel_route_execution.py` and the Hybrid-only continuation rule
in `IBG_Hybrid/kernel_route_forwarder.py`. No code under `IBG/` or `MILP/` was
modified.

Every executable flow route contains exactly two selected replicas in
increasing stage order and its one skipped stage. Stage 1 to stage 3 and stage
2 to stage 3 are accepted. Complete-slot route building refuses partial
placements, derives final loads from all real focal actions, and uses only
Phase 0 Ready endpoints. Execution returns exactly two selected processor
observations and one measured pair per flow and rejects incomplete or
mismatched identity/load/link telemetry.

The skipped stage has no request, endpoint, observation, learning signal,
physical metric input, or measured-pair endpoint. Exact's processor/forwarder
implementation, separated-jitter signal relation, exact convolved likelihood,
state estimation, and measured-pair model are reused unchanged. Exact's own
contiguous-stage forwarder still rejects noncontiguous routes.

Validation passes: 127 Hybrid Phase 0--5 plus Infrastructure Phase 0--1 tests,
including 19 focused Phase 1 cases, and 77 relevant unchanged Exact/runtime
tests. Imports remain silent and RNG-neutral. No file output, manifest, image,
deployment, Kubernetes API call, cluster start, resource adjustment, live
traffic, algorithm change, or automatic MC activation was introduced.

Infrastructure Phase 2 is now the next unimplemented phase. It is not yet
authorized: it will add the Hybrid-owned Kubernetes resources, HTTP flow-
generator wrapper, Ready discovery adapter, and controller adapter, while
Phase 3 retains image splitting and Phase 4 retains the first live gate.

## IBG-Hybrid Kernel Infrastructure Phase 2 complete

Updated: 2026-08-08.

The Hybrid-owned Kubernetes/controller boundary is implemented without
building an image, starting a cluster, applying resources, or running live
traffic. `deploy/hybrid-kubernetes/` contains the isolated
`ibg-hybrid-testbed` namespace, narrow namespace Role, Hybrid Services,
StatefulSets, ConfigMaps, flow-generator Deployment, Kustomize base, and
controller Job template. The long-running base renders 14 resources and does
not include the Job.

Runtime profiles contain only complete canonical replica identity, hidden
state, and observation seed. Assigned-flow admission capacities and directed
planning links are separately mounted controller inputs. Beliefs remain
controller-private and persist after a successful complete slot; the
controller does not mount the hidden-state profile.

Hybrid Ready discovery lists only the Hybrid namespace/selector and produces
the Phase 0 immutable snapshot only for exact Running/Ready ordinal coverage.
All missing, duplicate, unexpected, foreign, unready, mislabelled, and
identity-mismatched fixtures fail before placement or traffic.

The Hybrid flow-generator HTTP service accepts only the versioned two-selected-
stage request and wraps the completed Phase 1 concurrent executor. The
controller reuses the existing Hybrid runner: all deterministic-lookahead
focal placements complete first, then one complete request is submitted,
then exactly two selected observations and one measured pair per flow are
validated, and only then selected-only learning and metrics execute. A failed
or partial response leaves retained beliefs unchanged.

Kernel observations carry Pod/UID/endpoint provenance and no fabricated
simulation seeds. The two selected physical samples and their independent
observation-only jitter feed the existing exact convolved likelihood and
learning boundary. Physical latency remains the active realized utility/SLA
input; measured pair latency remains separate raw outcome telemetry, and
configured planning links remain policy inputs. The bypassed stage has no
request, observation, learning input, metric input, or pair endpoint.

The processor/forwarder wrappers reuse Exact's processor, forwarding, HTTP,
telemetry, jitter, likelihood, and measured-pair implementation unchanged.
Manifests retain one processor worker on 8081 at 50m/1 CPU and 128/768 MiB and
two forwarder workers on 8080 at 25m/1 CPU and 128/256 MiB, with separate
clients and the 30-second public keep-alive. The 64/256 MiB processor candidate
was not applied.

Validation passes: 16 focused Infrastructure Phase 2 tests; 143 Hybrid Phase
0--5 plus Infrastructure Phase 0--2 tests; and 77 relevant unchanged Exact
processor, forwarder, flow-generator, adapter, runner, learning, and dynamic-
configuration tests. Compilation, import/RNG/file safety, manifest JSON/YAML
parsing, 14-resource Kustomize rendering, `git diff --check`, empty `IBG/` and
`MILP/` diffs, and no Markdown under `IBG_Hybrid/` pass. No live deployment or
traffic occurred.

Infrastructure Phase 3 is the next unimplemented phase. It requires separate
authorization to build the lean Hybrid service/controller image split and
prove service/controller dependency isolation. Infrastructure Phase 4 remains
the first separately approved small live Kernel gate.

## IBG-Hybrid Kernel Infrastructure Phase 3 implemented

Updated: 2026-08-08. Source/dependency isolation and mocked validation are
complete; local image construction is pending dependency availability.

The Hybrid deployment boundary now has distinct service and controller
Dockerfiles and dependency manifests. The service image allowlist reuses the
frozen Exact private processor/public forwarder and includes only Hybrid
runtime-profile and two-hop service execution modules. The controller image
allowlist contains policy, deterministic lookahead, manual MC, selected-only
learning/metrics, Ready discovery, controller adapters, and the Job entry
point. Image-local package initializers prevent eager repository-facade
imports, and the frozen L=2 constant is provided without copying legacy
`budgeted.py` dependencies.

The service manifest contains NumPy, FastAPI, HTTPX, and Uvicorn only; it has
no Hybrid controller/policy/runner/reporting source and no MILP, SciPy/HiGHS,
OR-Tools, or pandas source/dependency. The controller manifest contains NumPy,
FastAPI, and HTTPX only; it has no Uvicorn, pandas, SciPy/HiGHS, OR-Tools, or
MILP dependency/source and no Hybrid service ASGI entry point. Lean
controller-image copies of only the Exact learning/utility/fairness/
equilibrium and SLA functions exercised by Hybrid were functionally compared
with the frozen originals. No file under `IBG/` or `MILP/` was modified.

Focused Phase 3 validation passes 9 tests. The complete Hybrid Phase 0--5 plus
Infrastructure Phase 0--3 suite passes 152 tests, and 77 unchanged Exact
processor, forwarder, flow-generator, adapter, runner, learning, and dynamic-
configuration tests pass. Materialized image-root imports are silent,
RNG-neutral, file-clean, and show the required source/dependency inclusions
and exclusions. Phase 2 route contracts and all worker, port, client,
keep-alive, probe, hidden-state/belief, and resource boundaries remain
unchanged.

Docker 29.6.1 and the required Azure Linux Python base are locally present.
The service build was attempted with pulling and network disabled; it accepted
the Dockerfile/context and failed only because no NumPy wheel was cached. No
new network access was used, no controller build was attempted, and neither
Hybrid image was successfully built or inspected in-container. No cluster,
kind load, deployment, live HTTP traffic, commit, or push occurred.

Infrastructure Phase 4 remains unimplemented and requires separate approval.
Its first prerequisite is to build and inspect both Phase 3 images with
separately available/approved dependency access. The live gate must then use a
small topology to validate Ready coverage, complete placement before traffic,
two selected observations and one measured pair per flow, skipped-stage
absence, belief retention, restarts, and pure/Kernel semantic parity. Rollout,
append-only scaling, resource reduction, diagnostics, and larger scale remain
later phases.

### Infrastructure Phase 3 image validation complete

Updated: 2026-08-08. Infrastructure Phase 3 now has no remaining work.

Both local images were built and inspected:

- `ibg-hybrid-testbed:kernel-service-v1`:
  `sha256:01b9795bea127235c7537677379fe42c67e076e07a69c52fece1c19e19651737`,
  78,954,015 bytes, user `10001:10001`, ports 8080/8081.
- `ibg-hybrid-testbed:kernel-controller-v1`:
  `sha256:8726906596820d56ae4ec17fd03efe583e1b84cf030f79de5fb87f905a7448c3`,
  78,492,804 bytes, user `10001:10001`, no exposed port.

The controller image was built offline from the user's individually downloaded
wheelhouse through a temporary read-only BuildKit context. The wheelhouse
remains only under `/tmp`; it was not copied into the repository or image.
Direct dependency inspection confirms Uvicorn only in the service and no
pandas, SciPy/HiGHS, OR-Tools, or MILP in either image. Read-only,
network-disabled import smokes passed silently with unchanged Python and NumPy
RNG state and the required source inclusion/exclusion checks. Focused Phase 3
tests pass 9/9 after the controller pip-timeout hardening.

No stale download/build process, server, Kubernetes API call, cluster, kind
load, deployment, live HTTP traffic, commit, or push occurred. Infrastructure
Phase 4 is the next separately approved action; it owns loading these images
and running the first small live Kernel gate.

## IBG-Hybrid Kernel Infrastructure Phase 4 complete

Updated: 2026-08-08.

The separately approved small live gate completed on the existing restarted
kind cluster. The deployed Hybrid-only topology is two flows, three stages,
one replica per stage, and two slots. It consists of three two-container
StatefulSet Pods, one flow-generator Pod, and one completed controller Job in
`ibg-hybrid-testbed`. The long-running Kustomize overlay excludes the Job; the
Job was applied only after exact ordinal discovery and all four serving Pods
were Running and Ready. Live namespace-scoped authorization allowed only Pod
get/list and rejected Secret get.

The service image remained
`sha256:01b9795bea127235c7537677379fe42c67e076e07a69c52fece1c19e19651737`.
The controller tag was rebuilt only to add the Phase 4 validation entry point
and is now
`sha256:0ea07d41c9e45b74f075bdba89c532761a4d670d80452a71a24ebe5144b10daf`.
Both Phase 0 tags were loaded into all three existing nodes; no registry push
or kind cluster creation occurred.

The controller Job succeeded once and emitted two structured slot records.
The first slot covered both required route forms: `(1, 3)` and `(2, 3)`. Each
slot returned four selected observations and two measured pairs, exactly two
observations and one pair per flow. Every record confirmed complete placement
before one request, skipped-stage absence, physical-plus-observation learning-
signal composition, seedless Pod provenance, and pure/Kernel replay parity.
Slot 2's beliefs-before exactly equalled slot 1's beliefs-after. Planning links
remained separate from measured pairs. Both slots had zero physical-only SLA
violations at the unchanged 110-ms threshold.

The first-slot 1-to-3 measured pair was approximately 425.056 ms against a
configured 0-ms planning link; the other three pair measurements were about
10.563, 10.090, and 9.091 ms. These raw values remain evidence only. No
normalization, diagnostic branch, retry, calibration, or latency-law change
was made, and measured pair/observation jitter remained excluded from the
physical-only SLA and realized utility.

Post-run inspection shows unchanged UIDs, Ready state, and zero restarts for
all four long-running Pods; the completed Job also has zero restarts. No Pod
was OOM-killed or evicted. Initial readiness-probe connection refusals occurred
only while the processes were starting and cleared before traffic.

Validation passes 236 tests across Hybrid Phase 0--5, Infrastructure Phase
0--4, and the relevant unchanged Exact processor, forwarder, flow-generator,
adapter, runner, learning, and dynamic-configuration boundaries. Python
compilation, `git diff --check`, the empty `IBG/`/`MILP/` diff, no Markdown
under `IBG_Hybrid/`, and stale pytest/download/Docker-build process checks also
pass. No commit or push occurred. The small long-running Hybrid serving Pods
remain deployed and the controller Job remains completed.

Infrastructure Phase 5 is next and has not started. It requires separate
authorization to add bounded deterministic all-stage rollout batches,
preserve the existing consistent count, add only missing ordinals, reject
partial or inconsistent StatefulSet ownership, and stop at an explicitly
requested replica count.

## Hybrid shared-cluster memory incident corrected

Updated: 2026-08-08.

Root cause: the Phase 4 gate restarted the existing three-node `ibg` kind
cluster. Kubernetes then reconciled all state retained in that cluster,
including 30 old `milp-testbed` stage Pods with two service containers each and
the old MILP flow generator. Runtime measurements attributed about 4.69 GiB to
the resumed MILP namespace, about 525 MiB to the small Hybrid serving topology,
and the remainder of the roughly 7.3-GiB kind footprint to Kubernetes/container
runtime overhead and caches.

The `ibg-control-plane`, `ibg-worker`, and `ibg-worker2` containers are now
stopped. Their external cluster state was preserved and no Exact/MILP workload
was scaled, deleted, or modified. Host used memory dropped from 8.8 GiB to
2.4 GiB; available memory increased to 13 GiB and swap remains unused. The
earlier Phase 4 Job evidence remains recorded, but none of its Pods is
currently running because the shared nodes are stopped.

Future Hybrid live work is isolated by
`scripts/run_hybrid_kernel_phase4.py` and the single-node
`deploy/hybrid-kubernetes-phase4-small/kind-config.yaml`. The runner hardcodes
cluster `ibg-hybrid` and context `kind-ibg-hybrid`, requires the pinned kind
node and Hybrid images locally, rejects wrong nodes, foreign baseline
namespaces, and foreign workload Pods, verifies complete Ready serving
coverage, and only then applies the Job. It never references or starts the
shared `ibg` cluster. By default it deletes the dedicated cluster after success
or failure; retention requires `--keep-cluster`.

Eleven focused Phase 4 tests and the complete 240-test requested regression
set pass after the correction. Python compilation and `git diff --check` pass;
the frozen `IBG/`/`MILP/` diff remains empty and no Markdown exists under
`IBG_Hybrid/`. No dedicated replacement cluster was created during this fix,
and no live traffic, commit, push, image pull, or download occurred.

## Hybrid persistent lifecycle correction applied

Updated: 2026-08-08. This latest status supersedes the preceding statement
that the dedicated Hybrid cluster is deleted by default.

`scripts/run_hybrid_kernel_phase4.py run-small` now creates `ibg-hybrid` only
when absent and otherwise reuses it after exact isolation preflight. A normal
Phase 4 rerun checks the two local Hybrid images, loads them into the existing
node, reapplies the small boundary, explicitly restarts only the Hybrid serving
workloads, waits for all four serving Pods, and deletes/recreates only the
controller Job. It retains the cluster and workloads on success or failure.
`cleanup` remains an explicit command restricted to `ibg-hybrid`; there is no
automatic deletion and no `--keep-cluster` option.

The authoritative remaining-phase plan now assigns Exact-compatible
`--skip-build` to Infrastructure Phase 5 with two-image/node-presence checks,
no Docker build, no kind load, and no forced service restart. Infrastructure
Phase 6 retains ownership of append-only profile validation and proof that
existing Pod UIDs/processes survive while only missing ordinals are created.
Phases 7--8 must continue using the persistent dedicated cluster unless an
explicit recovery starts a new evidence lineage.

Thirteen focused Phase 4 tests pass for dedicated-cluster rejection, persistent
reuse, normal Hybrid-only restart, fresh controller-Job creation, explicit
cleanup, and import safety. No cluster was started, created, deleted, or
otherwise changed while applying this correction; the historical shared
`ibg` node containers remain stopped.

## Pre-Phase-5 persistent lifecycle check complete

Updated: 2026-08-08.

The dedicated one-node cluster is now live and intentionally persistent:

- Cluster/context: `ibg-hybrid` / `kind-ibg-hybrid`.
- Docker node: `ibg-hybrid-control-plane`, container `d6b8e934dfd9`.
- Kubernetes node UID: `11d63e26-dd1a-448d-9a14-a99c1667727a`, Ready.
- Current serving Pods: `hybrid-stage-1-0`, `hybrid-stage-2-0`,
  `hybrid-stage-3-0`, and one flow generator; all Ready with zero restarts.
- Current controller Job: succeeded once after the second run, zero restarts.
- Namespaces: Kubernetes defaults/system storage plus only
  `ibg-hybrid-testbed`; no Exact or MILP namespace exists.

Two complete normal Phase 4 runs reused the same Docker node container and
Kubernetes node UID. The second run reloaded the local service/controller
images, restarted only Hybrid serving resources, waited for Ready coverage,
deleted/recreated only the Hybrid controller Job, and completed the two-slot
validation again. Both required route shapes, four observations/two pairs per
slot, belief retention, jitter separation, skipped-stage absence, zero
physical-only SLA violations, and pure/Kernel parity passed.

The shared `ibg-control-plane`, `ibg-worker`, and `ibg-worker2` containers
remained stopped throughout. Current dedicated-node usage is approximately
1.188 GiB; host memory is approximately 3.6 GiB used and 11 GiB available with
zero swap.

The initial creation attempt was interrupted after slow Docker node
preparation and before kubeadm wrote an admin kubeconfig. Its incomplete
dedicated node was explicitly deleted; the clean retry then completed. No
foreign cluster or workload was touched.

Infrastructure Phase 5 has not started. This is normal image-load/restart
evidence, not `--skip-build`, bounded-rollout, existing-Pod UID preservation,
or append-only-profile evidence. The dedicated Hybrid cluster is intentionally
left running for the next separately authorized action.

Node-runtime image inspection after the second run confirms service platform
image `bb6c47d791a1f` and controller platform image `eda04655da857` under
normalized `docker.io/library/ibg-hybrid-testbed` tags. Kind nevertheless
reported the unqualified host tags as absent and re-imported them. This is a
Phase 5 acceptance input: `--skip-build` must inspect normalized `crictl`
tags/platform IDs directly rather than using kind's manifest-list comparison.

## Manual Hybrid MC Kubernetes gate scheduled after Phase 7

Updated: 2026-08-08. Planning only; no controller, image, Job, cluster,
resource, or live-traffic change occurred.

The authoritative remaining sequence is now Phase 5 bounded rollout and
Exact-compatible `--skip-build`; Phase 6 append-only profiles/Pod-UID
preservation; Phase 7 Hybrid service and controller resource evidence; Phase
7.5 manual MC Kubernetes integration; and Phase 8 incremental scale.

Phase 7.5 will add explicit controller Job `--policy mc` and
`--mc-workers N` wiring around the existing frozen MC implementation. Default
Kernel behavior remains deterministic lookahead and no automatic activation is
allowed. The gate must reuse the Phase 7-accepted topology and persistent
cluster without restarting service Pods, create one bounded controller process
pool per slot, close it before the single post-placement traffic request, and
retain beliefs through complete selected-only learning.

Acceptance will cover fixed-seed pure/Kernel MC placement/final-load parity,
one-versus-many-worker equality, RNG neutrality, complete two-hop telemetry,
skipped-stage absence, hidden-state exclusion, service Pod UID preservation,
and controller-specific CPU/RSS/deadline evidence. It will not alter service
images/resources or increase scale. Phase 8 may test manual MC at a larger
approved topology only through a separate choice and fresh controller sizing.

Phase 5 remains next and unstarted. The currently running dedicated one-node
Phase 4 cluster was not contacted or changed for this planning update.
