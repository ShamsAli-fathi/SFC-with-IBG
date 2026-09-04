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

The one-node configuration is a completed small-gate boundary, not the
intended Hybrid workload topology. The next authorized correction is one
control-plane node plus one worker node, with every Hybrid workload Pod on the
worker. It requires fresh worker-only placement, resource-envelope, and
pure/Kernel-parity validation; it provides management/workload separation but
not same-worker versus cross-worker workload-path evidence.

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

## IBG-Hybrid Kernel Infrastructure Phase 5 complete

Updated: 2026-08-09.

Phase 5 implemented count-safe persistent rollout planning and
Exact-compatible `--skip-build` without changing Hybrid algorithm or service
semantics. `IBG_Hybrid/kernel_rollout.py` validates exact ownership of all
three StatefulSets, one consistent existing count, no implicit shrink,
deterministic bounded missing-ordinal targets, and exact Ready coverage per
target. The runner reconciles the current count before batching so an existing
topology cannot be transiently reduced by the static overlay.

`run-small --skip-build` now requires the persistent `ibg-hybrid` cluster,
derives each local linux/amd64 image config ID from a temporary offline OCI
archive, matches it to the normalized `crictl` tag/config ID on the dedicated
node, and skips both builds, the kind image load, and the explicit service
restart. It still validates isolation and StatefulSet ownership, applies only
Hybrid resources, waits for exact Ready coverage, and deletes/recreates the
finite controller Job. Normal mode defines both builds with `--pull=false
--network=none`; it was mocked but not executed during the live Phase 5 gate.
No dependency, image, or package download occurred.

The unchanged-count live gate completed at 2 flows x 3 stages x 1 replica.
Docker node `d6b8e934dfd9` and Kubernetes node UID
`11d63e26-dd1a-448d-9a14-a99c1667727a` remained unchanged. Pre/post serving
state is:

- `hybrid-stage-1-0`: `df6d584d-35cd-4de9-b53e-3f8b071586c2`, restarts 0/0.
- `hybrid-stage-2-0`: `760f9475-b6f3-412f-9279-fdcd3f53ece4`, restarts 0/0.
- `hybrid-stage-3-0`: `b0dd1dc9-59d8-4580-bbe5-a3fd7c55814c`, restarts 0/0.
- flow generator: `f9b97cb9-031a-4c72-b298-2c1a85cb8562`, restarts 0.

The controller Job UID changed from
`71ba7251-e4d9-48e8-b4c6-388573e62242` to
`42dd9e64-c7e5-4b37-93d1-ecee8cac59c3` and completed once. Both slots
retained `(1,3)` and `(2,3)` routes, four observations/two measured pairs,
complete-placement-before-one-request, belief retention, skipped-stage
absence, physical/observation separation, planning/measured separation, zero
physical-only SLA violations, and pure/Kernel parity.

The shared `ibg-control-plane`, `ibg-worker`, and `ibg-worker2` containers
remained exited before and after. The dedicated node remains running. No live
new ordinal, Phase 6 profile mutation, Phase 7 resource change, Phase 7.5
Kubernetes MC flag/worker wiring, or Phase 8 scale validation occurred.

Validation passes 14 focused Infrastructure Phase 5 tests, 179 Hybrid Phase
0--5 plus Infrastructure Phase 0--5 tests, and 111 relevant unchanged Exact
processor, forwarder, flow-generator, adapter, runner, learning,
dynamic-configuration, experiment, and launcher lifecycle tests. No commit or
push occurred.

Infrastructure Phase 6 is next: append-only profile entries must preserve
every running identity byte-for-byte, create only missing ordinals under
skip-build, retain existing Pod UIDs/processes, and prove the first safe
3-flow x 3-stage x 2-replica live gate before resource or MC work begins.

## IBG-Hybrid Kernel Infrastructure Phase 6 complete

Updated: 2026-08-09.

Phase 6 added `ibg-hybrid-kernel-profile-expansion-v1` and the separate
`deploy/hybrid-kubernetes-phase6-3x3x2/` projection. The new runtime profile
preserves all three old identity/state/seed entries and adds only replica 2 at
each stage. The controller profile preserves every old capacity/link and adds
complete two-replica admission and directed planning-link coverage. Beliefs
remain controller-private; controller inputs contain no hidden state or
observation seed.

Before mutation, the runner now reads both deployed ConfigMaps, requires exact
field/canonical completeness, rejects any old runtime/admission/link drift,
and permits only complete additions. A server-side dry-run must also preserve
each StatefulSet Pod template exactly. The fixed-name ConfigMaps have no hash,
checksum annotation, or `subPath`; existing processors retain the immutable
profile loaded at startup while only new processes read added entries.

The live `--skip-build --replica 2 --rollout-batch-size 1` gate completed on
the existing persistent cluster. Docker node `d6b8e934dfd9` and Kubernetes
node UID `11d63e26-dd1a-448d-9a14-a99c1667727a` are unchanged. Preserved
serving identities, all still at zero restarts, are:

- `hybrid-stage-1-0`: `df6d584d-35cd-4de9-b53e-3f8b071586c2`.
- `hybrid-stage-2-0`: `760f9475-b6f3-412f-9279-fdcd3f53ece4`.
- `hybrid-stage-3-0`: `b0dd1dc9-59d8-4580-bbe5-a3fd7c55814c`.
- flow generator: `f9b97cb9-031a-4c72-b298-2c1a85cb8562`.

Only these new zero-restart Pods were created:

- `hybrid-stage-1-1`: `ade01b78-9f31-4795-a5c6-a39cf00291c1`.
- `hybrid-stage-2-1`: `db51c381-0491-4a88-ac61-a4b396f0e8e1`.
- `hybrid-stage-3-1`: `c40c5d06-78fd-4635-bd61-32d44223386e`.

Every StatefulSet is exactly 2 desired/Ready/current/updated. The fresh
`ibg-hybrid-controller-phase6` Job UID is
`2517db9e-db76-43a0-b63b-3c7da2bb2374` and it completed once with zero Pod
restarts. Both live slots produced six selected observations and three
measured pairs after one complete request, passed skipped-stage absence,
belief retention, seedless provenance, jitter/latency separation, and
pure/Kernel parity, and had zero physical-only SLA violations. Slot 1 covered
`(1,3)`, `(2,3)`, and `(1,2)` with one final assigned flow per replica.

Node image identities remain service
`bb6c47d791a1fdd645e1ff14ed90f04619fa09fd80d36db7d12c71227bcb78f5`
and controller
`eda04655da8573cad9d60d72c8ef44761f1fb351619f089cdab38ae490ce6803`.
No image build/load/download, service restart, node creation, or cluster
deletion occurred. `ibg-control-plane`, `ibg-worker`, and `ibg-worker2`
remained exited before and after; the dedicated cluster remains running.

Validation passes 12 focused Phase 6 tests, 191 Hybrid Phase 0--5 plus
Infrastructure Phase 0--6 tests, and 119 relevant frozen Exact processor,
forwarder, flow-generator, adapter, runner, learning, latency, dynamic-
configuration, experiment, and launcher lifecycle tests. Compilation,
Kustomize rendering, `git diff --check`, empty `IBG/`/`MILP/` diffs, no
Markdown under `IBG_Hybrid/`, and stale-process checks pass.

Infrastructure Phase 7 is next. It must collect resource evidence at this
accepted persistent 3x3x2 topology before deciding on the candidate processor
64Mi/256Mi memory reduction. Phase 7.5 Kubernetes MC and Phase 8 incremental
scale remain unstarted and separately authorized. No commit or push occurred.

### Phase 6 explicit topology CLI correction complete

Updated: 2026-08-09.

The Hybrid persistent runner now accepts `--flow`/`--flows`,
`--stage`/`--stages`, and `--replica`/`--replicas`, matching the Exact and MILP
dimension interface. Explicit `--flow 2 --stage 3 --replica 1` selects the
historical Phase 4 profile, while `--flow 3 --stage 3 --replica 2` selects the
accepted Phase 6 profile. When flow/stage are omitted, the runner retains the
old behavior by inferring them from the unique approved replica boundary.

All topology resolution and local profile validation now precede the first
cluster command. Mixed or unsupported tuples, stage counts other than three,
and larger scales fail without contacting Kubernetes. Accepted runs print the
resolved topology before continuing. This is an interface correction only:
no profile generation, arbitrary dimensions, new live traffic, image action,
resource change, or Phase 8 scale authorization was added.

Forty-four focused Infrastructure Phase 4--6 tests, 196 complete Hybrid Phase
0--5 plus Infrastructure Phase 0--6 tests, and 119 relevant frozen Exact tests
pass. Compilation, CLI help, Kustomize rendering, `git diff --check`, frozen
`IBG/`/`MILP/` diffs, no Hybrid Markdown, and stale-process checks pass. The
accepted live topology remains 3x3x2 on the persistent dedicated cluster;
Phase 7 resource evidence remains next. No commit or push occurred.

## IBG-Hybrid Kernel Infrastructure Phase 7 complete

Updated: 2026-08-09.

Phase 7 added `IBG_Hybrid/kernel_resource_evidence.py`, the baseline
`deploy/hybrid-kubernetes-phase7-3x3x2/` projection, the processor-only
`deploy/hybrid-kubernetes-phase7-3x3x2-candidate/` projection, and
`scripts/run_hybrid_kernel_phase7.py`. The runner's explicit
`--processor-memory-profile baseline|candidate` boundary is legal only with
`--skip-build --flow 3 --stage 3 --replica 2`. It validates the complete
StatefulSet transition and preserves the Phase 6 profiles and counts.

The baseline five-slot gate retained every Phase 6 serving UID/restart count.
Its resource envelope was:

- private processors: 48,599,040-byte maximum cgroup peak,
  44,486,656-byte maximum CRI working set, zero throttling/events;
- public forwarders: 129,855,488-byte peak, 125,829,120-byte working set,
  zero throttling/events;
- flow generator: 53,125,120-byte peak, 48,783,360-byte working set,
  zero throttling/events;
- controller: 68,743,168-byte maximum process RSS, 1,847,270 CPU usec,
  zero throttling, and 6 seconds of the 600-second deadline.

The controlled candidate rollout changed only processor memory from
128Mi/768Mi to 64Mi/256Mi, retained 50m/1 CPU, and deliberately replaced the
six stage Pods. Candidate Pods reached Ready five to seven seconds after
creation; earliest creation to final Ready was 16 seconds. Startup-only
connection-refused/503 readiness events cleared before traffic. The current
zero-restart stage UIDs are:

- `hybrid-stage-1-0`: `7afce7fc-6ad3-42b2-993a-0019a00eb1d5`.
- `hybrid-stage-1-1`: `b2d8b1ae-e9f1-44c9-9a3a-9e13c0a4ac54`.
- `hybrid-stage-2-0`: `285c0285-1aaa-4565-9943-be36fddd096a`.
- `hybrid-stage-2-1`: `7c24806a-6936-47f7-b9ab-5ab976c8d3a3`.
- `hybrid-stage-3-0`: `4b7dd167-72c9-4bcf-9cd7-709b0f8123a2`.
- `hybrid-stage-3-1`: `b1d98cab-5069-4a64-b47b-42b6c3332ec5`.

Docker node `d6b8e934dfd9`, Kubernetes node UID
`11d63e26-dd1a-448d-9a14-a99c1667727a`, and flow-generator UID
`f9b97cb9-031a-4c72-b298-2c1a85cb8562` are unchanged. The node remains Ready
with 4 CPU and 16,328,364 Ki allocatable memory and no Memory/Disk/PID
pressure. The shared `ibg-control-plane`, `ibg-worker`, and `ibg-worker2`
containers remained exited.

The final candidate gate measured a 46,583,808-byte maximum processor cgroup
peak and 42,487,808-byte working set, leaving 221,851,648 bytes below the
256Mi limit. Processor/forwarder/flow-generator throttling and memory-event
deltas were zero; all serving restarts, OOM kills, evictions, fatal events,
and post-Ready probe failures were zero. The controller completed in 6 seconds
with 69,238,784-byte maximum process RSS, 2,396,824 CPU usec, and 116,940
throttled usec. The candidate is accepted and remains deployed.

Each of five final slots produced six selected observations and three measured
pairs after one complete request. Noncontiguous and stage-2-first routes,
skipped-stage absence, final loads, belief retention, selected-only learning,
seedless Kernel provenance, physical/observation and planning/measured
separation, zero physical-only SLA violations, and pure/Kernel parity passed.

No image build/load/download, new dependency, node/topology scale, Phase 7.5
MC wiring, Phase 8 work, commit, or push occurred. Phase 7.5 manual MC
Kubernetes integration is next and must reuse this accepted candidate
resource boundary at 3x3x2 without changing service Pods or scale.

Validation passes seven focused Infrastructure Phase 7 tests, 203 Hybrid
Phase 0--5 plus Infrastructure Phase 0--7 tests, and 119 relevant frozen Exact
processor, forwarder, flow-generator, adapter, runner, learning, latency,
dynamic-configuration, experiment, and launcher-lifecycle tests. Python
compilation, both Phase 7 Kustomize renders, CLI help, `git diff --check`, the
empty `IBG/`/`MILP/` diff, no Markdown under `IBG_Hybrid/`, and stale-process
checks pass.

## IBG-Hybrid Kernel Infrastructure Phase 7.5 complete

Updated: 2026-08-09.

Manual Kubernetes MC is now exposed only by
`--policy mc --mc-workers N`; omitted policy still resolves to deterministic
lookahead, and `N` is restricted to 1--2. The finite Job mounts only the three
Phase 7.5 controller source files from
`ibg-hybrid-controller-phase75-source`, allowing the already-loaded controller
image to run the new boundary without a build or kind load. No serving Pod,
runtime profile, controller input, hidden state, or belief uses that ConfigMap.

The one-worker and two-worker live Jobs each completed two slots at exactly
3 flows x 3 stages x 2 replicas. Their placements and final load matrices were
identical at fixed seeds. All four slots used MC for every focal placement,
completed placement before one flow-generator request, returned six selected
observations and three measured pairs, covered `(1,3)` and `(2,3)` routes,
excluded skipped stages, propagated final loads, retained beliefs, used
seedless Kernel provenance, preserved physical/observation and
planning/measured separation, and passed pure/Kernel replay parity. Direct
child sampling observed exactly one and two workers respectively; every slot
ended with zero active children.

Controller evidence is:

- one worker: 3,367,647 CPU usec, 0 throttled usec, 58,904,576-byte maximum
  cgroup current, 62,308,352-byte cgroup peak, 71,356,416-byte maximum process
  RSS, 16 samples;
- two workers: 3,408,358 CPU usec, 897 throttled usec, 64,458,752-byte maximum
  cgroup current, 67,727,360-byte cgroup peak, 71,315,456-byte maximum process
  RSS, 13 samples;
- both Jobs: duration 8 seconds, deadline margin 592 seconds, zero controller
  restarts, zero fatal events/post-Ready probe failures, and no node pressure.

Persistent identities remain:

- Docker node `d6b8e934dfd9`;
- Kubernetes node UID `11d63e26-dd1a-448d-9a14-a99c1667727a`;
- stage UIDs `7afce7fc-6ad3-42b2-993a-0019a00eb1d5`,
  `b2d8b1ae-e9f1-44c9-9a3a-9e13c0a4ac54`,
  `285c0285-1aaa-4565-9943-be36fddd096a`,
  `7c24806a-6936-47f7-b9ab-5ab976c8d3a3`,
  `4b7dd167-72c9-4bcf-9cd7-709b0f8123a2`, and
  `b1d98cab-5069-4a64-b47b-42b6c3332ec5`;
- flow-generator UID `f9b97cb9-031a-4c72-b298-2c1a85cb8562`;
- every serving restart count remains zero.

The final Phase 7.5 Job Pod is
`ibg-hybrid-controller-phase75-rm77s`, UID
`aed04fbc-e03c-4624-9686-97e77ffa3068`, Succeeded with zero restarts. The
shared `ibg-control-plane`, `ibg-worker`, and `ibg-worker2` remain exited. No
image build/load/download, service restart, new profile, topology scale,
Phase 8 work, commit, or push occurred. Nine focused Phase 7.5 tests, 212
complete Hybrid Phase 0--7.5 tests, and 119 relevant frozen Exact regressions
pass. Phase 8 incremental scale validation is next and remains unstarted.

## IBG-Hybrid Kernel Infrastructure Phase 8 Gate 1 complete

Updated: 2026-08-09.

The first Phase 8 gate is exactly 4 flows x 3 stages x 2 replicas under
deterministic lookahead. `deploy/hybrid-kubernetes-phase8-gate1-4x3x2/`
changes only the versioned source identity and `num_flows`; its six runtime
identity/state/seed entries, six admission capacities, twelve planning links,
three StatefulSet templates, service resources, and images are unchanged.
`validate_flow_only_profile_expansion` rejects any deployed or proposed drift
before reconciliation. The runner accepts only explicit
`--skip-build --flow 4 --stage 3 --replica 2`, emits no scale or restart for
the equal two-replica target, and rejects MC at this gate.

The live gate used the already-running dedicated cluster and completed two
lookahead slots. Each slot completed four focal placements before one request,
returned eight selected observations and four measured pairs, excluded every
skipped stage, propagated admission-safe final loads, retained beliefs,
preserved selected-only learning and seedless Kernel provenance, kept
physical/observation jitter and planning/measured pair latency separate, and
passed pure/Kernel parity. The first slot contained `(1,3)` and `(2,3)` routes;
both slots had zero physical-only SLA violations.

Persistent identities remain unchanged with zero serving restarts:

- Docker node `d6b8e934dfd9`;
- Kubernetes node UID `11d63e26-dd1a-448d-9a14-a99c1667727a`;
- stage UIDs `7afce7fc-6ad3-42b2-993a-0019a00eb1d5`,
  `b2d8b1ae-e9f1-44c9-9a3a-9e13c0a4ac54`,
  `285c0285-1aaa-4565-9943-be36fddd096a`,
  `7c24806a-6936-47f7-b9ab-5ab976c8d3a3`,
  `4b7dd167-72c9-4bcf-9cd7-709b0f8123a2`, and
  `b1d98cab-5069-4a64-b47b-42b6c3332ec5`;
- flow-generator UID `f9b97cb9-031a-4c72-b298-2c1a85cb8562`.

The finite controller Job UID is
`f9ae6288-2799-4288-99ee-afe93b8cabd8`; its Pod UID is
`c060064e-ed79-4a03-a4d6-b034f8d95364`, Succeeded with zero restarts.
Controller duration was 22 seconds with 578 seconds of deadline margin,
1,811,503 CPU usec, 79,981 throttled usec, 51,302,400-byte cgroup peak, and
69,079,040-byte maximum process RSS.

Serving processor/forwarder/flow-generator cgroup peaks were
46,899,200/129,708,032/53,149,696 bytes; CPU deltas were
734,676/1,344,907/125,690 usec. Serving throttling, memory events, restarts,
fatal events, post-Ready probe failures, and node pressure were all zero. All
three StatefulSets remain exactly 2/2 Ready. The shared `ibg-control-plane`,
`ibg-worker`, and `ibg-worker2` containers remained exited before and after.

No image build/load/pull/download, service rollout, new replica/stage/node,
resource change, MC-at-scale run, later Phase 8 work, commit, or push occurred.
Fourteen focused Gate 1 tests, 225 full Hybrid tests through Gate 1, and 122
relevant frozen Exact tests pass, plus compilation, Kustomize, import-safety,
diff, frozen-tree, and process checks. The dedicated cluster remains running.

The next action requires a separate Phase 8 choice. Current evidence supports
considering a `5x3x2` lookahead-only flow increment; manual MC at `4x3x2`
would instead require its own controller-resource gate. Neither is authorized
by this completion.

## IBG-Hybrid dynamic-topology correction complete

Updated: 2026-08-09.

The Hybrid runner now accepts arbitrary positive flow/replica dimensions with
exactly three stages. It no longer treats `2x3x1`, `3x3x2`, and `4x3x2` as the
permanent topology whitelist. It generates deterministic append-only runtime
profiles, `ceil(F/R)` admission capacities, and all `3 * R^2` planning links,
validates deployed drift before writes, preserves StatefulSet templates, and
uses the Phase 5 bounded rollout plus exact Ready coverage. The general-seed,
scale-down, automatic-MC, and arbitrary-stage features remain absent.

The live command used `--skip-build --flow 10 --stage 3 --replica 5
--rollout-batch-size 2`. Resource preflight calculated 2,225m requested CPU
against 4,000m allocatable and 3,726,639,104 requested bytes against
16,720,244,736 allocatable. Rollout targets were four then five. Exactly these
nine Pods were added, all with zero restarts:

- `hybrid-stage-1-2`: `214a326d-1cc9-41f8-ae83-aa5b355468ef`;
- `hybrid-stage-1-3`: `df3d0d1a-4cef-4a38-ad4d-2057f5817915`;
- `hybrid-stage-1-4`: `99005354-cf25-4281-be5e-ebf0da189ca1`;
- `hybrid-stage-2-2`: `33ab331b-2f47-4567-8214-039802090366`;
- `hybrid-stage-2-3`: `eca4b593-fe15-4a4e-9340-5fe7a9a8f95e`;
- `hybrid-stage-2-4`: `636db67d-4995-4193-a80e-e124404f032a`;
- `hybrid-stage-3-2`: `a16bcab8-e36d-4432-90aa-0a842cee3709`;
- `hybrid-stage-3-3`: `bb1376bf-f2ba-43ab-ad0c-c3b7eef6ac25`;
- `hybrid-stage-3-4`: `ae37180b-3efe-49de-adcf-85b123703ff6`.

All six previous stage UIDs from Phase 7/8 and flow-generator UID
`f9b97cb9-031a-4c72-b298-2c1a85cb8562` were preserved with zero restarts.
Docker node `d6b8e934dfd9` and Kubernetes node UID
`11d63e26-dd1a-448d-9a14-a99c1667727a` are unchanged. All three StatefulSets
are 5/5 Ready and the flow generator remains Ready. The final finite Job Pod
is `ibg-hybrid-controller-dynamic-svhcp`, UID
`939b7c13-e1cd-4b3d-9644-507ed70d3c86`, Succeeded with zero restarts.

The generated ConfigMaps identify `10x3x5` and contain exactly 15 runtime
profiles, 15 admission entries of capacity two, and 75 planning links. Both
initial and unchanged two-slot runs completed ten placements before one
request per slot and returned twenty selected observations and ten measured
pairs. They passed required route coverage, skipped-stage absence,
admission/final-load propagation, selected-only learning, belief retention,
seedless provenance, jitter/link separation, physical-only SLA accounting, and
pure/Kernel deterministic-lookahead parity.

Final processor/forwarder/flow-generator maximum CRI working sets are
42,639,360/126,119,936/49,430,528 bytes; cgroup peaks are
46,899,200/130,232,320/53,907,456 bytes with zero memory events. The final
controller completed in 16 seconds against 600 seconds, restarted zero times,
and the collector found no unsafe resource condition. Startup-only readiness
connection failures occurred while new containers started; there were no
post-Ready probe failures, fatal events, serving restarts, OOM/evictions, or
node pressure.

The shared `ibg-control-plane`, `ibg-worker`, and `ibg-worker2` remain exited.
No Docker build, kind load, image pull/download, service restart, resource
change, worker-node addition, MC-at-scale run, Exact/MILP edit, commit, or push
occurred. The dedicated `ibg-hybrid` cluster remains running.

Validation passes 9 focused dynamic tests, 234 complete Hybrid tests, 119
relevant frozen Exact tests, and 194 frozen MILP tests, plus Python compilation
and all seven retained Hybrid Kustomize renders. `IBG/` and `MILP/` diffs are
empty and no Markdown file exists under `IBG_Hybrid/`.

## IBG-Hybrid per-timeslot console output complete

Updated: 2026-08-09.

`IBG_Hybrid/console_output.py` now prints the requested readable metrics block
for every completed pure or Kernel Hybrid slot, including manual MC. It shows
iteration and slot, `physical-only-v1`, per-flow processing/pair/raw/outcome
latency, predicted/realized/physical/raw utility, SLA violations, fairness,
time, and equilibrium with the requested precision. It prints none of the flow
order, placements, observations, learning signals, beliefs/deltas, or CSV
messages.

The current Hybrid result contract stores predicted per-flow utility only
after summing its selected stage-level components. The formatter therefore
prints that stored scalar directly. Hybrid also currently supports only the
active `physical-only-v1` outcome in slot computation, so realized and
physical utilities intentionally match; this is stated explicitly rather than
presented as two independently calculated outcomes.

Kernel `run_small_live_gate` now calls its printer after each slot passes
complete telemetry, route, retention, pool-cleanup, and parity validation and
before running the next slot. Controller stdout carries the human block plus a
prefixed evidence line. `scripts/run_hybrid_kernel_phase4.py` follows those
logs while the Job runs, displays only the human block, returns the normalized
JSON evidence to existing collectors, and no longer prints detailed evidence
at Job completion.

The new formatter is controller-only in deployment ownership. It is included
in the future controller image and in the current Phase 7.5 source ConfigMap
mounts used by Phase 7.5, Phase 8, and dynamic Jobs. Service images and Pods
remain unchanged.

Validation passes 53 focused tests, 238 complete Hybrid tests, and 119 relevant
frozen Exact tests. Compilation, all seven retained Hybrid Kustomize renders,
and all three affected Job parses pass. No live run, build/load/pull/download,
cluster or serving-process mutation, MC-at-scale run, Exact/MILP edit, commit,
or push occurred.

## IBG-Hybrid production experiment lifecycle correction complete

Updated: 2026-08-09.

The Hybrid launcher now has a real production command:

`run --skip-build --flow F --stage 3 --replica R --rollout-batch-size B
--max-iterations N`

All four numeric inputs are positive and resolved before cluster access. The
normal controller runs one slot at a time, carries controller-private beliefs,
streams each completed human block before the next slot, stops on the first
existing equilibrium result, or stops exactly at `N` and prints that equilibrium
was not reached. `run-small` remains only for historical bounded validation.

The rendered production Job receives the explicit limit and lifecycle marker;
the dynamic template no longer contains `MAX_ITERATIONS=2`. Production removes
the historical 600-second gate deadline because the iteration limit is already
finite. Historical Job templates and gates keep their previous bounds.

Human output no longer contains a `Latency:` section or per-flow latency lines.
The underlying physical processing, measured-pair, raw end-to-end, and selected
outcome values remain unchanged in `HybridSlotResult` and prefixed machine
evidence. Utility, SLA, fairness, timing, equilibrium, learning, jitter, and
planning/measured-pair behavior are unchanged.

Focused lifecycle/presentation checks pass 73 tests; the complete Hybrid suite
passes 249 tests; 119 relevant frozen Exact regressions pass. Seven retained
Kustomize projections render and seven controller Job templates parse. The
PyYAML module was not locally installed, so Job parsing used offline
`kubectl create --dry-run=client --validate=false`; nothing was downloaded.

No live Kubernetes experiment, cluster mutation, serving-process change,
image build/load/pull/download, commit, or push occurred. `IBG/` and `MILP/`
remain unmodified. Large-topology Kubernetes MC is still unsupported: manual
MC remains isolated to the accepted `3x3x2` candidate-resource topology with
one or two workers, while ordinary dynamic production runs default to
deterministic lookahead.

## IBG-Hybrid intentional replica scale-down correction complete locally

Updated: 2026-08-11.

The no-shrink failure has been removed from the Hybrid production rollout
contract. `5 -> 5` is a no-op, `5 -> 8` with batch two targets `7` then `8`, and
`8 -> 5` is one deliberate target that removes only StatefulSet ordinals
`5`, `6`, and `7`. Plans expose their direction plus added and removed ordinals.

The dynamic transition validator now requires exact deterministic deployed and
target runtime/controller documents and exposes retained/added/changed/removed
identity and link sets. Retained runtime identities, hidden states, seeds, and
planning links remain identical. Only removed replicas may lose runtime or
admission entries, every removed link has a removed endpoint, and retained
admission changes must match `ceil(flows / replicas)`.

The mocked production lifecycle dry-runs the lower target without applying it,
scales all three StatefulSets, waits for exact retained Ready coverage and
removed-Pod absence, and only then applies the reduced ConfigMaps. Final profile,
template, and readiness checks precede controller Job creation. Retained Pod and
flow-generator UID/restart comparisons are separate from the declared removed
set. A repeated unchanged five-replica run emits no scale or service restart.

No live cluster command, cluster start, Kubernetes mutation, image operation,
dependency download, Exact/MILP edit, commit, or push occurred. The last observed
eight-replica live state was not treated as current evidence and must be
re-snapshotted before a separately approved live gate. The relevant MILP code
was inspected read-only; its direct lower-target planner concept was reused, but
its scale-up-oriented existing-profile validator was intentionally not copied.

Validation passes 37 focused scale-down/dynamic/production tests, 105 Hybrid
Infrastructure Phase 5--8 and lifecycle tests, all 252 Hybrid tests split into
memory-bounded processes, 119 relevant frozen Exact tests, and 50 frozen MILP
Phase 5 rollout/profile tests. Python compilation, all seven retained Kustomize
renders, and all seven controller Job parses pass.

## IBG-Hybrid initial/final belief output complete locally

Updated: 2026-08-11.

The production controller prints `Initial replica state` before its first slot
and `Final replica state` after the equilibrium reached/not-reached line. Each
table is sorted by stage/replica and prints the four-state belief vector with
three decimals. Per-timeslot metrics still print no beliefs or belief deltas.
The Exact presentation was inspected read-only; its hidden state and legacy
capacity/delay/gamma columns were intentionally not copied into Hybrid.

Focused lifecycle/console/service-isolation validation passes 70 tests; all 253
Hybrid tests pass in memory-bounded groups; 119 relevant frozen Exact tests
pass. Compilation and seven Kustomize renders pass. No live cluster action,
image operation, download, Exact/MILP edit, commit, or push occurred.

## Hybrid reproducible offline image-build correction complete locally

Updated: 2026-08-11.

The former normal Hybrid build was only accidentally offline when Docker could
reuse its old pip layer; clean cache builds failed because pip tried PyPI while
Docker had `--network=none`. Normal builds now require two explicitly validated,
project-local ignored wheelhouses, with committed exact service/controller
manifest and lock files in `deploy/hybrid-kubernetes/wheel-manifests/`. The
Dockerfiles use only `pip --no-index --find-links=/opt/ibg-hybrid-wheels` and
remove those copied wheels after installation. Neither dependency set contains
MILP/SciPy/HiGHS/OR-Tools; the service retains Uvicorn while the controller does
not.

The runner prints one unambiguous image-mode line. Without `--skip-build`, it
validates both wheelhouses before any cluster/Docker action, then can build both
images with `--pull=false --network=none`, load both only into `ibg-hybrid`, and
restart only Hybrid serving workloads. With `--skip-build`, it never validates
or requires wheel files and does no build/load/restart; it instead validates the
existing node-local images before its existing configuration/rollout/Ready/Job
flow. `scripts/hybrid_offline_wheelhouse.py show|validate|copy` is import-safe
and never downloads; `copy` is explicit and accepts only a complete supplied
wheel set.

No persistent local wheelhouse is currently present, so no clean Docker image
build was attempted or claimed. Local checks pass: 48 focused wheelhouse/Phase
3--5 tests, 39 dynamic/lifecycle/Phase 6 tests, and 52 Phase 7.5/8/Hybrid
regressions; Python compilation passed. No Kubernetes mutation, kind load,
image build/load, package download, Exact/MILP edit, commit, or push occurred.
Next: manually obtain the exact files listed by
`python -m scripts.hybrid_offline_wheelhouse show`, explicitly stage both
wheelhouses, validate them, and separately approve any normal-build/live gate.

The user subsequently explicitly authorized this one-time setup. Pinned wheels
were downloaded into the ignored project-local `.offline-wheels/ibg-hybrid/`
cache; validation passed for service and controller. Clean local Docker builds
used `--no-cache --pull=false --network=none` and produced service manifest-list
ID `sha256:fb1245a5bcfd8c46a5e0d500aaac62d3c36b051744cad3b5604323a9bb2683f8`
and controller ID
`sha256:0ea07d41c9e45b74f075bdba89c532761a4d670d80452a71a24ebe5144b10daf`.
No host package was installed, no image was loaded into kind, no container was
started, and no Kubernetes resource was contacted or changed. Future normal
runs may build from this persistent ignored cache; `--skip-build` continues to
reuse only node-local images and therefore intentionally does not use it.

## Hybrid seeded hidden-state profile allocation complete locally

Updated: 2026-08-11.

`IBG_Hybrid/kernel_profile_expansion.py` now owns
`ibg-hybrid-profile-state-allocation-v1`. For each stage it builds deterministic
ten-replica strata with exact Very Good/Good/Bad/Very Bad counts `3/3/2/2`.
Hash-ranked feasible choices permute the ordinal layout by profile seed while a
prefix constraint keeps every arbitrary replica count within one of the
30/30/20/20 ideal. Repeated generation is byte-identical, growth is append-only,
trim removes only high ordinals, and neither Python nor NumPy global RNG is used.

The normal `run` CLI requires `--profile-seed`. Runtime source provenance records
the allocation version/seed only on the processor side; controller inputs and
the controller Job expose neither it nor hidden state, observation seed, or mix.
Observation seeds retain their separate canonical/identity-derived ownership.
Historical fixed profile JSON remains unchanged.

Seed-aware drift validation recognizes exact legacy or seeded deployed runtime
documents. A changed allocation fails before apply without
`--refresh-runtime-profiles`. The explicit mocked refresh is `--skip-build` only,
requires an unchanged replica count, applies no Pod-template hash, reconciles the
validated target, and deletes only hidden-state-changed Pods stage-by-stage with
Ready coverage before the controller Job. Unaffected stage Pods and the flow
generator must preserve UID/restart state.

Local validation passes 271 complete Hybrid tests in memory-bounded groups and
126 relevant frozen Exact tests. No live Kubernetes read or mutation, image
build/load/pull, dependency download, Exact/MILP edit, commit, or push occurred.

The separately approved legacy `15x3x10` migration gate must re-snapshot live
state before using:

`PYTHONPATH=. ./.venv/bin/python -B scripts/run_hybrid_kernel_phase4.py run --skip-build --flow 15 --stage 3 --replica 10 --rollout-batch-size 3 --profile-seed 42 --refresh-runtime-profiles --max-iterations 6`

After that explicit refresh, rerun the same command without
`--refresh-runtime-profiles` and require every seeded serving UID/restart count
to remain unchanged while only the finite controller Job is recreated.

## Hybrid seeded-profile live migration attempt

Updated: 2026-08-11.

The approved dedicated-cluster migration from the legacy `15x3x10` document to
profile seed `42` reached exact `10/10` Ready coverage at every stage and
installed the processor-private seeded runtime document.  Each stage now has
exactly Very Good/Good/Bad/Very Bad counts `3/3/2/2`; the controller document
remains free of hidden state and seed data.  The staged refresh deliberately
replaced all ten stage-1 Pods, all ten stage-2 Pods, and only stage-3 ordinals
`0`, `1`, `5`, `6`, and `7`; stage-3 ordinals `2`, `3`, `4`, `8`, and `9` and
the flow-generator Pod retained their identities.

This first live refresh gate is not accepted as clean evidence.  During the
stage-2 cold start, `hybrid-stage-2-1` public forwarder failed its 8080 liveness
probe once and restarted.  The refresh guard therefore correctly aborted before
deleting/recreating the controller Job or running traffic.  There was no OOM,
eviction, image operation, download, or shared-cluster action.  The dedicated
cluster remains running and all stage Pods are now Ready; the one restart remains
recorded on that Pod.

The requested unchanged seeded `--skip-build` rerun then completed its fresh
controller Job in 68 seconds without replacing a serving Pod or changing any
serving restart count.  It completed six lookahead slots (equilibrium not
reached).  Every slot had 30 selected observations and 15 measured pairs, with
complete placement before one request, skipped-stage absence, seedless Kernel
provenance, separated-jitter validation, and pure/Kernel replay parity.  State
selection counts (Very Good/Good/Bad/Very Bad) were respectively `5/8/7/10`,
`10/6/8/6`, `12/12/4/2`, `12/15/3/0`, `13/14/3/0`, and `15/14/1/0` for slots
1--6.  The shared `ibg` Docker nodes remained stopped throughout.

The next action is not another refresh.  Diagnose and, if separately approved,
correct the cold-start liveness behavior before repeating the explicit refresh
acceptance gate with zero replacement-Pod restarts.  No commit or push occurred.

## Hybrid fresh-host bootstrap repair

Updated: 2026-08-11.

The migrated Ubuntu 24.04 host now has Docker, kubectl 1.36, and kind 0.32
installed; the Hybrid development environment pins and imports Pydantic 2.13.4.
The first normal 15x3x10 invocation created the dedicated `ibg-hybrid` kind
cluster but stopped before any Hybrid namespace or workload was created: its
server-side generated-overlay dry run could not use the namespace that would
otherwise be created by the later real apply.

`scripts/run_hybrid_kernel_phase4.py` now creates only the dedicated Namespace
manifest before that dry run, and only during first-cluster bootstrap. Existing
cluster reconciliation, profile validation, template preservation, and all
placement/runtime contracts remain unchanged. Focused dynamic-topology,
Phase-5 rollout, and production-lifecycle tests pass (47 tests), along with
compilation, diff checks, and a direct bootstrap-order check.

The failed bootstrap left only the disposable dedicated kind control-plane and
system Pods. It must be removed with the launcher `cleanup` action before the
corrected first-run command can create the workload cleanly. No Hybrid traffic
or controller Job ran.

The subsequent normal 15x3x10 serving rollout completed on the current
one-control-plane cluster. The user then stopped the progressing controller
Job; all thirty two-container replica Pods and the flow generator remained
Running with zero observed restarts. A transient host-side `kubectl logs
--follow` fsnotify watcher failure did not stop the Job or change Hybrid
semantics. The launcher displayed 15 flows, but controller evidence recorded
`configuration.num_flows: 20` and emitted twenty per-flow results. That
stopped-run discrepancy was later checked by the user: a subsequent test
confirmed correct requested-flow propagation. Treat it as an interrupted-run
anomaly, not an active blocker; the stopped run itself remains invalid 15-flow
evidence.


## Hybrid management/workload node separation complete locally

Updated: 2026-08-15.

The repository now defines `ibg-hybrid` as one kind control-plane plus one
labelled worker. All three replica StatefulSets, the flow generator, the base
and dynamic controller Jobs, and every retained Phase 4/6/7/7.5/8 controller
Job select `ibg-hybrid.workload-node=true`. The launcher requires exactly the
Ready `ibg-hybrid-control-plane` and `ibg-hybrid-worker` roles and rejects any
recognized Hybrid workload Pod outside the worker. Serving rollout readiness
also requires worker placement.

Resource preflight now reads only the worker allocatable envelope, counts only
nonterminal Pods bound to that worker, excludes control-plane management Pods
and terminal Jobs, and retains the accepted request formulas and all resource
declarations. Phase 7 CRI serving statistics now target the worker. No Hybrid
policy, lookahead/MC behavior, route, profile, physical/observation jitter,
learning, belief retention, metric, utility/SLA, telemetry, console, image, or
rollout semantics changed. Frozen Exact and MILP source files were not edited.

Validation passes 71 focused topology/dynamic/rollout tests, 183 complete
Hybrid Kernel/infrastructure/offline-build tests, and 93 pure Hybrid tests
(276 Hybrid tests total in memory-bounded groups). The established 119 relevant
frozen Exact processor, forwarder, flow-generator, adapter, runner, learning,
latency, dynamic-configuration, experiment, and launcher tests pass. All seven
retained Hybrid Kustomize overlays and all seven controller Job templates render
offline. Changed Python compiles, `git diff --check` passes, and no Markdown was
created under `IBG_Hybrid/`.

No live cluster, Docker image, kind node, Kubernetes object, or traffic was
mutated. The last user-supplied live state is the historical single-control-plane
cluster with thirty replica Pods and one flow generator; its controller Job was
stopped by the user. That state was not reverified during this local
implementation. The later user check confirming correct requested-flow
propagation remains authoritative, and the stopped mismatch is not 15-flow
evidence. The new runner intentionally rejects that one-node topology before
mutation.

Next action requires explicit approval to cleanly replace the current dedicated
cluster and execute the worker-placement/resource/pure-Kernel live gate. Until
then there is no two-node live evidence and no same-worker/cross-worker,
multi-host, NIC, SR-IOV, DPDK/VPP, hugepage, line-rate, or datapath-performance
claim.


## Hybrid two-node bootstrap readiness correction

Updated: 2026-08-15.

The user's normal 15-flow/3-stage/7-replica command created
`ibg-hybrid-control-plane` and `ibg-hybrid-worker`, then the launcher failed
closed at its first topology check. Read-only inspection showed the eventual
inventory is correct: both exact nodes are Ready, only the worker has
`ibg-hybrid.workload-node=true`, and no Hybrid workload was deployed. The cause
was a startup race: kind's create-time wait completed for the control-plane
before the worker was Ready.

Fresh-cluster operation now explicitly waits for both named nodes before the
unchanged strict preflight. Fifty-five focused Phase 4 topology, dynamic-
topology, and Phase 5 rollout tests pass; changed code compiles and
`git diff --check` passes. The launcher's read-only preflight also passes
against the retained live cluster. Codex performed no Kubernetes or Docker
mutation while diagnosing or validating this correction.

Next action is for the user to rerun the same normal-build command without
cleanup and without `--skip-build`. It will reuse the empty two-node cluster,
build and load both Hybrid images, then continue the resource, rollout,
worker-placement, controller, and pure/Kernel gates. No live workload evidence
exists yet, and no same-worker/cross-worker, multi-host, NIC, or line-rate claim
is authorized.

The resume path now explicitly treats a validated existing cluster without the
Hybrid namespace as pristine and runs namespace-first bootstrap with zero
existing replicas. A final read-only inventory confirms
`ibg-hybrid-testbed` is absent and only Kubernetes management Pods exist. The
same 55 focused tests pass after this addition.


## Hybrid two-node live test user-confirmed

Updated: 2026-08-15. The user reports that a test run after the bootstrap and
resume corrections works. No detailed results were supplied or requested for
retention, so no dimensions, metrics, placement inventory, parity values,
restart/resource observations, or trace artifact are claimed here. The current
two-node Hybrid functional task is complete; further evidence capture is
optional and requires a new explicit request.


## Deferred Hybrid follow-up backlog

Updated: 2026-08-15. The user requested that three later workstreams be
retained: opt-in `tc/netem` robustness testing, verification and possible
production integration of the existing Hybrid CSV functions, and an opt-in
per-timeslot control-plane data-footprint feature.

No implementation or runtime mutation was performed. The planned order is
netem robustness, CSV verification, then control-plane footprint. The Exact
`netem_v1`, host-side CSV, and `control_plane_v1` contracts are compatibility
references, not proof that their code can be copied unchanged into Hybrid.
Each workstream must preserve the active Kernel-only runtime, worker placement,
Hybrid algorithm/MC behavior, separated physical and observation jitter,
selected-only learning, physical-only utility/SLA outcome, telemetry, and
frozen Exact behavior. Packet loss and wire-byte claims remain outside the
recorded scope.


## Hybrid JSONL trace persistence complete locally

Updated: 2026-08-15. Successful production Hybrid runs now save their detailed
machine evidence outside Kubernetes as
`runs/ibg-hybrid-experiment-<UTC timestamp>.jsonl` by default. The launcher
prints the final path, and `--trace-dir` can relocate it. The versioned file has
start, per-timeslot, and completion records; every timeslot includes the
existing placement records and therefore each configured flow's
`measured_pair_ms`, alongside observations, beliefs, metrics, identities,
loads, planning links, and parity evidence.

The writer validates complete dimensions, contiguous slots, one placement and
measured pair per flow, two selected observations per flow, and equilibrium
typing before creating the file. Cgroup evidence is neither required nor added,
and processor-private profile allocation remains undisclosed. The complete
Hybrid Kernel selection passes 178 tests; compilation and `git diff --check`
pass. No live cluster, Job, image, or traffic was changed or executed for this
implementation.


## Hybrid SLA threshold is now 80 ms locally

Updated: 2026-08-15. With explicit user authorization, Hybrid physical-only SLA
classification now compares each flow's two selected physical processing
latencies against 80 ms. Pair latency remains present in
`measured_pair_ms`/raw end-to-end reference metrics and observation jitter
remains learning-only; neither enters the active SLA count. Exact remains at
110 ms and no Exact Python source was edited for this change.

The full 279-test Hybrid selection passes; compilation and `git diff --check`
pass. Existing JSONL traces keep their historical threshold. No live build or
run was performed, so the current node-local controller image still has the
previous behavior until the next normal-build production command.


## Hybrid automatic random series implemented locally

Updated: 2026-08-15. `scripts/run_hybrid_kernel_phase4.py run --runs N` now
requires no seed argument and rejects an explicitly supplied profile seed. It
uses system CSPRNG values, guarantees a nonzero distinct experiment seed for
each member, and records that seed in a separate JSONL trace. Every member gets
a new finite controller Job and fresh uniform beliefs; its experiment seed is
used for the policy root and first slot ID.

The environment remains fixed: an existing seeded Hybrid deployment keeps its
profile seed, while a fresh environment receives one automatic random profile
seed for the entire series. Runtime-profile refresh is disallowed. The first
member honors the requested build mode and subsequent members reuse the
prepared image/workloads. Ordinary one-run operation is unchanged and still
requires `--profile-seed`.

All 284 Hybrid tests pass. The relevant 109-test frozen Exact regression
selection passes, changed Python compiles, the CLI help exposes the intended
contract, and `git diff --check` is clean. No live Kubernetes object, kind
cluster, Docker image, or traffic was changed or exercised. Because the local
controller behavior has changed (including the earlier Hybrid 80-ms SLA), the
next live invocation should be a normal build, not `--skip-build`.

Deferred next work remains the isolated CSV-helper verification. It must not
change default run output, historical CSV files, the new random-series/JSONL
contract, or frozen Exact behavior.


## Hybrid live mismatch diagnosed and resume path corrected

Updated: 2026-08-15. Read-only inspection after the user's failed launch shows
all three Hybrid StatefulSets at 3/3 Ready replicas. The deployed runtime
profile is still the exact seeded `20x3x10` allocation with profile seed 42.
StatefulSet last-applied data describes 7 replicas, while the replica field is
currently owned through the Kubernetes scale subresource. The launcher
therefore correctly detected inconsistent persisted layers, but previously had
no way to resume the safe low-ordinal prefix.

The local launcher now validates and resumes this exact interrupted scale-down
shape. It still rejects profiles smaller than live replica counts, unequal
stage counts, ownership/template problems, or any deterministic document
drift. Focused recovery and lifecycle tests pass 44 tests; the complete Hybrid
selection passes 286 tests; the relevant frozen Exact selection passes 109
tests. Changed Python compiles and `git diff --check` passes.

Codex made no live mutation. The next user invocation can use the intended
normal-build `--runs` command; it will first reconcile the retained three-Pod
prefix to the requested topology and then execute the series. Do not use
`--skip-build` until the updated controller image has been built successfully.


## Hybrid CSV helpers repaired and `--csv 1` available locally

Updated: 2026-08-15. The five requested outputs now work from the active
Hybrid JSONL schema while preserving their legacy layouts. `time.csv`,
`sla_violations.csv`, `aggregate_utility.csv`, and `jain_index.csv` use one
six-character experiment column with one completed-timeslot value per row.
`replica_results.csv` uses `(stage, replica)` columns and appends the initial
beliefs plus every completed post-update snapshot. `log_results` and
`results.csv` were ignored completely as requested.

`aggregate_utility.csv` now deliberately records
`raw_end_to_end_reference_utility`. SLA records the active physical-only count;
time and Jain use their existing completed-slot metrics. The helpers safely
handle empty files, reordered/added belief identities, and unequal run lengths;
they reject malformed files, duplicate headers/run hashes, non-finite metrics,
invalid Jain/SLA/time values, and malformed beliefs.

CSV generation is off by default. Adding `--csv 1` to either a single
production run or automatic random `--runs N` series exports each completed
trace host-side to ignored `figures/`; no controller or Kubernetes storage is
used. A real retained Hybrid trace passed a temporary export probe. All 291
Hybrid tests and the relevant 109 Exact regressions pass; compilation, CLI
help, and `git diff --check` pass. No live runtime or existing CSV was mutated.


## Hybrid CSVs isolated in their own folder

Updated: 2026-08-15. `--csv 1` now saves all five Hybrid reports under
`/home/vhakami/vesal/SFC-with-IBG/figures/IBG_hybrid/`. The exporter creates
the directory recursively when absent. Existing CSV formats and semantics are
unchanged, and no historical file was moved.


## Hybrid control-plane data footprint complete locally

Updated: 2026-08-15. Production `--csv 1` now enables per-timeslot Hybrid
controller-boundary payload/message accounting and propagates the switch into
the controller Job. `--csv 0` or omission emits no footprint JSONL block and
creates no footprint CSVs. The original five Hybrid reports remain unchanged.

Completed slots count actual HTTP application-body bytes for one accepted
aggregate Kubernetes Pod-list exchange and one route-command/selected-
telemetry exchange. Belief TX/RX bytes and messages remain zero because beliefs
are controller-local. The data-only schema validates the six primary category
totals, exactly one message for each discovery/route/telemetry direction, zero
belief messages, and derived belief TX-plus-RX totals without double counting.
Timing, CPU, memory, cgroups, HTTP headers, wire bytes, forwarder traffic, NIC
throughput, and line rate are outside this implementation.

Enabled trace export creates 16 separate wide-layout files under
`figures/IBG_hybrid/footprint/`, including each payload/message category,
belief totals, and exact grand totals. Mixed enabled/disabled traces, malformed
schemas/files, negative values, incorrect totals, and duplicate run hashes are
rejected before export.

Local verification passes all 305 Hybrid tests and 188 broad frozen Exact
regressions. All seven retained Hybrid Kustomize overlays render, changed
Python compiles, CLI help and `git diff --check` pass. No live Kubernetes or
Docker mutation and no experiment traffic occurred. A live validation would
require separate user approval; it is not needed for local completion.

Final verification addendum: `scripts/hybrid_control_plane_summary.py` now
provides the requested data-only trace summary for every payload/message
category, derived belief totals, and exact grand totals. It emits no timing or
CPU metrics and leaves Exact's summary unchanged. Three additional focused
tests pass, bringing the complete Hybrid result to 308 tests; the recorded 188
Exact regressions, seven offline renders, compilation, CLI help, and diff
checks remain passing.


## Hybrid per-timeslot execution optimization plan recorded

Updated: 2026-08-16. Four architecture-only phases are now planned. Phase 1
reuses selected HTTP client pools across slots and is medium difficulty. Phase
2 creates a two-process-safe independent focal-candidate evaluation boundary
and is high difficulty because exact serial/parallel semantic equality is
mandatory. Phase 3 gives the finite controller one reusable two-process pool
and is medium-high difficulty because lifecycle, stale-state prevention,
exception propagation, and termination cleanup must all be proven. Phase 4 is
last and conditionally raises only the controller's shared CPU request; it is
medium overall difficulty because the small manifest change requires complete
resource-preflight agreement and controlled live non-regression evidence.

No real-flow decision, dependent projected flow, or state commit may run in
parallel. Candidate results must be collected in canonical order before the
unchanged tie rule. No exclusive CPU, CPU pinning, extra node, topology change,
algorithm change, new footprint timing/CPU field, Exact edit, or live mutation
is authorized by this planning entry. The current cluster and running serving
Pods were not touched.

The next action is local Phase 1 implementation of persistent HTTP-client
lifecycles with focused connection-reuse/cleanup, footprint, behavior-parity,
and regression tests. Any image build, Job execution, workload mutation, or
live validation remains separately approval-gated.


## Hybrid optimization Phase 1 complete locally

Updated: 2026-08-16. The controller now reuses one Kubernetes API client and
one flow-generator client across its finite slot loop, then closes both on
success or failure. Partial controller construction also closes already-created
clients. The flow-generator owns one persistent asynchronous first-forwarder
client through FastAPI startup/shutdown, while direct non-ASGI executor calls
remain safely ephemeral.

The implementation does not change any request/body count, timeout, footprint,
forwarder client, keep-alive, pair latency, algorithm, load, belief, learning,
utility/SLA, telemetry, scheduling, or resource value. All 312 Hybrid tests and
188 relevant frozen Exact regressions pass; seven offline Hybrid renders,
changed-Python compilation, and `git diff --check` also pass. No live resource
or generated result was touched, and no timeslot speed claim is made.

The next action is local Phase 2 only. It must create and validate a pure worker
boundary for independent candidates of one focal lookahead decision while
leaving real flows, projected flows inside each branch, state commits, and the
production execution path serial. Phase 3 pool activation and Phase 4 CPU
priority remain deferred.


## Hybrid optimization Phase 2 complete locally

Updated: 2026-08-16. Hybrid deterministic lookahead now exposes one frozen,
picklable task and module-level evaluator for each independent focal candidate.
Every task explicitly carries current loads, configuration/parameters, the
scored action, admission, beliefs, planning links, depth, and canonical index.
The evaluator creates private state and a private policy/cache, keeps future
flows inside the branch sequential, and returns an indexed complete evaluation
or branch failure. Canonical ordering, strict improvement, first-on-tie
selection, and unexpected-error provenance are enforced during assembly.

Production `select_lookahead` still evaluates all candidates serially. Only the
private validation path accepted a caller-owned two-process executor; there is
no persistent pool or controller/runner/CLI/Job/launcher activation. MC pool
semantics and all algorithm, random, learning, utility/SLA, telemetry,
footprint, scheduling, resource, and topology behavior remain unchanged.

Focused verification passes 46 tests. Full verification passes all 321 Hybrid
tests and the recorded 188 relevant frozen Exact regressions. Changed Python
compiles, seven Hybrid overlays render offline, and `git diff --check` passes.
No live cluster mutation, image build/load, Job, or traffic occurred; no
repository experiment trace or CSV output was created or modified. No
performance improvement is claimed from local tests.

Phase 3 is the next planned optimization but is not implemented or authorized
by this entry. It will own one bounded controller-lifetime process pool and may
activate only the Phase 2 independent-candidate boundary after a separate
handoff. Phase 4 soft CPU priority remains last and deferred.


## Hybrid optimization Phase 3 complete locally

Updated: 2026-08-16. Deterministic-lookahead Kernel controllers now own one
two-worker `spawn` process pool for their complete finite lifetime. The same
executor handles independent candidate branches for every sequential focal
flow and persists across completed slots. Tasks receive current loads, beliefs,
admission, links, parameters, and canonical candidate identity explicitly;
workers do not inherit HTTP clients or retain controller state. Dependent
future-flow projection, real commits, traffic, telemetry, learning, and metrics
remain sequential.

Controller closure waits for both workers, cancels pending work, then closes
the persistent flow-generator and Kubernetes clients. Worker failures propagate
without traffic or serial fallback. Lookahead evidence now distinguishes the
new two-child controller-lifetime lifecycle from historical zero-worker
records; manual MC retains its separate per-slot pool and zero lookahead-worker
contract. Direct pure policy and slot calls remain serial by default, and no
lookahead worker CLI flag was added.

Four dedicated Phase 3 tests and a 76-test focused lifecycle/evidence group
pass. Full verification passes all 325 Hybrid tests and the recorded 188
relevant frozen Exact regressions. Changed Python compiles, seven Hybrid
overlays render offline, and `git diff --check` passes. No live cluster or
Docker operation, Job, traffic, repository trace, or CSV mutation occurred,
and no speed improvement is claimed.

The next gate requires explicit approval because it would build/load the
changed controller image and run a finite live lookahead Job. It should verify
two stable child PIDs across slots, zero after controller exit, unchanged
Pure/Kernel results and serving behavior, and wall-time evidence. Phase 4 soft
CPU priority remains unimplemented and should proceed only if that live result
shows remaining controller CPU contention.


## Hybrid optimization Phase 3 live gate complete

Updated: 2026-08-16. The approved live gate rebuilt and loaded only
`ibg-hybrid-testbed:kernel-controller-v1`; the service image was not rebuilt.
The existing `ibg-hybrid` cluster was not recreated. At the user's approved
15-flow/8-replica size, each StatefulSet now has eight Ready worker-only Pods.
The bounded scale-down removed ordinals 8--14 and preserved every retained
ordinal 0--7 UID/restart count plus the flow-generator UID and zero restarts.

`ibg-hybrid-controller-dynamic` completed three explicit-lookahead slots on the
worker with root seed 2050 and profile seed 50. All slots contain
`lookahead_process_workers=2`, lifecycle
`ibg-hybrid-controller-lookahead-pool-v1`,
`active_child_processes_after_slot=2`, Pure/Kernel replay parity, belief-chain
continuity, complete placement before one request, 30 observations, and 15
measured pairs. Worker PIDs 22 and 25 persisted across the run. The controller
Pod exited 0; no active controller container remained. The remaining 48 spawn
workers exactly match two unchanged Uvicorn workers in each of 24 public
forwarders.

Slot times were 10.150, 7.545, and 8.546 seconds; the Pod runtime was about 58
seconds and the Job duration was 61 seconds. No matched serial baseline exists,
so this is not speedup evidence. Trace:
`runs/ibg-hybrid-experiment-20260816T105745.330728Z.jsonl`. Post-gate
compilation, seven offline Kustomize renders, and `git diff --check` pass. No
code correction, Exact edit, service-image or retained-Pod template rollout,
CPU-resource change, multi-host, cross-worker, NIC, line-rate, or exclusive-CPU
validation occurred. Phase 4 is still unimplemented and not authorized.


## Hybrid optimization Phase 4 complete locally

Updated: 2026-08-21. Every retained finite Hybrid controller Job now requests
one CPU with the existing two-CPU limit. Controller memory remains 256 MiB
requested and 1 GiB limited. The finite-controller worker preflight now adds
1000 millicpus, preserves existing Pod-request arithmetic, accepts exact-fit
capacity, and rejects CPU or memory shortages before mutation against the
worker's reported allocatable envelope.

The one-CPU request is soft shared Kubernetes scheduling/accounting, not an
exclusive CPU, pin, cpuset, extra core, extra worker, or topology change.
Unused CPU remains usable by replicas and the flow generator. Deterministic
lookahead and manual-MC templates agree, and Phase 1 HTTP lifecycles, Phase 3
pool semantics, service resources, worker-only placement, algorithm behavior,
and all experiment metrics remain unchanged.

Focused Phase 4/Phase 3 verification passes 15 tests. All 331 Hybrid tests and
188 relevant frozen Exact regressions pass; changed Python compiles, all seven
offline Kustomize renders succeed, and `git diff --check` passes. No cluster,
node, image, Job, Pod, workload, or traffic mutation occurred. No runtime
improvement is claimed. The next action is read-only live inspection and an
exact-command proposal for a separately approved matched 100m-versus-1-CPU
A/B; it must preserve the controller image/code, serving Pod identities,
topology, seeds, first slot, flow order, iteration count, and two-CPU limit.


## Phase 4 live A/B read-only preflight

Inspected: 2026-08-21. The dedicated `ibg-hybrid` kind cluster remains
registered, but both node containers are stopped: the worker exited with code
130 and the control-plane exited with code 137. Both retain Docker restart
policy `on-failure` and the pinned kind node image identity. As expected while
the control-plane is stopped, the Kubernetes API refused read-only node and
workload queries, so current Pod UIDs, restart counts, replica count, Jobs, and
controller image identity could not be refreshed.

No node was started and no cluster, image, Job, Pod, workload, or traffic state
was changed. A valid A/B therefore requires separate approval first to start
only the two retained kind node containers, wait for both nodes, and repeat the
read-only inventory. The experiment commands must remain separately gated
after that inventory confirms no controller Job and stable serving identities.


## Hybrid end-to-end SLA plan recorded

Updated: 2026-08-21. The user authorized changing the current Hybrid SLA count
from selected physical-only latency to raw end-to-end latency while retaining
the strict 80-ms threshold. The active field will be
`end_to_end_sla_violations`; raw end-to-end remains selected physical
processing plus measured pair latency. Realized utility, reference utility,
placement, learning, beliefs, jitter, and telemetry remain unchanged.
The active count CSV will be `end_to_end_sla_violations.csv`; historical
`sla_violations.csv` files will not receive mixed-semantics columns.

The requested quality/severity metric is recorded but deliberately deferred.
A later separately authorized change may add `end_to_end_sla_excess_ms` as the
per-completed-timeslot sum of positive raw end-to-end excess above 80 ms and a
separate CSV. No quality metric or quality CSV is part of the current step.


## Hybrid end-to-end SLA count complete locally

Updated: 2026-08-21. The active Hybrid count is now
`end_to_end_sla_violations`, computed from selected physical processing plus
measured pair latency for every flow, with a strict greater-than-80-ms rule.
Exactly 80 ms is not a violation. Physical-only realized utility, raw end-to-
end reference utility, placement, learning, beliefs, jitter, traffic, and pair
measurement are unchanged.

New traces use `ibg-hybrid-experiment-jsonl-v2`; persistence rejects malformed
raw coverage, incorrect counts, threshold drift, and the retired physical-only
field. Console output is explicitly end-to-end. `--csv 1` writes the count to
`figures/IBG_hybrid/end_to_end_sla_violations.csv`; it does not create or
modify historical `sla_violations.csv` and rejects legacy physical-only trace
input.

Focused verification passes 65 tests. All 334 Hybrid tests and 188 relevant
frozen Exact regressions pass; changed Python compiles, CLI help succeeds,
seven offline overlays render, and `git diff --check` passes. No live resource,
image, traffic, trace, or CSV was touched. A live run requires a normal
controller-image build because runner/contract code changed. The accumulated
quality metric `end_to_end_sla_excess_ms` and its CSV remain unimplemented and
await separate explicit authorization.


## Hybrid end-to-end SLA excess complete locally

Updated: 2026-08-21. The authorized quality metric is implemented as
`end_to_end_sla_excess_ms`: one per-completed-timeslot sum of unrounded positive
raw end-to-end latency differences above 80 ms. Both it and the unchanged
strict `end_to_end_sla_violations` count are derived from the same recorded raw
per-flow map. Exactly 80 ms contributes neither count nor excess.

The value flows through `HybridSlotMetrics`, complete Pure/Kernel replay,
completed Kernel metrics evidence, and explicitly labelled console output.
Active persistence is `ibg-hybrid-experiment-jsonl-v3` and rejects invalid or
inconsistent count/excess evidence. `--csv 1` adds
`figures/IBG_hybrid/end_to_end_sla_excess_ms.csv` in the existing wide atomic
format; disabled CSV operation creates no quality file. Historical v1/v2
traces, `sla_violations.csv`, and `results.csv` remain untouched.

Focused verification passes 81 tests. All 350 collected Hybrid tests pass in
memory-bounded groups, and all 188 relevant frozen Exact regressions pass.
Changed Python compiles, launcher help/import checks pass, seven offline Hybrid
overlays render, and `git diff --check` passes. The 80-ms threshold, violation
count semantics, utility, learning, placement, beliefs, telemetry, resources,
and runtime architecture are unchanged. No live resource, image, workload,
traffic, trace, or CSV was mutated. The next live run requires a normal
controller-image build before that rebuilt image can later be reused with
`--skip-build`.


## Hybrid tc/netem complete locally

Updated: 2026-08-22. The opt-in `ibg-hybrid-netem-v1` feature is implemented
and locally verified. `--netem` defaults to zero; enabled runs accept strict
finite delay/jitter values and dynamically add a non-privileged, `NET_ADMIN`-
only init container to all replica StatefulSets. Its qdisc affects only each
replica Pod's `eth0` egress. Disabled templates contain no impairment fields.
The launcher detects enabled/disabled/value drift, requires a deliberate
replica rollout, preserves the flow generator, propagates one configuration
through `--runs`, and records matching explicit provenance on every host-side
lifecycle event without changing the v3 metrics contract.

Focused verification passes 94 tests. All 372 Hybrid tests pass in three
memory-bounded groups (153, 123, and 96), and all 188 established frozen Exact
regressions pass (84 and 104). Changed Python compiles, launcher help/import
checks pass, all seven offline overlays render, and `git diff --check` passes.

No image build/load, Docker or kind startup, Kubernetes command, Job, Pod,
traffic run, or live experiment occurred. Therefore no live robustness claim
is recorded. The next action belongs to the user: first build the new
Hybrid-owned netem image in a normal enabled run, then execute matched disabled
and enabled runs with identical dimensions and seeds. Netem may legitimately
raise measured pair latency and the dependent raw end-to-end SLA/reference
metrics; it does not change physical jitter, observation noise, policy,
learning, beliefs, placement, or physical-only utility.


## Hybrid equilibrium threshold set to 0.04

Updated: 2026-08-22. The active Hybrid runner now declares equilibrium only
when every belief entry changes by strictly less than `0.04` between completed
timeslots. Exactly `0.04` remains non-equilibrium. This supersedes the prior
Hybrid `<0.033` threshold and affects stopping time only. No live cluster,
image, workload, Job, Pod, or traffic mutation occurred.


## Hybrid phase wall-time footprint complete locally

Updated: 2026-08-22. `--csv 1` now records monotonic wall time for Ready-Pod
discovery, admission/planning through route dispatch, the separate
flow-generator/data-plane wait, and feedback through completed-slot validation.
Active control time is the exact admission-plus-feedback sum. The footprint is
versioned `ibg-hybrid-control-plane-wall-time-v2`; enclosing traces remain v3,
and five timing CSVs are written under `figures/IBG_hybrid/footprint/` beside
the unchanged payload/message reports.

The instrumentation contains no CPU, child-process CPU, cgroup, memory, NIC,
or wire measurement and therefore identifies phase dominance rather than CPU
saturation. It remains outside `HybridSlotMetrics` and changes no algorithm,
placement, learning, utility/SLA, telemetry, resources, process pool, or
scheduling behavior.

Focused verification passes 81 tests. All 376 Hybrid tests pass in bounded
groups (147, 103, and 126), all 188 frozen Exact regressions pass, changed
Python compiles, launcher/summary checks pass, seven offline overlays render,
and `git diff --check` passes. No live or generated state was mutated. The next
action is a user-run five-slot current-configuration baseline after a normal
controller-image rebuild; the future CPU/pool candidate remains unimplemented
until that baseline is captured.


## Hybrid four-process CPU candidate ready for user gate

Updated: 2026-08-22. The local candidate now uses four persistent deterministic-
lookahead child processes, a two-CPU controller request, and a four-CPU limit.
Manual MC remains capped at two workers. Controller memory, serving resources,
topology, placement and learning semantics, policy parameters, telemetry, and
wall-time instrumentation are unchanged. Resource preflight accounts for the
new 2000m request.

The reference trace is
`runs/ibg-hybrid-experiment-20260822T122453.268408Z.jsonl`: five completed
20x3x10 lookahead slots, netem disabled, Pure/Kernel parity true, two persistent
workers, mean total slot time 15.49 seconds, mean admission 15.32 seconds, mean
data-plane wait 177 ms, and mean feedback 14 ms. It did not equilibrate within
the deliberate five-slot cap. This is baseline evidence, not a speed claim.

Focused candidate verification passes 80 tests; all 376 Hybrid tests and 188
frozen Exact regressions pass. Compilation, launcher checks, seven offline
renders, and `git diff --check` pass. No live mutation occurred. The next action
is a user-run candidate after rebuilding/loading only the controller image,
then comparing its five timing rows and serving health against the baseline.


## Hybrid ordinary parity replay is now optional locally

Updated: 2026-08-22. Ordinary production experiments now default to
`--parity-replay 0`. They execute the real four-process Kernel scheduling,
traffic, telemetry, belief update, metrics, and persistence once, then proceed
to the next timeslot without repeating the full scheduling calculation through
the serial parity oracle. `--parity-replay 1` explicitly restores that oracle
and fails the run if it does not match.

Disabled evidence records `pure_kernel_replay_performed=false` and omits a
parity value; enabled evidence records performed/true. Trace persistence and
all lifecycle events enforce the selected mode. The active metrics schema
remains v3, and the `run-small` correctness gate still mandates replay.

Focused verification passes 63 tests; all 383 Hybrid tests and 188 frozen
Exact regressions pass. Compilation, launcher help/import checks, seven
offline renders, and `git diff --check` pass. No live or generated state was
mutated. A normal controller-image rebuild is required before using the option
in the cluster; no live runtime reduction is claimed by this local result.


## Hybrid netem image is now available on both nodes

Updated: 2026-08-22. The failed user run stopped before traffic because
`ibg-hybrid-testbed:netem-v1` did not exist. The deeper cause was repaired: the
offline netem Dockerfile no longer requires the absent historical
`ibg-testbed:kernel-phase3` tag. It extracts the required tc/netem userspace
files from the existing pinned kind node image into a 3.28-MB scratch image.

The corrected image built offline, executed the requested 7-ms delay/3-ms
normal-jitter command successfully in a disposable container, and is present
on both `ibg-hybrid-worker` and `ibg-hybrid-control-plane`. All 60 replica Pods
and the flow generator were observed Running afterward. The existing
controller Job/Pod is completed, not active. No experiment was rerun and no
manifest or workload rollout was initiated by this work; the next experiment
command remains user-owned.

## MILP 40x3x20 ConfigMap annotation-limit repair

Updated: 2026-08-23. The user-run 40-flow/3-stage/20-replica synthetic-scale
MILP launch built and loaded its images, created `kind-ibg`, and applied the
namespace/RBAC/flow generator, but stopped before replica rollout because
client-side `kubectl apply` attempted to persist the large generated profile
again in `kubectl.kubernetes.io/last-applied-configuration`. Kubernetes
rejected that annotation above its 262144-byte limit.

The launcher now uses server-side apply with the stable
`milp-kernel-launcher` field manager for that ConfigMap only. The exact
40x3x20/profile-seed-50 ConfigMap succeeds in Kubernetes server-side dry-run.
All 51 `tests/test_milp_phase5.py` tests pass, including focused ordinary and
large synthetic-profile launcher coverage; changed Python compiles. No retry,
replica rollout, controller Job, traffic, trace, or solver invocation was
started after the correction. The next action is user-owned rerun of the same
command.

### MILP 40x3x20 controller OOM resource repair

Updated: 2026-08-23. The corrected user-run launcher created all 60 replica
Pods and the controller Job, but the solver Pod was OOM-killed after 3m51s at
the prior 1-GiB memory limit; no traffic or result followed. Each current kind
worker advertises about 31.3 GiB allocatable memory, with the 60 serving Pods
requesting about 5.6 GiB per worker. The controller Job now requests 8 GiB and
limits at 16 GiB; its CPU remains 100m request/2-core limit and serving
resources are unchanged.

All 51 `tests/test_milp_phase5.py` tests pass and changed Python compiles. A
Kubernetes server-side dry-run accepts the revised 40x3x20 controller Job. No
retry, controller Job, traffic, trace, or additional live resource mutation
was started by this correction; the existing 60 serving Pods were preserved.

### MILP 20-to-5 replica scale-down validation repair

Updated: 2026-08-23. The user-requested 10-flow/3-stage/5-replica synthetic
run failed before mutation because the launcher compared profiles for all 20
existing replica ordinals. The 6--20 profiles are intentionally removed by
the requested scale-down and must not block it. The launcher now validates
only retained ordinals through `min(existing, requested)` while preserving
drift rejection for every retained Pod and all scale-up behavior.

All 52 `tests/test_milp_phase5.py` tests pass and changed Python compiles. A
read-only validation against the actual current 20-replica/profile-seed-50
deployment accepts the target 5-replica profile. No retry, Pod, Job, traffic,
trace, or other live mutation was started by the repair; the next action is
user-owned rerun of the same 10x3x5 command.

### MILP synthetic planning-link v2 range update

Updated: 2026-08-23. At user direction, new synthetic-scale profiles now use
`milp-scale-synthetic-profile-v2`: each deterministic directed planning-link
coefficient lies in 65.000--74.999 ms. The prior v1 0.500--5.499-ms generator
remains supported for historical reproduction. This is a planner-objective
coefficient change only, not a netem setting or real traffic-delay injection.

The current 10x3x5/profile-seed-50 v2 profile has 75 links in the observed
65.034--74.934-ms range and fingerprint
`437f27a1c8765d01d7de01bc17c95247`. The focused Phase 4/5 MILP suite passes
66 tests and changed Python compiles. No live profile update, Pod, Job,
traffic, trace, or other live mutation was started by this change.

## Greedy final-baseline plan recorded

Updated: 2026-08-24. Planning and Phase 0 contract characterization are
complete; policy/runtime implementation has not started.

The requested final baseline will live under `Greedy/` and use a pure budgeted
`L=2` myopic policy. For each sequential flow, enumerate feasible actions that
select one Ready replica from each of exactly two distinct configured stages,
score the action by the sum of its two immediate belief-driven expected stage
utilities at projected load, commit both loads, and bypass the remaining `K-2`
stages. The lowest canonical `(stage, replica)` action wins an exact tie. There
is no future-flow simulation, pruning, lookahead, Monte Carlo, bandit, MILP, or
planning-link selection term. The no-rejection contract chooses the greatest
feasible action even when every score is non-positive.

The current untracked `Greedy/` folder is legacy material, not a working
container baseline. Its driver executes at import time and contains a retired
`range(1,30)` loop around hard-coded 50-flow, 3-stage, 80-replica-per-stage
(240 total) executions. That 29-execution behavior is characterization only
and does not belong to the new baseline. The driver enables the budgeted
two-stage branch by default,
uses historical model/SLA/equilibrium/CSV behavior, and has no Kubernetes,
dynamic topology, JSONL, or launcher contract. The dormant per-stage path can
return replica zero, while its embedding logic mutates the last replica load
for that sentinel. No legacy experiment was run and no generated file was
rewritten during this planning task.

The recorded target uses a dedicated `greedy` kind cluster,
`kind-greedy` context, `greedy-testbed` namespace, and one control-plane plus
one worker with all workloads worker-only. Every run requires explicit positive
flow, stage, and per-stage replica dimensions with `K>=2`; there are no
topology defaults. The explicit 10-flow/3-stage/5-replica shape is only the
canonical matched-comparison input. It plans safe stage/replica scale-up and
scale-down. Each launcher
invocation creates exactly one experiment/controller run, with no `--runs`
option or internal repetition. Required production controls are `--rollout-batch-size`,
`--profile-seed`, `--max-iterations`, `--csv`, and `--skip-build`, with the
same narrow no-build meaning and fail-closed lifecycle as Hybrid.

Console blocks, rollout progress, host-side lifecycle JSONL, and opt-in
wide-layout CSVs will mirror current Hybrid structure with Greedy ownership and
policy provenance. Active compatible semantics are separated jitter and exact
likelihood, selected-only learning, physical-only realized utility, measured
pair/raw reference metrics, strict raw-end-to-end SLA above 80 ms plus excess,
Jain fairness, and strict `<0.04` equilibrium. JSONL will be mandatory after a
successful run; `--csv 1` will export under `figures/Greedy/`.

`ROADMAP.md` now contains Phases 0--9: contract/legacy characterization, pure
policy, stateful simulation, Kernel adapters, isolated images/manifests,
persistent dynamic topology, console/JSONL/CSV, complete local verification, a
separately authorized small live gate, and separately authorized scaling/final
acceptance. The next action, only after the user asks to continue implementation,
is Greedy Phase 1. No Docker build, kind/Kubernetes command, cluster deletion,
namespace/resource mutation, Pod rollout, controller Job, traffic, trace, CSV,
test execution, commit, or push occurred in this planning turn.

### Greedy optimization review incorporated

Updated: 2026-08-24. The Greedy roadmap now includes the applicable execution
and deployment optimizations found in the Hybrid implementation, not merely its
container layout. Each Phase 0--9 now begins with a targeted preparation step
to inspect the current handoff and the phase-related documentation, source,
scripts, and focused tests when such material exists, then record what is
reused, adapted, or excluded before implementation.

Accepted Greedy measures are immutable per-stage identity and canonical `L=2`
action-order precomputation,
finite-lifetime deterministic expected-utility memoization, persistent
controller discovery/flow-generator HTTP clients, one flow-generator-lifespan
async route pool, the accepted separate forwarder local/downstream clients,
concurrent execution of already-selected routes, change-scoped image work,
equal-topology no-op reconciliation, bounded Ready-gated rollout, and narrow
`--skip-build` reuse. Placement/load updates remain sequential.

The planned production CLI now also contains `--parity-replay {0,1}`, default
zero. Local correctness and the small live gate force replay on; ordinary runs
avoid the duplicate serial calculation, and JSONL records whether it was
requested and performed. `--csv 1` additionally exports monotonic discovery,
admission/placement, data-plane-wait, feedback/validation, and total timing plus
compatible controller payload/message footprint.

Hybrid's focal-candidate worker tasks and persistent lookahead process pool were
studied and explicitly excluded. Pure Greedy has no independent candidate tree,
while parallel real-flow decisions would change load-dependent choices. The
earlier separately conservative Greedy controller profile is superseded: the
comparison baseline uses Hybrid's active request `2 CPU/256Mi` and limit
`4 CPU/1Gi`, while Greedy remains one sequential policy process. One-sided
resource tuning is forbidden; alternatives require a versioned matched A/B.

That earlier optimization refinement changed only the four handoff Markdown
files. At that point Phase 0 was still next; Phase 0 is now complete under the
later corrected budgeted `L=2` contract. No image, manifest, cluster,
namespace, Pod, Job, traffic, trace, CSV, or generated result was created by
the planning refinement.

### Greedy per-phase intelligence guidance recorded

Updated: 2026-08-24. Every Greedy Phase 0--9 records a user-facing recommended
Codex reasoning-effort level and a phase-specific rationale. The repository
does not freeze a model ID. These are personal selection suggestions for the
user, not checks or requirements for the implementing agent.

The allocation is `high` for Phase 0 contract characterization, Phase 4
images/manifests, Phase 6 evidence/reporting, and the separately authorized
Phase 8 small live gate. It is `xhigh` for Phase 1 policy mathematics, Phase 2
stateful learning/metrics, Phase 3 concurrent Kernel lifecycles, Phase 5 dynamic
topology safety, Phase 7 complete regression synthesis, and Phase 9 scale/final
evidence. The user may prefer `xhigh` for Phase 8 if read-only preflight reveals
drift or requires command redesign.

The agent does not inspect, verify, enforce, or change the user's selected
model or reasoning level, and the user may disregard or change any suggestion
without explanation. The recommendations do not authorize implementation,
live Kubernetes operations, destructive actions, phase advancement, or reduced
testing. Phase preparation, focused checks, explicit live approval, and handoff
updates remain unchanged. No code, test, image, manifest, cluster, workload,
traffic, or generated result was changed by this documentation update.

## Greedy Phase 0 complete locally

Updated: 2026-08-24. The baseline contract and legacy characterization gate is
complete. Phase 1 has not started.

Superseding user correction: the intended baseline is not full-chain
per-stage Greedy. It is pure Greedy over a budgeted Hybrid-shaped `L=2` action:
exactly two distinct selected stages per flow and `K-2` bypasses. Phase 0 was
updated in place; no Phase 1 policy code was implemented.

Latest configuration correction: every future invocation must receive
`--flow`, `--stage`, and `--replica` explicitly; no topology dimensions have
runtime defaults. The 10-flow/3-stage/5-replica shape is only the explicitly
supplied canonical matched-comparison configuration. Each invocation performs
exactly one run, the new Greedy interface will not expose a `--runs` option,
and legacy `range(1,30)` remains only retired characterization evidence.

Added only three Greedy Phase 0 files:

- `Greedy/phase0_contract.py` freezes `pure-greedy-budgeted-l2-v1` through
  small executable fixtures for positive `N`, `M`, and `K>=2`, exactly two
  selected stages, `K-2` bypasses, `ceil(N/M)` admission, projected loads,
  sequential joint-action mutations, canonical action ties, best non-positive
  selection, empty-feasible failure, selected observations/pairs, public policy
  inputs, excluded algorithms, and active metric/learning constants.
  It separately freezes 10x3x5 as a canonical comparison fixture rather than
  a default, plus the one-run/no-`--runs` invocation contract, while retaining
  the intentionally tiny hand-checked slot fixture.
- `Greedy/legacy_characterization.py` parses legacy source syntax without
  importing it and contains the complete callable disposition registry.
- `tests/test_greedy_phase0.py` provides bounded characterization and active
  compatibility tests. It never imports `Greedy/main.py` and checks clean
  Phase 0 imports in a temporary directory with no output or file creation.

Observed legacy facts are now executable evidence rather than planning notes:

- `main.py` has a retired top-level `range(1,30)` experiment, 50 flows, three
  stages, 80 replicas per stage (240 total), and `is_budgeted=1`; `test.py`
  also performs import-time CSV read/repair/write, while `header.py` changes
  the recursion limit on import.
- The active budgeted helper returns exactly two selected stages from
  stochastic 30-sample Pandas grids. Its separate link helper is not used in
  that choice. The dormant per-stage helper returns replica `0` when every
  utility is non-positive, and legacy embedding then increments the last load
  entry through index `-1`.
- Randomness mixes module-global Python `random`, NumPy random calls, in-place
  shuffling, and UUIDs, with no explicit seed call across the audited files.
- Historical behavior uses `100/(q*(1+gamma*n))-5`, a non-convolved signal
  likelihood, state-based SLA paths plus a 15-ms latency-excess metric, strict
  belief changes below `0.06`, direct working-directory wide CSV mutation, and
  a script that fabricates missing SLA rows by regression.
- All 38 top-level callables/methods are classified: 5 active behaviors may be
  reused through shared code with compatibility tests, 14 remain reference,
  and 19 retire. The Greedy/Hybrid matrix has 4 direct-reuse, 5 Greedy-adapter,
  and 2 exclusion rows.

Verification completed:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/pytest -q
  tests/test_greedy_phase0.py`: 13 passed.
- The corrected compatibility selection used `tests/test_latency_model.py`,
  four focused Hybrid Phase 1 `L=2` action/bypass tests, two Phase 2
  belief/tie tests, and three Phase 5 observation/SLA/learning tests: 17 passed.
- `Greedy/phase0_contract.py`, `Greedy/legacy_characterization.py`, and
  `tests/test_greedy_phase0.py` compile with the project virtual environment;
  `git diff --check` passes.
- A first bare `pytest` attempt found no command on PATH; a first selected
  compatibility invocation without `PYTHONPATH=.` could not collect `IBG`
  package imports. A later compatibility command named two nonexistent Hybrid
  test node IDs and collected no tests. These command-selection issues were
  corrected without source changes; the intended commands above passed.

No legacy Greedy experiment, CSV/result generation, Docker/image operation,
kind/Kubernetes command, traffic, cluster mutation, or live validation ran.
Frozen `IBG/`, `IBG_Hybrid/`, MILP, Kubernetes, generated evidence, and
unrelated worktree files were not modified. The next action is Greedy Phase 1
only after a separate user request.

### Greedy/Hybrid matched-comparison plan corrected

Updated: 2026-08-24. The four Greedy handoffs now define
`greedy-hybrid-matched-comparison-v1`. Fair comparison means identical inputs,
infrastructure opportunity, runtime conditions, and measurement boundaries;
only policy logic is intentionally different.

The plan now requires the same explicitly supplied 10x3x5/L2 comparison shape,
capacity and Ready semantics, one Job/run, maximum iterations, exact
materialized hidden-state/observation-
seed map, root and flow-order seeds, deterministic keyed physical/observation
input schedule, worker placement, rollout/build/warm state, HTTP lifecycles,
instrumentation, and timing boundaries. Exact map equality and fingerprints
are required; matching `--profile-seed` spelling alone is insufficient.

Current active Hybrid settings recorded for the comparison profile are:

- private processor request `50m/128Mi`, limit `1 CPU/768Mi`, one worker;
- public forwarder request `25m/128Mi`, limit `1 CPU/256Mi`, two workers,
  ports 8080/8081 and 30-second downstream/server keep-alive;
- flow generator request `50m/128Mi`, limit `1 CPU/768Mi`;
- controller request `2 CPU/256Mi`, limit `4 CPU/1Gi`.

Every later phase preparation must reread the current relevant
`IBG_Hybrid/` code, `deploy/hybrid-kubernetes/` manifests,
`scripts/run_hybrid_kernel_phase4.py`, and smallest focused tests, then refresh
the phase rows of the comparison matrix before Greedy changes. Source drift
fails preparation until reviewed and versioned. This prevents stale handoff
values from silently defining the implementation.

Greedy still excludes Hybrid pruning, activation, planning-link selection,
lookahead, Monte Carlo, candidate/depth flags, `--policy`, `--mc-workers`, and
process pools. Actual CPU time, RSS, throttling, and wall time under the common
resource ceiling are outputs to compare. No policy, manifest, launcher,
container, cluster, trace, or CSV was changed by this documentation correction;
Phase 1 remains next and unstarted.

## Greedy Phase 1 complete locally

Updated: 2026-08-24. The import-safe pure policy core and typed-contract gate
are complete. Phase 2 has not started.

Added `Greedy/__init__.py`, `Greedy/contracts.py`,
`Greedy/expected_utility.py`, `Greedy/policy.py`, `Greedy/comparison.py`, and
`tests/test_greedy_phase1.py`; corrected the Phase 0 fixture/test and all four
handoffs so 10x3x5 is never described as a runtime default. Typed configuration
now requires explicit positive `N`, `K`, and `M`, with `K>=2` and fixed `L=2`.
The only 10x3x5 object is explicitly named as the canonical matched-comparison
fixture.

The policy owns immutable public contracts, precomputes contiguous identities
and globally lexicographic complete L=2 actions once, and processes the exact
supplied flow order sequentially. It evaluates public-belief stage utility at
`current_load+1`, examines every Ready/capacity-feasible action, keeps the
strict first canonical action on a tie, commits both loads, selects the best
non-positive action, and raises `NoFeasibleActionError` only for an empty
complete feasible set. It returns `N` complete actions, each action's `K-2`
bypasses, decision states, and final loads without caller-input mutation.

The Greedy utility adapter directly uses policy-neutral
`IBG.latency_model.expected_state_utility`; it does not import a Hybrid policy
namespace. A controller-lifetime exact-key `(belief tuple, projected load)`
LRU is bounded to 4096 entries by default and can be cleared. Cached,
uncached, repeated, and transparent exhaustive-reference results agree. The
policy consumes no Python or NumPy global RNG and exposes no hidden state,
profile/observation/physical seed, pair-latency, or planning-link input.

Phase 1 revalidated the comparison rows at HEAD
`19229c274038db440f3cfdd62ed2102ea4c2c545`. Current Hybrid sources still show
`ceil(N/M)` at `IBG_Hybrid/kernel_profile_expansion.py:587-600`, public
Ready/projected-capacity checks at `IBG_Hybrid/phase0_contract.py:252-289`,
deterministic belief utility at `IBG_Hybrid/expected_utility.py:12-42`, and
identity/action/cache/tie patterns at `IBG_Hybrid/contracts.py:17-171` and
`IBG_Hybrid/policy.py:1240-1555`. The active manifests still show private
processor `50m/128Mi` request and `1 CPU/768Mi` limit, public forwarder
`25m/128Mi` and `1 CPU/256Mi`, flow generator `50m/128Mi` and
`1 CPU/768Mi`, controller `2 CPU/256Mi` and `4 CPU/1Gi`, one private worker,
two public workers, ports 8081/8080, and 30-second downstream/server keep-alive.
No relevant recorded value drifted. Hybrid pruning, activation, pair-aware
selection, lookahead, Monte Carlo, policy/worker CLI, and process pools were
explicitly excluded.

Verification completed:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/pytest -q
  tests/test_greedy_phase0.py tests/test_greedy_phase1.py`: 34 passed.
- The selected unchanged compatibility command ran all eight
  `tests/test_latency_model.py` cases, four Hybrid Phase 1 action/ordering
  cases, two Hybrid Phase 2 belief/tie cases, and three Hybrid Phase 5
  jitter/SLA/learning cases: 17 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/pytest -q
  tests/test_ibg_hybrid_phase0.py::test_feasibility_uses_ready_and_declared_flow_capacity_only`:
  1 passed.
- The isolated Phase 1 silent-import/no-file test passed in a clean temporary
  directory.
- The changed/new Greedy Python and focused test files compiled with the
  project virtual environment, and `git diff --check` passed.

No unsafe legacy driver import, Phase 2 loop, controller/service adapter,
container/image, Kubernetes resource, launcher, experiment JSONL/CSV, Docker,
kind, kubectl, cluster mutation, traffic, commit, or push occurred. Frozen
`IBG/`, `IBG_Hybrid/`, MILP, deployments, generated evidence, and unrelated
worktree changes were preserved. The next action is Greedy Phase 2 only after
a separate user request.

## Greedy Phase 2 complete locally

Updated: 2026-08-25. The stateful pure-Python slot and one-experiment gate is
complete. Phase 3 has not started.

Added `Greedy/slot_contracts.py`, `Greedy/simulation.py`,
`Greedy/learning.py`, `Greedy/metrics.py`, `Greedy/runner.py`,
`Greedy/oracle.py`, and `tests/test_greedy_phase2.py`. Updated only the typed
Phase 2 source locations in `Greedy/comparison.py` plus the four required
handoffs. No frozen source, runtime resource, deployment, generated evidence,
or unrelated worktree file was changed.

One pure slot now:

- accepts an explicit flow order or derives the exact active Hybrid
  `blake2b-hybrid-flow-order-v1` order with a local RNG;
- calls the Phase 1 exhaustive immediate policy once and preserves its `N`
  sequential decisions and final loads;
- creates and validates exactly `2*N` selected observations and `N` measured
  selected-pair records, with `K-2` bypasses per flow;
- conditions selected samples and predictions on final assigned load;
- separates physical and observation streams and uses the exact convolved
  likelihood;
- updates only selected replicas with the frozen posterior/`0.8` retention
  rule and retains the learned snapshot for the next slot;
- records predicted, physical-only realized, processing, measured-pair, raw
  end-to-end/reference, strict 80-ms SLA count/unrounded excess, Jain,
  maximum-belief-change, strict `<0.04` equilibrium, placement timing, and
  feedback/validation timing; and
- performs no print, log, JSONL, CSV, HTTP, container, or Kubernetes action.

The deterministic physical/observation key includes experiment, slot, flow,
stage, replica, final load, and component. Canonical experiment ID 1 matches
the current Hybrid component seed payload exactly; noncanonical pure fixture
IDs receive an explicit namespace. `profile_seed` is excluded from order,
policy, and component draws. Environment identity comes from the complete
materialized hidden-state/observation-seed map and its fingerprint.

`run_greedy_experiment` executes exactly one experiment per call, retains one
policy/cache and evolving beliefs across slots, exits early on equilibrium, or
completes exactly the explicit positive `max_iterations`. The explicit oracle
replays captured results without stochastic redraw and checks an independent
serial immediate-policy enumeration. Normal slots do not invoke it and do not
double-solve.

Phase 2 revalidated active comparison behavior at HEAD
`19229c274038db440f3cfdd62ed2102ea4c2c545`. No mathematical or canonical
one-experiment seed value drifted. Active Hybrid's component seed source has no
separate experiment field; Greedy preserves its exact bytes for canonical
experiment 1 and versions only the noncanonical pure-fixture extension. Exact
source locations and blobs plus reuse/adapt/exclude classifications are in
`ARCHITECTURE.md`.

Verification completed:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/pytest -q
  tests/test_greedy_phase0.py tests/test_greedy_phase1.py
  tests/test_greedy_phase2.py`: 58 passed.
- The focused unchanged compatibility command ran all eight latency-model
  tests, two Hybrid Phase 0 Ready/seed cases, three Phase 1 action/oracle cases,
  three Phase 2 tie/hidden-state/oracle cases, and eight Phase 5
  order/observation/jitter/SLA/learning/fairness/continuity/failure cases:
  24 passed.
- All changed/new Greedy Python files compile with bytecode directed to `/tmp`.
- The isolated Phase 2 import test passes in a clean temporary directory with
  no stdout, stderr, or file creation.
- `git diff --check` passes.

Not verified and intentionally out of scope: Phase 3 Kernel adapters,
controller/services, HTTP traffic, images, manifests, launcher lifecycle,
JSONL/CSV, Docker/kind/kubectl, cluster state, live parity, scaling, and
performance. Existing unrelated dirty worktree changes were preserved. The
next action is Greedy Phase 3 only after a separate user request.

## Greedy Phase 3 complete locally

Updated: 2026-08-25. The Greedy-owned Kernel/HTTP adapter and finite-controller
gate is complete. Phase 4 has not started.

Added:

- `Greedy/kernel_contracts.py`
- `Greedy/kernel_kubernetes_discovery.py`
- `Greedy/kernel_route_contracts.py`
- `Greedy/kernel_route_execution.py`
- `Greedy/kernel_flow_generator.py`
- `Greedy/kernel_processor_service.py`
- `Greedy/kernel_route_forwarder.py`
- `Greedy/kernel_route_forwarder_service.py`
- `Greedy/kernel_controller_config.py`
- `Greedy/kernel_controller.py`
- `Greedy/kernel_controller_service.py`
- `Greedy/kernel_oracle.py`
- `tests/test_greedy_phase3.py`

Updated `Greedy/comparison.py` with the current Phase 3 matched timeout,
client-ownership, request-count, route-command, and telemetry rows plus exact
Hybrid/shared source audit records. No frozen `IBG/`, `IBG_Hybrid/`, MILP,
deployment, generated evidence, or unrelated variant was changed.

The implemented controller discovers exact public Running/Ready identity and
`ceil(N/M)` capacity coverage, performs the existing Greedy placement once,
and commits every sequential decision before traffic. It sends one complete
slot envelope to the flow generator; the generator sends `N` selected routes
concurrently, with one request per flow and two ordered already-selected hops.
Arbitrary `K>=2`, nonconsecutive selected stages, complete `K-2` bypasses,
final loads, route positions, next hops, and selected-pair telemetry are all
explicitly correlated. Any incomplete, duplicate, mismatched, or failed route
fails the slot before belief commit.

The finite controller retains one synchronous discovery client, one
synchronous controller-to-generator client, one policy/cache, and beliefs
across slots. The flow-generator lifespan retains one asynchronous
first-forwarder pool; direct tests alone have an ephemeral fallback. Public
forwarders retain separate local-processor and 30-second downstream clients.
All owners have idempotent exactly-once normal, partial-construction/start,
request/slot-failure, and shutdown cleanup coverage. The accepted 10-second
discovery, 30-second controller-to-generator, 10-second selected-route, ports
8081/8080, and 30-second downstream/server keep-alive values did not drift.

Selected-only learning and all Phase 2 metrics are unchanged. HTTP telemetry
cannot change completed selection; observation jitter remains learning-only;
physical latency remains the realized-utility input; measured pair latency
remains raw-reference/SLA-only; strict raw latency `>80.0` ms, unrounded
excess, Jain fairness, and strict `<0.04` equilibrium remain active. The
finite controller runs exactly one experiment and stops at equilibrium or the
explicit positive maximum. Injected monotonic timing covers discovery,
admission/placement, route dispatch, data-plane wait, feedback/validation, and
total slot duration.

Explicit Pure/Kernel replay consumes the captured public input,
observations, and pairs with no HTTP or stochastic redraw, and checks
placements, loads, beliefs, utilities, SLA, fairness, and equilibrium while
excluding timing/provenance. Ordinary execution does not import replay and
does not duplicate the solve.

Phase 3 audit facts:

- repository HEAD: `19229c274038db440f3cfdd62ed2102ea4c2c545`;
- no Phase 3 timeout, client, request/telemetry count, port, worker,
  keep-alive, or matched resource drift;
- exact source locations and blob IDs are recorded in `ARCHITECTURE.md` and
  `Greedy/comparison.py`;
- shared processor/forwarder behavior is reused; discovery, arbitrary-K
  schemas, lifecycle, controller, timing, and replay are adapted behind
  Greedy ownership; Hybrid policy/pool/output behavior is excluded.

Verification completed:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/pytest -q
  tests/test_greedy_phase0.py tests/test_greedy_phase1.py
  tests/test_greedy_phase2.py tests/test_greedy_phase3.py`: 102 passed.
- The focused unchanged compatibility command ran all eight latency-model
  tests plus selected Hybrid route, executor, discovery, lifecycle,
  controller-failure, and shared-forwarder cases: 32 passed.
- A clean temporary-directory import of all Phase 3 modules produced no
  stdout, stderr, or files.
- All changed/new Phase 3 Python files and the focused test compile with
  bytecode directed to `/tmp`.
- `git diff --check` passes.

Not verified and intentionally out of scope: images, manifests, namespace,
RBAC, ConfigMaps, controller Jobs, launcher lifecycle, JSONL/CSV, Docker,
kind, kubectl, cluster state, live traffic, live Pure/Kernel parity, scaling,
or performance. Existing unrelated dirty worktree changes were preserved. The
next action is Greedy Phase 4 only after a separate user request.

## Greedy Phase 4 complete locally

Updated: 2026-08-25. The isolated static image/Kubernetes gate is complete.
Phase 5 has not started.

Added:

- `Greedy/kernel_runtime_profiles.py`
- `Greedy/kernel_infrastructure.py`
- `scripts/render_greedy_kubernetes.py`
- `scripts/greedy_offline_wheelhouse.py`
- `deploy/greedy-kubernetes/` with two Dockerfiles, two direct requirement
  declarations, two exact wheel locks/manifests, lean package/report overlays,
  one-worker kind configuration, and an explicit canonical 10x3x5 input
- `tests/test_greedy_phase4.py`

Updated only the Greedy Phase 3 processor/config serialization boundary,
`Greedy/comparison.py`, `.dockerignore`, and the four required handoffs. Frozen
`IBG/`, `IBG_Hybrid/`, MILP, existing deployment resources, generated
evidence, and unrelated worktree changes were preserved.

The static renderer requires explicit dimensions and a complete contiguous
processor-private profile map. It generates the `greedy-testbed` namespace,
namespace-scoped Pod get/list RBAC, separate runtime/controller ConfigMaps,
one token-free flow-generator Deployment, and one two-container StatefulSet
plus headless Service for every explicit stage. All workloads are worker-only,
non-root, capability-dropped, read-only-root, and runtime-default-seccomp. Only
the finite controller Job gets a service-account token. The Job is outside the
long-running base and cannot be rendered without exact replica and
flow-generator readiness.

The Greedy service/controller images have separate offline CPython 3.12 Linux
AMD64 inputs and source inventories. The service image has no policy,
controller, oracle, Hybrid, MILP, or unsafe legacy Greedy source. The
controller includes the sequential policy/controller boundary but no service
entry points, Hybrid policy, lookahead, Monte Carlo, or process pool. Both run
as UID/GID 10001. No image was built.

Active Hybrid comparison values were revalidated at HEAD
`f2e0065204570d9631f26953c94729b451ff92b5`. No Phase 4 resource, probe,
worker, port, keep-alive, RBAC, topology, or image-boundary drift was found.
Exact locations and blobs are recorded in `ARCHITECTURE.md` and
`Greedy/comparison.py`; policy-neutral runtime constants are reused, static
ownership/rendering is adapted, and Hybrid policy/pool/launcher/output paths
are excluded.

Verification completed:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/pytest -q
  tests/test_greedy_phase0.py tests/test_greedy_phase1.py
  tests/test_greedy_phase2.py tests/test_greedy_phase3.py
  tests/test_greedy_phase4.py`: 117 passed.
- The focused unchanged Hybrid static compatibility selection covered all ten
  Phase 3 image tests, four Phase 2 profile/manifest/isolation tests, five
  offline-wheelhouse tests, and two Phase 4 static topology/scope tests:
  21 passed.
- The explicit canonical 10x3x5 example and arbitrary 7x4x3 fixture render
  deterministically and parse back exactly without PyYAML, network, or file
  output.
- Both Dockerfile source inventories materialize in clean temporary image
  trees and import silently without wrong-role, Hybrid, MILP, or legacy
  modules.
- Phase 4 imports are silent, file-free, and global Python/NumPy RNG-neutral in
  a clean temporary directory.
- All changed/new Python files compile with bytecode directed to `/tmp` and
  `git diff --check` passes.

Not verified and intentionally out of scope: Docker builds, base-image pulls,
actual wheel installation, kind or kubectl rendering/application, live
namespace/RBAC/security admission, cluster state, traffic, runtime profiles in
Pods, controller Job execution, launcher lifecycle, dynamic scaling,
rollout-batch behavior, skip-build, JSONL/CSV, live parity, or performance. No
Docker, kind, kubectl, network, or cluster command ran. Existing unrelated
dirty worktree changes remain untouched. The next action is Greedy Phase 5
only after a separate request.

## Greedy Phase 5 complete locally

Updated: 2026-08-25. The persistent lifecycle and dynamic-topology gate is
complete under fake command execution. Phase 6 later completed separately and
is recorded below.

Added:

- `Greedy/kernel_profile_reconciliation.py`
- `Greedy/kernel_rollout.py`
- `Greedy/kernel_lifecycle.py`
- `scripts/run_greedy_kernel.py`
- `tests/test_greedy_phase5.py`

Updated `Greedy/comparison.py` and the four required handoffs. Frozen policy,
learning, utility, SLA, fairness, equilibrium, active Hybrid/Exact sources,
MILP, deployment resources, generated evidence, and unrelated dirty worktree
changes were not modified by Phase 5.

The launcher now has `run`, read-only `preflight`, and explicit Greedy-only
`cleanup`. Run requires explicit positive flow/replica/max-iteration values,
stage at least two, and nonnegative profile seed. Batch size defaults to one;
`--skip-build` is supported; reserved CSV/parity settings default to zero; no
topology default, repetition, policy, candidate/depth, Monte Carlo, or worker
pool option exists. Every call resolves one profile-independent experiment
root and creates exactly one finite controller Job after readiness.

The lifecycle validates exact cluster/context/node/namespace/workload
ownership, worker resources, profiles, image provenance, and Ready coverage.
It supports flow-only capacity updates without Pod replacement, all-stage
batched replica high-suffix expansion/contraction, highest contiguous stage
expansion/contraction, retained profile-prefix preservation, and versioned
recovery of an unambiguous interrupted supported transition. Equal
topology/profile is a serving no-op. Fresh bootstrap orders wheelhouse
validation before offline Docker builds, exact kind creation/image load, static
apply, readiness, and the Job. Skip-build cannot bootstrap and validates local
and node image identities without build/load or forced serving restart.

The Phase 5 Hybrid audit used repository HEAD
`f2e0065204570d9631f26953c94729b451ff92b5`. No relevant lifecycle, CLI,
profile, resource, image, rollout, or readiness drift was found. Exact active
blobs are:

- Hybrid launcher: `c571940408423410df91480470a79f0007a0f68e`;
- Hybrid rollout: `2a766eb47c1149570b01999335d1cb56772709ff`;
- Hybrid profile expansion: `8f10eb51ac4fce23a693ccda783f5828f60422d2`;
- wheelhouse validator: `412e66c89df29b1ea304a2a60fa379b5f981c3b2`;
- one-worker kind configuration:
  `e756783e3923bf87d69b9df2dc0df613ea1ba727`.

Policy-neutral validation is reused, lifecycle/profile/rollout behavior is
adapted behind Greedy ownership for arbitrary stages, and Hybrid policy,
pruning, lookahead, Monte Carlo, process pools, repetitions, netem, and
evidence behavior is excluded.

Verification completed:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/pytest -q
  tests/test_greedy_phase0.py tests/test_greedy_phase1.py
  tests/test_greedy_phase2.py tests/test_greedy_phase3.py
  tests/test_greedy_phase4.py tests/test_greedy_phase5.py`: 137 passed.
- The focused unchanged Hybrid rollout/profile/skip-build/CLI/lifecycle
  compatibility selection: 20 passed.
- Phase 5 import tests produced no stdout, stderr, or files in a clean
  temporary directory; repeated fake-executor runs were deterministic and
  consumed no global Python or NumPy RNG state.
- Changed/new Phase 5 Python files compiled with bytecode directed outside the
  workspace, and `git diff --check` passed.

Not verified and intentionally out of scope: actual Docker builds or image
installation, kind/kubectl behavior, live cluster/context/node/namespace
state, real resource admission, live Pod identity/restart preservation,
traffic, controller execution, performance, console evidence, JSONL, CSV, or
production parity replay. No Docker, kind, kubectl, network, cluster, traffic,
or result-file operation ran during Phase 5. The separately authorized Phase 6
completion is recorded below.

## Greedy Phase 6 complete locally

Updated: 2026-08-26. Greedy console, replay, JSONL, CSV, and controller
footprint evidence are implemented and locally accepted. Phase 7 completed
separately on 2026-08-27 and is recorded below.

Added:

- `Greedy/console_output.py`
- `Greedy/control_plane_footprint.py`
- `Greedy/runtime_resources.py`
- `Greedy/evidence_replay.py`
- `Greedy/evidence.py`
- `Greedy/persistence.py`
- `Greedy/csv_export.py`
- `Greedy/kernel_reporting.py`
- `tests/test_greedy_phase6.py`

The controller prints aligned initial/final beliefs and a completed-slot block
covering predicted, physical realized, raw reference, SLA count/excess,
fairness, time, and equilibrium. It emits one machine record only after the
slot has completely validated and committed. Default parity replay performs no
second solve and records no result; opt-in replay is captured-input-only and
fails closed without HTTP or stochastic redraw.

The host launcher always validates and atomically persists a one-run JSONL
lifecycle after a successful Job. The trace includes complete placement/load,
selected observation/pair, belief, utility/SLA, timing, comparison-matrix,
dimension/seed/profile, lifecycle, source/image, worker allocatable, Pod
resource, CPU/RSS, and throttling provenance. It rejects hidden state,
stochastic seeds, mixed versions/settings, incomplete cardinality, broken
arithmetic, discontinuous beliefs, malformed image/source identity, and
premature non-equilibrium completion. `--csv 1` then exports validated wide
metric/belief and controller footprint files; `--csv 0` remains JSONL-only.
Controller resources contain no result volume.

Phase 6 also closes a lifecycle provenance hole: `--skip-build` refuses when
active service/controller source fingerprints differ from retained image
state. It can no longer associate old node-local images with newly changed
source. No policy, learning, utility, SLA, fairness, equilibrium, Phase 4
resource, port, probe, worker, keep-alive, or security value changed.

The Phase 6 Hybrid audit used repository HEAD
`8e5114e6e9101057da48255962afa65900c6c8d0`. No relevant output-boundary drift
was found. Exact audited blobs are:

- console output: `6a3f9ef99b54e5cc4aa4311f3c5ddc45e437a9ed`;
- controller presentation: `38bc74e203f3b53cf796e0de45899e717d3783f1`;
- slot validation/replay: `64f44a827e6e0915fa545062926c272e66bdb5f9`;
- control-plane footprint: `9ac212bcfab417c7c33cd20fdf8578ed2d14eff6`;
- host lifecycle/CSV launcher: `c571940408423410df91480470a79f0007a0f68e`;
- wide CSV primitives: `67d0e8c8c2d73ff61722ee02d2365234dcc47a70`.

Hybrid human layout, atomic host persistence, optional replay semantics, and
footprint categories were adapted behind Greedy ownership. Hybrid policy,
candidate/depth controls, pruning, lookahead, Monte Carlo, process pools,
repeated runs, netem, and unrelated diagnostics remain excluded.

Verification completed:

- `PYTHONPYCACHEPREFIX=/tmp/greedy-phase6-pycache .venv/bin/python -m pytest
  -q tests/test_greedy_phase0.py tests/test_greedy_phase1.py
  tests/test_greedy_phase2.py tests/test_greedy_phase3.py
  tests/test_greedy_phase4.py tests/test_greedy_phase5.py
  tests/test_greedy_phase6.py`: 159 passed.
- The focused unchanged Hybrid console, optional replay, JSONL lifecycle, SLA
  validation, CSV alignment/atomicity, and control-plane footprint selection:
  35 passed.
- Phase 6 imports are silent and file-free in a clean temporary directory.
  JSONL and CSV round trips, duplicate refusal, unequal-run padding,
  no-controller-volume behavior, captured replay, and deterministic fake
  measurement seams pass.
- Changed/new Python sources compile with bytecode outside the workspace and
  `git diff --check` passes.

Not verified and intentionally out of scope: Docker image construction or
installation, kind/kubectl behavior, live cluster/context/node/namespace
state, real Pod admission, traffic, controller Job execution, live console or
host persistence, live replay, live CPU/RSS/throttling values, performance, or
repository experiment output. Tests wrote fixtures only under pytest temporary
directories. No Docker, kind, kubectl, network, cluster, traffic, repository
JSONL/CSV, or live operation ran. The separately authorized Phase 7 completion
is recorded below.

## Greedy Phase 7 complete locally

Updated: 2026-08-27. The complete local integration and regression gate is
accepted. Phase 8 is the next action only after separate live authorization;
it has not started.

Added:

- the final semantic/source audit entries and HEAD lock in
  `Greedy/comparison.py`;
- `tests/test_greedy_phase7.py`.

No runtime implementation changed. The new gate composes completed Phase 0--6
behavior and covers explicit `3x2x1`, `5x2x2`, and `5x4x3` configurations,
including `K=2`, `K>2`, one/multiple replicas, `ceil(N/M)` admission, complete
L2 placements, bounded cache behavior, and deterministic offline resource and
controller-Job rendering. Existing tests cover equal-topology no-op,
flow-only changes, bounded replica expansion, highest-suffix contraction,
stage expansion/contraction, interrupted-transition recovery, malformed-state
refusal, skip-build source-drift refusal, persistent clients, concurrent route
dispatch with ordered hops, sequential placement/load mutation, optional
captured replay, exact timings/footprint, JSONL, CSV, and manifest security.

Controller resource instrumentation now has an explicit equality gate: fake
finite experiments with and without CPU/RSS/cgroup-throttling samples have
identical pure slots, placements, loads, belief updates, utility, SLA,
fairness, equilibrium, and stopping. Only the optional measurement field
differs. Duplicate CSV headers and rows wider than their retained header are
also rejected. The aggregate Phase 0--6 import gate is silent, file-free, and
global Python/NumPy RNG-neutral and never imports unsafe `Greedy/main.py`.

The final comparison audit used starting/current repository HEAD
`8e5114e6e9101057da48255962afa65900c6c8d0`. All 35 unique active
Hybrid/shared source and manifest paths represented by 45 Phase 3--7 audit
records match their exact recorded blobs. The 52 required
`greedy-hybrid-matched-comparison-v1` rows remain equal and ordered; its 11
intentional policy differences remain the only declared differences. The four
final semantic blobs are:

- `IBG_Hybrid/contracts.py:12-54`:
  `4f50cb74b56f3739a9dba1be59b80091f8f20732`;
- `IBG_Hybrid/phase0_contract.py:234-307`:
  `45eb84512efa7457648ae8667b30e7f83f25f304`;
- `IBG_Hybrid/runner.py:198-218,281-386,544-630`:
  `b60ddcc0c7d55d7c6d3cc55e2308c194d24389c3`;
- `IBG_Hybrid/simulation.py:21-161`:
  `1b9f59f208885874b57e06e1d92fcabeeccc2db4`.

Reuse remains limited to policy-neutral latency/likelihood/learning,
processor/forwarder behavior, fixed comparison resources, and offline
validation. Greedy-owned identities, arbitrary-stage routes, lifecycle, and
evidence are adaptations. Hybrid pruning, activation, planning-link
selection, lookahead, Monte Carlo, policy/process-pool controls, and repeated
runs remain excluded.

Verification completed:

- complete Greedy Phase 0--7 suite: 166 passed;
- focused unchanged Exact/Hybrid compatibility selection: 61 passed;
- direct launcher top-level, `run`, `preflight`, and `cleanup` help: exit 0;
- direct empty `run` invocation: expected argparse refusal, exit 2, listing all
  five required inputs before lifecycle execution;
- all small offline long-running/controller/kind renders parsed and matched
  their canonical forms;
- clean-directory imports were silent, file-free, and RNG-neutral;
- changed Python files compiled with bytecode outside the workspace;
- `git diff --check` and final frozen-path status/digest comparison passed.

Not verified and intentionally out of scope: image construction/loading,
Docker, kind, kubectl, a live namespace/cluster, real Ready or resource
admission, traffic, controller Job execution, live console/JSONL/CSV/replay,
actual controller resource values, or performance. No live or network command
ran, and no repository experiment result was created. Pre-existing unrelated
changes under `IBG/`, MILP, `Chart/`, and `EVIDENCE_SUMMARY.md` remained
untouched; Phase 7 introduced no change under any prohibited or frozen path.

## Greedy Phase 8 small live gate complete

Updated: 2026-08-27.  Phase 8 is accepted.  The dedicated live cluster remains
present for an explicitly authorized Phase 9: cluster `greedy`, context
`kind-greedy`, namespace `greedy-testbed`, nodes `greedy-control-plane` and
`greedy-worker`.  Both nodes are Ready; the worker has
`greedy.workload-node=true`.  Existing stopped `ibg` and `ibg-hybrid` clusters
were neither reused nor mutated.

Accepted invocation shape and environment:

- explicit `--flow 3 --stage 3 --replica 2 --max-iterations 50`;
- `--profile-seed 17 --rollout-batch-size 1 --csv 1
  --parity-replay 1`;
- profile fingerprint `53de63eb180316c2fc4b9f5f02b078ed`;
- worker allocatable 8000 millicores and 32044 MiB after conservative `Ki`
  conversion;
- service node config ID
  `d8f90a98f0d5b7567bfa89f5570fbdeb83e487508edc8e32e703f787e45bff1e`;
- controller node config ID
  `803cb4c93eb95779b5772e122e7b4ec0e8133188beae4a3536b1cdc5602b279f`.

The normal offline bootstrap produced
`runs/greedy-experiment-20260827T095759.183839Z.jsonl`: 16 lifecycle events,
14 slot events, equilibrium stop, `bootstrap=true`, both images built/loaded,
forced parity true for every slot, and complete 3 placements/6 selected
observations/3 measured pairs per slot.  Its controller process samples range
from 0.015583006 to 0.039220608 CPU seconds and 58,535,936 to 59,219,968 RSS
bytes; cgroup throttle count/usec remained zero.  Total slot wall times range
from 0.123195 to 0.202234 seconds.

The unchanged `--skip-build` repeat produced
`runs/greedy-experiment-20260827T095942.447983Z.jsonl`: 12 lifecycle events,
10 slots, equilibrium, `bootstrap=false`, empty built/loaded image lists, and
parity/cardinality checks true throughout.  Its CPU samples range from
0.010241184 to 0.030558890 seconds, RSS from 58,548,224 to 59,039,744 bytes,
zero throttling, and total slots from 0.104681 to 0.155730 seconds.  All seven
serving Pod UIDs and restart counts remained identical at zero; the finite Job
UID changed from `0801ce1a-2970-4ab7-9cbc-4780bae81945` to
`7a2dd490-c4e3-4369-9432-bee8d8202bf1`.

CSV export under `figures/Greedy/` contains 31 validated files.  Metric files
have two run columns and 14 rows with unequal-run padding; replica evidence has
unique six-identity columns.  No hidden state or physical/observation seed key
appears in either validated JSONL trace.  Initial readiness-probe
connection-refused events were transient startup events; the final generator
and all six replica Pods are Running/Ready on the worker with zero restarts.

Live compatibility fixes made during the gate:

- floor valid Kubernetes `Ki` allocatable memory to whole MiB;
- resolve local linux/amd64 OCI config IDs before comparing kind node images;
- accept only bounded three-decimal belief sum drift in evidence; and
- emit the 64-hex source fingerprint required by the trace schema.

Verification completed:

- complete Greedy Phase 0--8 suite: 176 passed;
- focused unchanged Exact/Hybrid compatibility selection: 113 passed;
- two canonical JSONL lifecycle round trips, forced replay, cardinality,
  resource, seed-redaction, and CSV checks passed;
- live exact ownership, two-node topology, worker-only placement, Ready
  coverage, resources, probes, security contexts, RBAC, private/public mount
  boundaries, image identity, skip-build reuse, Job replacement, and zero
  serving restarts passed.

Not claimed: cross-policy same-input performance, large scale, multi-host,
line rate, DPDK/VPP, netem, resource retuning, or Phase 9 transition evidence.
Pre-existing unrelated changes under frozen/prohibited paths remain untouched.
Phase 9 scale and final-baseline acceptance was previously recorded as next,
but the paper audit below now supersedes that ordering.

## Greedy paper audit and corrective-phase status

Updated: 2026-08-27. A targeted read of `misc/vesal_tex.tex` confirms that the
paper's Greedy baseline uses current beliefs and observed pre-decision counts,
evaluating immediate utility at `n+1`, while ignoring subsequent-flow choices
and their future congestion. The paper defines physical node/resource capacity
and state-conditioned congestion behavior but does not define the
topology-derived `ceil(N/M)` assigned-flow admission ceiling.

The pre-correction `pure-greedy-budgeted-l2-v1` implementation had a material
baseline mismatch: `GreedyConfiguration.admission_capacity_per_replica`,
`PublicReplicaState.max_assigned_flows`, discovery labels, and feasibility
reject a replica above `ceil(N/M)`. This can mechanically suppress the
premature hot spots that the paper attributes to Greedy myopia. Current-load
scoring itself is correct and must remain: Greedy is reactive to congestion
from earlier real flows but blind to congestion from future flows.

Other paper differences were rechecked. The paper describes per-stage/all-K
Greedy selection and a highest-positive choice, whereas the container baseline
uses the user's deliberate exact `L=2` joint action, bypasses `K-2`, and
requires the best complete feasible route even when scores are non-positive.
Those behaviors are not part of this correction. Link-cost wording in the
paper is internally inconsistent; the current explicit no-link-selection
contract also remains unchanged.

The offline Phase 8.1 correction is complete. The active contract is
`pure-greedy-budgeted-l2-v2`; policy feasibility is exact identity coverage
plus public Ready state, with no configuration property, public-state field,
discovery label, rendered label, lifecycle equality check, controller input,
or new evidence field for synthetic admission. The policy still evaluates
every candidate at its actual `current_load+1`, commits the selected pair
sequentially, and performs no future-flow simulation. A deterministic `5x2x2`
fixture reaches load five on one selected replica, above the old ceiling of
three, and proves successive scores use loads 1 through 5.

Paper findings were revalidated at `misc/vesal_tex.tex:677-700`,
`:981-1032`, `:1084-1088`, and `:1675-1708`: utility is
congestion-sensitive; the full budgeted solver predicts subsequent load;
Greedy instead uses observed pre-decision counts plus one and is explicitly
myopic; premature hot spots are an expected baseline outcome. No paper rule
defines `ceil(N/M)` flow admission, and physical node capacity remains
separate from modeled processing congestion.

The source audit used repository HEAD
`ae95e74497339b6ce49d96a709409489ef287fd5`. Active Hybrid still declares
`max_assigned_flows` and rejects projected overflow in
`IBG_Hybrid/phase0_contract.py:232-289` (blob
`45eb84512efa7457648ae8667b30e7f83f25f304`) and derives `ceil(N/M)` in
`IBG_Hybrid/kernel_profile_expansion.py:587-600` (blob
`8f10eb51ac4fce23a693ccda783f5828f60422d2`). Its focused test blobs are
`c46ebb91100d85d29e7e24afe0a3e641a694e482` and
`d8edc6944dd5314de819eddadd67e7dd82467cf1`. No drift was found and no Hybrid
file was modified. `greedy-hybrid-matched-comparison-v2` therefore records an
unresolved admission mismatch; a final same-input comparison requires a
separately accepted common physical/admission rule.

The final working-tree source/blob audit for the affected production boundary
is: `phase0_contract.py` `29d26c99729bb743b5c839757a39e4d573ef2a91`;
`contracts.py` `8579d7dcccd5e4d3b8efb1630514e2498bc014ef`;
`policy.py` `1b22a4a3c184f26c9db0b30ed28fb497a01fce37`;
`oracle.py` `ea4a8ab8fc9d3ccae1de36fe09d34fc56daef858`;
`comparison.py` `183990b11ad2ecef381899a67a1f856c8d3fbd7c`;
`kernel_contracts.py` `9ed06f21f6f2e1a18a44068608de887b64ce4544`;
`kernel_kubernetes_discovery.py`
`22bb10f85dbdb7e10357e56fbe4b4f61b8bf7f45`;
`kernel_controller.py` `6e2a0e2115da6dbcc69ada13093071be3508de58`;
`kernel_infrastructure.py` `b83eb8401d0cbe38c6122badb0bc312ee4de5f27`;
`kernel_rollout.py` `71e10755f6260734bb0586b10a6696ef8520ace8`;
`kernel_lifecycle.py` `0bdef84b7127058d4667942eaa731535e68db979`;
`evidence.py` `22396a3068edd0976c9c0fec69841d0311fee925`;
`persistence.py` `d7fd773cef384feec34507e9e76aa1a1d191dea5`;
`csv_export.py` `d65510ea476f78683d7fc4ea75620aaf92ad5e70`;
and `scripts/run_greedy_kernel.py`
`a2efc1a4543176a2d13a992ddff551cfe661c452`.

V1 Phase 8 JSONL remains immutable and readable through explicit legacy slot,
comparison, and trace validators. New slot/trace schemas are v2 and omit the
removed field. CSV uses a policy-contract marker, defaults to
`figures/Greedy/v2`, and rejects unversioned retained data or mixed v1/v2
columns. No production v2 JSONL or CSV was created.

Verification completed on 2026-08-27:

- `PYTHONPYCACHEPREFIX=/tmp/greedy-phase81-final-pycache .venv/bin/python -m pytest -q tests/test_greedy_phase0.py tests/test_greedy_phase1.py tests/test_greedy_phase2.py tests/test_greedy_phase3.py tests/test_greedy_phase4.py tests/test_greedy_phase5.py tests/test_greedy_phase6.py tests/test_greedy_phase7.py tests/test_greedy_phase8.py tests/test_greedy_phase81.py`:
  183 passed in 18.45 seconds.
- `PYTHONPYCACHEPREFIX=/tmp/greedy-phase81-compat-pycache .venv/bin/python -m pytest -q tests/test_latency_model.py tests/test_learning_signal.py tests/test_ibg_hybrid_phase0.py::test_feasibility_uses_ready_and_declared_flow_capacity_only tests/test_ibg_hybrid_kernel_dynamic_topology.py::test_dynamic_transition_accepts_formula_changes_and_rejects_drift tests/test_greedy_phase4.py::test_arbitrary_topology_render_is_complete_deterministic_and_parseable tests/test_greedy_phase7.py::test_arbitrary_shapes_are_policy_complete_and_offline_renderable tests/test_greedy_phase81.py::test_v2_render_and_controller_inputs_have_no_synthetic_capacity_field_or_label`:
  19 passed in 1.80 seconds.
- Clean-directory import tests cover all owned Phase 0--8 modules and remain
  silent, file-free, and RNG-neutral. Changed Python compilation directs
  bytecode to `/tmp`; local render/parse and capacity-label absence checks pass.
- Compilation used `PYTHONPYCACHEPREFIX=/tmp/greedy-phase81-compile .venv/bin/python -m py_compile` with the 15 affected production modules above plus the
  updated Phase 0--7 and Phase 8.1 test modules; it exited zero and created no
  workspace bytecode.
- `git diff --check` passes. Final path status preserves every pre-existing
  unrelated/frozen-path change; Phase 8.1 did not edit `IBG/`, `IBG_Hybrid/`,
  MILP, `Chart/`, `Tutorial.md`, `Report.md`, or `EVIDENCE_SUMMARY.md`.

Not verified or claimed: live image rebuild/load, cluster reconciliation,
traffic, production v2 JSONL/CSV, corrected live replay, performance, scale,
or a Greedy/Hybrid same-admission comparison. Phase 8.2 is the next separately
authorized live correction gate. Phase 9 remains deferred until it passes.
## Hybrid posterior-transmission mirror planned

Updated: 2026-08-31. The current Hybrid implementation keeps and updates all
authoritative beliefs inside the controller. Consequently, the existing
observed application-body footprint correctly reports belief TX/RX as zero.
The manuscript, however, discusses exchanged posterior summaries and defines
control-plane overhead using telemetry plus belief updates. A new opt-in
measurement extension is therefore planned to isolate and measure posterior
payload volume without converting the algorithm to distributed belief
ownership.

The accepted design adds a separate worker-only HTTP receiver only when
enabled. The controller sends deterministic, non-authoritative copies of its
completed posterior updates; the receiver validates and discards them. Exact
canonical vector bytes, complete application-body bytes, message counts, and
per-timeslot totals will be kept separate from protocol overhead and from the
existing Kubernetes/route/telemetry footprint. Local beliefs continue to drive
all future decisions, and existing observed belief TX/RX fields and historical
traces remain unchanged.

Three phases are recorded. Phase 1 implements the contract, receiver,
deployment integration, evidence, and focused tests locally. Phase 2 performs
complete local verification and records actual results. Phase 3 is a separately
authorized matched live validation. No implementation, test, build, render,
Docker, kind, Kubernetes, Job, Pod, traffic, or experiment action has been
performed for this feature yet.

## Hybrid posterior-transmission mirror Phase 2 complete locally

Updated: 2026-08-31. Phase 1 and Phase 2 are complete in the local worktree.
`--posterior-mirror 1` enables real HTTP copies of completed aggregated
posteriors to a separate worker-only validation/discard receiver; the default is
disabled. The controller's local beliefs remain authoritative, and existing
observed control-plane belief TX/RX values remain zero.

Enabled `--csv 1` runs now export vector payload bytes, complete application-
body bytes, and update-message counts under
`figures/IBG_hybrid/posterior_mirror/`. The Hybrid-only posterior-mirror summary
reports per-timeslot values plus total, median, and p95 and clearly labels the
result as an instrumented non-authoritative payload mirror rather than wire or
required distributed-learning traffic.

Local evidence is green: 104 final focused tests passed; the complete Hybrid
suite passed as 162 + 103 + 146 = 411 tests; changed Python compilation, clean
imports, CLI help, seven retained offline renders, the enabled-receiver offline
render, and `git diff --check` passed. IBG-Exact was untouched and not tested.
No live cluster mutation, build/load, Job, Pod, traffic, or experiment occurred.

Next action: prepare Phase 3 read-only preflight and exact matched disabled/
enabled commands only after explicit user authorization. Live receiver and
semantic evidence remain unvalidated until that gate runs.

User-run preflight follow-up: a retained manual-rollout annotation caused the
template guard to reject reconciliation before apply. The local launcher now
preserves that non-netem annotation while changing only requested impairment
fields. Sixty-five focused tests, compilation, and `git diff --check` pass. The
agent performed only live read-only inspection and server-side dry-run; it did
not rerun traffic or mutate the cluster.

The subsequent enabled receiver Pod entered `CrashLoopBackOff` before traffic
because the controller image intentionally lacks Uvicorn. Read-only logs
confirmed `/usr/bin/python3: No module named uvicorn`. The local manifest now
uses the Hybrid service image and its existing pinned Uvicorn runtime; the
service image also includes the self-contained mirror module. Fifty-eight
focused tests, compilation, and `git diff --check` pass. The failed live
Deployment was not restarted or modified by the agent, and no controller Job
or experiment traffic was started by this failed gate.

## Greedy Phase 8.2 live rollout timeout status

Updated: 2026-09-01. The owned Greedy nodes were restarted explicitly and both
became Ready; the Greedy isolation preflight passed. The retained `3x10`
serving topology then recovered to complete readiness. A user-started normal
`40-flow/3-stage/20-replica`, one-iteration run scaled and rolled all three
StatefulSets, but the single fixed 120-second `kubectl rollout status` command
timed out despite continuing progress. All stages subsequently reached 20/20
Ready, but no controller Job was created. `--skip-build` correctly refused the
still-active service-image transition marker. A second normal attempt repeated
the full revision rollout and hit the same fixed-deadline condition; it too
eventually reached 20/20 Ready per stage with no controller Job.

The local launcher now treats 120 seconds as a stall timeout reset only by
verified generation/revision, updated/Ready count, or new owned Pod UID/
readiness progress. It also enforces a topology-bounded total deadline and
retains exact final revision and Pod coverage validation. Verification:

- `PYTHONPYCACHEPREFIX=/tmp/greedy-rollout-timeout-phase5-pycache .venv/bin/python -m pytest -q tests/test_greedy_phase5.py`: 21 passed.
- Focused rollout/bootstrap/scale/skip-build checks: 6 passed.
- The synthetic progress test succeeds after 140 seconds of continuing
  progress and fails after 122 seconds without progress.
- Changed Python compilation and `git diff --check` pass.
- Complete Greedy Phase 0--8.1 selection: 183 passed, one failed solely because
  the current unrelated dirty `IBG_Hybrid/kernel_controller.py` blob no longer
  equals the frozen Phase 7 comparison audit. No Hybrid file was changed for
  this Greedy repair.

Phase 8.2 is not accepted yet. No corrected experiment trace or CSV exists, no
controller Job is running, and the live StatefulSet templates still retain the
historical `greedy.max-assigned-flows` label despite the local v2 renderer
excluding it. Do not claim v2 live completion until the pending transition is
resumed with this progress-aware launcher and the stale-label reconciliation
gate is fixed and verified.

## Greedy Phase 8.2 rollout recovery completed

Updated: 2026-09-01. Starting state was branch `IBG` at
`ac026c77506fd4cf115106a1d7696255290d9238`, with unrelated dirty Hybrid
posterior-mirror work preserved. Read-only preflight found exactly the expected
Ready control-plane/worker pair, no launcher process or controller Job, three
fully Ready but transition-marked 20-replica StatefulSets, exact running
service image ID
`7df0670f2107506093812904e9f9bd80ded049b9869235603384b7062da2bf89`,
and the pending `40x3x20` launcher target with profile fingerprint
`ef7c80158b547c94d26f40cd158d1381`. All retained serving templates and Pods
still carried `greedy.max-assigned-flows=2` and lacked deterministic rollout
provenance.

The repaired lifecycle now annotates each serving template with the exact
service image ID and source fingerprint, distinguishes legacy/update-required,
progressing, and converged transitions, rejects ambiguous provenance, and
validates running CRI image IDs. It applies a canonical template correction at
most once, removes the stale capacity label, and no longer follows an apply
with `kubectl rollout restart`. The 120-second value is a verified-progress
stall timeout; an independent topology-bounded deadline rejects endless UID
replacement churn. Launcher state is marked stable only after exact template,
revision, Ready identity, profile, and image convergence.

The exact authorized live command was:

```text
.venv/bin/python scripts/run_greedy_kernel.py run --flow 40 --stage 3 --replica 20 --max-iterations 1 --profile-seed 17 --rollout-batch-size 3
```

It performed no image build/load because local source fingerprints and exact
local/node OCI config IDs already matched. One canonical apply combined the
provenance and stale-label correction. The observed serving-Pod replacement
window was 162 seconds, from `2026-09-01T16:34:47Z` through
`2026-09-01T16:37:29Z`, and progressed beyond the former fixed 120-second
deadline. Revisions converged as follows:

- stage 1: `greedy-stage-1-6ff5769677` at 20/20 updated and Ready;
- stage 2: `greedy-stage-2-54bdd8ddb` at 20/20 updated and Ready;
- stage 3: `greedy-stage-3-64f5c7f4c` at 20/20 updated and Ready.

All 60 replica Pod UIDs and the flow-generator UID changed in this one
necessary template rollout; all new serving containers had zero restarts. The
capacity label is absent from every active Pod and template. CRI inspection
found 60 private processors, 60 public forwarders, and one flow generator,
all Running with exact image ID `7df0670f...bf89`. Launcher state is now stable
at `40x3x20` with `transition_active=false` and
`service_restart_required=false`.

Exactly one controller Pod, `greedy-controller-7vt5g`, completed successfully
with zero restarts. The validated evidence is
`runs/greedy-experiment-20260901T163749.921241Z.jsonl` using
`greedy-experiment-jsonl-v2` and `pure-greedy-budgeted-l2-v2`. It contains one
completed iteration, 40 complete placements, 80 selected observations,
40 measured-pair records, 40 route requests, one controller-to-generator
request, and no hidden-state or stochastic-seed keys. CSV and replay were not
requested or performed. No second experiment was started.

Final offline verification for this recovery:

- `PYTHONPYCACHEPREFIX=/tmp/greedy-phase82-final-focused .venv/bin/python -m pytest -q tests/test_greedy_phase5.py tests/test_greedy_phase81.py`: 36 passed.
- Complete Greedy Phase 0--8.1 selection: 192 passed and one failed. The sole
  failure remains the frozen comparison audit for unrelated dirty
  `IBG_Hybrid/kernel_controller.py`: expected blob
  `b9408745de6175316481a47915423d16c9b1aea8`, current blob
  `81d0d3514b9c41f720763938a7f0b0c83412e030`. Hybrid was not modified and the
  audit was not weakened.
- Changed Python compilation with external bytecode and `git diff --check`
  pass.

The rollout-recovery substep passes, but complete Phase 8.2 remains open. This
specific `40x3x20` trace had maximum final replica load two and did not request
forced replay or CSV; an unchanged `--skip-build` repeat was intentionally not
started. The separate Phase 8.2 gate still requires its deterministic
above-old-ceiling live demonstration, forced replay/CSV validation, and
unchanged skip-build repeat. Phase 9 remains blocked until those pass.

## Greedy Phase 8.3 offline end-to-end fairness correction completed

Completed offline: 2026-09-01. Nothing was run live and no experiment was
rerun.

The reported Greedy Jain index scored the wrong per-flow series. Eq.
(e2e_utility) in `misc/vesal_tex.tex` defines per-flow utility as the selected
stage utilities minus the inter-stage link costs, and the paper scores fairness
over that quantity. `Greedy/metrics.py` summed only the stage utilities and
dropped the link term, so the index was a function of belief and final load
alone. In `runs/greedy-experiment-20260901T164804.903455Z.jsonl` that made all
40 flows share the identical predicted value `134.619568` and report fairness
`0.999994`, while the same slot's realized end-to-end values ranged 59.69 to
159.15 and its per-flow measured pair cost ranged 8.74 to 66.98 ms. Recomputing
that slot over the corrected series gives `0.958115`. Active Hybrid already
subtracts its planning link cost (`IBG_Hybrid/runner.py:293-305`) and IBG
applies a link penalty (`IBG/runner.py:229`), so Greedy was the only policy of
the three omitting it.

What changed, in `Greedy/` only:

- `metrics.py`: new `clamped_end_to_end_fairness` scores
  `raw_end_to_end_reference_utility_per_flow` with each flow floored at zero
  and returns the index plus `fairness_domain_valid`; assembly bumped to
  `greedy-active-slot-metrics-v2`. The zero floor exists because Jain is only
  meaningful on nonnegative values: on mixed signs it rated three healthy flows
  plus one ruined flow at `0.075`, and a slot with every flow ruined at a
  fair-looking `0.67`.
- `slot_contracts.py`: `GreedySlotMetrics.fairness_domain_valid`.
- `evidence.py`: three readable generations. v3 recomputes the clamped
  end-to-end index and the flag; v1 and v2 keep the retired predicted formula
  and must not carry the new field; unknown generations are refused. Slot
  evidence bumped to `greedy-kernel-slot-evidence-v3`.
- `persistence.py`: trace bumped to `greedy-experiment-jsonl-v3`, with v1 and
  v2 still loadable.
- `csv_export.py`: the marker pins policy and trace contract together because
  the policy version did not change; default output moved to
  `figures/Greedy/v3`; a pre-Phase-8.3 marker or foreign generation fails
  closed.
- `console_output.py`: the slot line now reads `end-to-end fairness=` and
  appends `(clamped)` when the domain flag is false.

Verification actually run:

- `PYTHONPATH=. .venv/bin/pytest tests/test_greedy_phase83.py -q`: 19 passed.
- `PYTHONPATH=. .venv/bin/pytest tests/ -k greedy -q`: 215 passed, 1 failed.
- Complete suite `PYTHONPATH=. .venv/bin/pytest tests/ -q`: 1029 passed, 6
  failed.

Every failure is pre-existing and unrelated. One is the frozen comparison audit
for dirty `IBG_Hybrid/kernel_controller.py` (expected blob
`b9408745de6175316481a47915423d16c9b1aea8`, current
`81d0d3514b9c41f720763938a7f0b0c83412e030`); the other five are
user-controlled `Chart/` tests excluded under their repository guardrail, and
neither Chart module imports `Greedy`. `tests/test_greedy_phase6.py` was
updated only so its synthetic v1 downgrade emits a faithful historical
document.

Not done, and owed:

- No live run. Phase 8.2's acceptance evidence must now be produced under the
  v3 contracts, and its topology should use a small `M` so replica loads
  actually exceed one or two; every completed `40x3x20` trace so far peaked at
  load two, which is why fairness had no congestion to measure.
- `Greedy/comparison.py` still lists `learning_and_metric_semantics` as a
  matched Greedy/Hybrid row. That row is now stale by explicit user decision;
  the divergence is recorded in `DECISIONS.md` and no same-metric fairness
  claim is permitted.
- The paper's node-capacity constraint (`misc/vesal_tex.tex` line 819,
  `sum_i d_{i,k,j} * rho_{k,j} <= C_{h(k,j)}`) remains unimplemented. It is the
  paper's real per-replica flow limit and is unrelated to the removed
  `ceil(N/M)` ceiling; the user explicitly deferred it.

Phase 9 remains blocked.

## Greedy Phase 8.3 rebuilt-service rollout repair completed

Completed offline: 2026-09-01. No cluster mutation was performed by the
implementation; the user ran the build.

The user's first authorized Phase 8.3 rebuild built and loaded both images and
then failed closed:

```
Greedy cluster isolation failure: serving rollout provenance is mismatched:
StatefulSet/greedy-stage-1
```

Cause: `Greedy/slot_contracts.py` is a member of both `SERVICE_SOURCE_FILES`
and `CONTROLLER_SOURCE_FILES`, so the single `fairness_domain_valid` field
added in Phase 8.3 moved the service source fingerprint from
`d9d0e69efcf870a201c0a44f618380dcf8e51057b3c32b5509b56d6b824bcfdb` to
`3a51cb938bcd197a21eba3c4ad1def30a7cb6fbfa7b67be76c467e9c85c33311` and rebuilt
the service image, while every serving Pod template still carried the previous
pair.

This was a latent launcher gap, not a Phase 8.3 regression.
`_classify_service_rollout` accepted only absent provenance (legacy or
not-started) or exact target provenance, so `exact(old) -> exact(new)` was
unreachable and no service-source change could ever be applied to existing
serving workloads. Earlier rebuilds passed only because the annotations were
introduced in that same change and read as absent. Deleting serving workloads
is not a workaround either, because the classifier requires complete coverage
of all four serving resources.

Repair, in `Greedy/kernel_lifecycle.py` only. The first attempt compared the
templates against the pair recorded in `greedy-launcher-state`. The user's
retry proved that insufficient and is worth recording: the interrupted run had
already persisted its transition marker, so the record had advanced to
`service_source_fingerprint=3a51cb93...`,
`service_image_id=eda4c834...`, `service_restart_required=true`,
`transition_active=true`, while the templates still held the superseded pair.
The recorded pair therefore no longer identified them and the failure moved
earlier, to the pending-rollout check.

The landed repair gates on a declared `rebuild_pending` instead. When the
launcher knows a service rebuild is committed for this run, a uniform
non-target pair is the pre-rebuild template and classifies as
`template-update-required`. This is the correct discriminator because the
marker is persisted before the canonical apply, so the superseded pair is not
recoverable from the record by any equality test; what the launcher can always
assert is that it rebuilt the service. `_reconcile_existing` declares the run's
`service_restart_required`, and the pending-rollout check declares it
unconditionally because it only executes when a restart is already recorded.

Everything else stays strict: all four serving resources must agree on one
mode, a mixed set is still `partial or ambiguous`, a half-written annotation
pair still raises, a non-target pair with no pending rebuild is still foreign
mutation, and the final post-apply gate omits `rebuild_pending` so a settled
rollout must show exact provenance. Overwriting an unexpected uniform pair
during a declared rebuild is acceptable because the launcher already asserts
exclusive namespace ownership and the canonical apply is the corrective action.

Verification actually run:

- `PYTHONPATH=. .venv/bin/pytest tests/test_greedy_phase5.py -q`: 36 passed,
  including six new classification tests covering a clean rebuild, the
  interrupted-transition resume, the strict settled-rollout check, an unrebuilt
  service under a pending rebuild, partial provenance, and a half-written
  annotation pair.
- `PYTHONPATH=. .venv/bin/pytest tests/ -k greedy -q`: 221 passed, 1 failed.
- Complete suite: 1035 passed, 6 failed.
- The live blocked inventory and its recorded launcher state were replayed
  read-only. The pending check raises `serving rollout provenance is
  mismatched` without `rebuild_pending` and returns `template-update-required`
  with it; the final gate still raises, correctly, until the canonical apply
  updates the templates.

The six failures are the same pre-existing unrelated ones recorded for Phase
8.3: the frozen comparison audit for dirty `IBG_Hybrid/kernel_controller.py`
and five guardrail-excluded user-controlled `Chart/` tests.

Next action: rerun the launcher. The previously blocked command should now
reconcile the serving templates and create one finite controller Job. The
`--csv` help text was corrected to name `figures/Greedy/v3`. Phase 8.2 still
owes its acceptance run under the v3 contracts, preferably at a small `M` so
replica loads exceed one or two. Phase 9 remains blocked.

## Greedy belief-tolerance repair and live launcher output

Implemented locally: 2026-09-01, after the Phase 8.3 contracts were already in
the tree.

A user `40x3x20`, 50-iteration run with `--profile-seed 17 --skip-build --csv 1`
created its controller Job normally and completed eleven slots, then the Job
failed with `BackoffLimitExceeded`. The pod traceback was
`ValueError: beliefs_after belief vectors exceed the rounded unit-mass
tolerance` from `Greedy/evidence.py` `_belief_mapping`, reached through
`kernel_controller_service.py` slot persistence on iteration 12. No trace was
written for that run.

The cause was the validator bound, not the learner. Measured
`max |sum(belief) - 1|` per slot in the two completed ten-slot traces
`runs/greedy-experiment-20260901T184309.744815Z.jsonl` and
`...T184835.529758Z.jsonl` rises from 0.000 to 0.002 and then sits pinned at
0.002, which is exactly the former tolerance; slot 12 was the first to exceed
it. The frozen learner rounds four posterior entries independently to three
decimals and never renormalizes, and each slot re-rounds a belief retained at
0.8, so the per-slot 4 * 0.0005 error accumulates toward 0.01.

Changes:

- `evidence.py`: `GREEDY_ROUNDED_BELIEF_SUM_TOLERANCE` `0.0020000001` ->
  `0.0100001`, with the accumulation derivation recorded in the comment. No
  contract version moved; expected utility already normalizes by the belief
  sum, so no mathematical or evidence semantics changed.
- `kernel_reporting.py`: `_follow_controller_logs` follows the finite Job with
  `kubectl logs --follow --pod-running-timeout=600s` and prints each
  non-evidence line live. The captured log is still re-read afterwards for
  trace construction, and the post-run projection is silenced when the live
  follow already displayed the same text.
- `kernel_lifecycle.py`: `run_greedy_lifecycle` gained an optional
  display-only `stream_logs` hook, invoked once the Job exists and before the
  unchanged `kubectl wait --for=condition=complete`. It defaults to absent.
- `tests/test_greedy_phase8.py`: the rounding-bound cases encoded the retired
  single-pass assumption. A vector off by exactly 0.01 is now an accepted
  accumulated extreme; the rejection cases moved to 0.96 and 1.02.

Verification actually run:

- `PYTHONPATH=. .venv/bin/pytest tests/test_greedy_*.py -q`: 219 passed,
  1 failed.
- The sole failure is
  `test_greedy_phase7.py::test_phase7_comparison_envelope_matches_current_active_hybrid_sources`,
  the pre-existing frozen comparison audit. Its recorded constant is
  `b9408745de61...`, while both the committed and the worktree blob of
  `IBG_Hybrid/kernel_controller.py` are `81d0d3514b9c...`, so it fails on a
  clean checkout of HEAD and is unrelated to this repair. `IBG_Hybrid/` was not
  edited.
- Changed Python compiles and imports.
- No experiment was rerun by the implementation agent.

Next action: rerun the failed command **without** `--skip-build`. The
controller image copies `Greedy/evidence.py` at build time
(`deploy/greedy-kubernetes/Dockerfile.controller`), so a skip-build reuse would
run the retired bound and fail on iteration 12 again. Phase 8.2 still owes its
acceptance run under the v3 contracts, preferably at a small `M`: the completed
`40x3x20` runs reached a maximum replica load of four, left 24 of 60 replicas
unobserved in the final slot, and never approached the 0.04 equilibrium
threshold. Phase 9 remains blocked.

## End-to-end SLA threshold raised to 130 ms

Updated: 2026-09-02.

The end-to-end reporting SLA threshold is now 130 ms for both Greedy and Hybrid
(`GREEDY_SLA_LATENCY_THRESHOLD_MS`, `HYBRID_SLA_LATENCY_THRESHOLD_MS`), chosen
from trace evidence after 100 ms proved to sit at the steady-state median. Both
80 ms and 100 ms are now version-bounded history. The
selected-processing SLA stays 110 ms and realized utility is unchanged. See the
`DECISIONS.md` entry for the reasoning and the version-bounded compatibility path
that keeps existing 80-ms traces readable.

Verified: `PYTHONPATH=. .venv/bin/pytest tests/ -q` — 1037 passed, 6 failed. All
six failures are pre-existing and unrelated, confirmed by stashing the change and
reproducing the identical set: five `Chart/` CSV-discovery tests
(`test_chart_belief_all.py`, `test_chart_jain.py`) and
`test_greedy_phase7.py::test_phase7_comparison_envelope_matches_current_active_hybrid_sources`,
whose pinned blob hash for `IBG_Hybrid/kernel_controller.py` is stale — the
worktree and HEAD both hash to `81d0d35`, while the test still expects
`b940874` from before commit `1bb3407`. That stale pin is left for the user to
decide on, since it is a real drift signal rather than a threshold issue.

Also added: the Hybrid controller now reports the flow-generator response body
on stderr before re-raising, at `IBG_Hybrid/kernel_controller.py`. A bare 502
previously hid the originating `RouteForwardingError`. The original exception is
re-raised unchanged, so the no-rejection route contract still fails the slot with
no retry and no imputation.

Note for reruns: `IBG_Hybrid/runner.py` and `IBG_Hybrid/kernel_controller.py` are
both copied into the controller image only (`Dockerfile.controller`), not the
service image. Neither the 130-ms threshold nor the stderr diagnostic takes
effect under `--skip-build`.

Known failing test, unresolved by choice:
`test_greedy_phase7.py::test_phase7_comparison_envelope_matches_current_active_hybrid_sources`
whole-file-pins `IBG_Hybrid/kernel_controller.py` from `Greedy/comparison.py:102`.
It was already failing before this work because the posterior-mirror feature
(`HybridPosteriorMirrorPort`, the `posterior_mirror` field, changed cleanup
ordering) landed without re-running the Greedy Phase 3 audit. The stderr
diagnostic adds a second, behavior-neutral reason: the audited invariants — one
POST per slot, fail-before-belief-commit, close-once ownership — all still hold.
The pin was deliberately left stale so the posterior-mirror drift gets re-audited
rather than silently re-baselined.
