# Project Status

Updated: 2026-07-12

## Completed

- Reviewed the paper draft and its hybrid-testbed proposal.
- Read the Python files directly under `IBG/` and identified the active decoupled simulation path.
- Established the lightweight target architecture and migration boundary.
- Chose a WSL-only development toolchain with native Docker Engine instead of Docker Desktop.
- Created the native ext4 checkout at `/home/shams/projects/SFC-with-IBG` and preserved the existing unstaged `requirements.txt` change.
- Installed Docker Engine 29.6.1, kubectl 1.35.6, kind 0.31.0, and Helm 4.2.0 inside Ubuntu.
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
- Added `scripts/run_experiment.py` as a one-command operator entry point that creates/reuses kind, rebuilds and loads the image, deploys and waits for workloads, launches a fresh experiment Job, prints readable live progress, and saves the detailed trace under ignored `runs/`.
- Switched slot-duration measurement to a monotonic clock after the first observable run exposed a WSL wall-clock jump in one iteration.
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
- Recreated the disposable `ibg` kind cluster after its stopped node containers returned with an unusable API following a WSL interruption, then reloaded the existing local runtime image.
- Verified `./scripts/run_experiment.py --csv 1 --flow 4 --stage 3 --replica 3 --max-iterations 100 --skip-build` live. All nine replica Pods and the flow generator became Ready, the controller Job reached equilibrium in 8 iterations, the JSONL trace completed, and all five requested CSV files were written successfully.
- Created and maintained the repository handoff documents as implementation progressed.
- Reset the active roadmap for the next expansion: begin with controlled user-directed mathematical and parameter revisions, then make the resulting validated FastAPI/Kubernetes route the explicit `kernel` mode, plan the later comparison path as DPDK/VPP, and leave coupled IBG awaiting a separate user-defined scope.

## Environment facts

- Host: Windows 11 Enterprise, Intel i7-10750H (6 cores/12 threads), approximately 16 GB RAM.
- Hardware virtualization is enabled.
- Ubuntu 24.04 runs under WSL2 with `systemd` enabled. Its `ext4.vhdx` is stored at `E:\WSL\Ubuntu-24.04`.
- The active checkout for this workspace is `/home/vhakami/Desktop/projects/vesal/SFC-with-IBG`. Earlier WSL checkout paths recorded in prior handoffs are historical and must be re-verified before use.
- Native Docker Engine is active under `systemd`, normal-user Docker access is configured, and its data root is `/var/lib/docker` inside the E-hosted ext4 filesystem.
- `%UserProfile%\.wslconfig` is active: WSL reports approximately 10 GB RAM, 6 processors, and 4 GB swap.
- The `ibg` kind cluster is running with one Ready control-plane node and two Ready workers. The `ibg-testbed` namespace currently has nine Ready replica Pods, one Ready flow-generator Pod, and a successfully completed four-flow/three-stage/three-replica experiment Job.
- C has limited free space; the WSL distribution and its Docker/cluster data are therefore kept on E.
- The current project root is a Git repository on branch `IBG`, with `origin` configured for `ShamsAli-fathi/SFC-with-IBG`.
- Docker Hub returned HTTP 403 for the initial Python base-image pull, so the local runtime image uses the official Azure Linux Python 3.12 base from Microsoft Container Registry. This is a packaging workaround, not a change to runtime behavior.

## Current state

The original decoupled exact Kubernetes migration is complete. Its supported three-stage, five-replica, three-flow target matches controlled simulation mathematics over three seeds; only expected infrastructure timing and Kubernetes-specific metadata differ. Phase 1 is specified but not implemented: hidden ordered states will cause load-conditioned processing latency/jitter, latency becomes the selected private signal, utility becomes linear in latency, end-to-end reporting deducts compatible link latency, and SLA uses latency thresholds. Phase 2 then calibrates all numerical values against predeclared state-specific zero-crossing ranges so bad replicas turn negative early and perfect replicas remain positive until high congestion. Calibration does not add rejection: the current solver still requires one replica per stage, so the supported range must retain a feasible option unless a later admission-policy change is explicitly approved. The calibrated FastAPI/Kubernetes route becomes the frozen `kernel` baseline before DPDK/VPP work.

## Next action

Implement Phase 1 in reviewable slices using provisional test profiles: state-conditioned latency, load-aware likelihoods, linear stage utility, end-to-end/link reporting, and latency-threshold SLA. Then execute Phase 2 with a reproducible calibration script: declare $N_{\mathrm{cal}}$ and target zero-crossing bands, fit latency curves, choose policy weights, run sensitivity/Monte Carlo checks, and validate representative points live. Do not introduce rejection, pair-dependent link optimization, DPDK/VPP resources, or coupled behavior implicitly.

## New-thread handoff prompt

> We are continuing Phase 1 of the Kernel-versus-DPDK/VPP expansion roadmap in `/home/vhakami/Desktop/projects/vesal/SFC-with-IBG` on branch `IBG`. Read `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`, and `STATUS.md`. Do not read or edit `Tutorial.md` unless explicitly requested; `Report.md` is opt-in only. Phase 1 implements hidden-state/load-conditioned processing latency, latency likelihoods, linear utility $R_k-\alpha_kq-c_k$, end-to-end link deduction, and latency SLA using provisional profiles. Phase 2 reproducibly calibrates parameters so $n_1^*<n_2^*<n_3^*<n_4^*$, with bad states negative early and perfect states positive until high congestion. The one-of-M solver does not reject negative choices; retain feasibility in the supported range unless rejection is separately authorized. Kernel baseline, DPDK/VPP, pair-dependent links, and coupled IBG follow later phases.
