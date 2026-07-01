# Project Decisions

## Accepted direction

- Use WSL2 Ubuntu for the development workflow; Windows supplies only the WSL2 host and its resource configuration.
- Run native Docker Engine inside Ubuntu under `systemd`; do not use Docker Desktop.
- Keep the Ubuntu distribution, source checkout, Docker data, and cluster data in the E-hosted WSL ext4 filesystem. Do not place Docker's data root on a Windows-mounted `/mnt/*` filesystem.
- Limit WSL2 to 10 GB RAM and 6 processors, with a 4 GB swap file on E.
- Use kind with one control-plane node and two worker nodes. kind uses containerd internally.
- Start with the decoupled IBG only. Preserve its mathematical and learning logic with minimal alterations.
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
- Characterize the reference behavior before refactoring, then introduce simulation-backed adapter contracts before Kubernetes implementations.
- Treat measured HTTP latency and the legacy belief observation as separate fields initially. Replacing the legacy signal with measured latency requires an explicit, validated mathematical decision.
- Make the slot runner depend on explicit discovery, traffic, observation, and result-sink ports. Keep simulation implementations as the behavioral baseline for future infrastructure adapters.
- Apply observation likelihoods in the controller learning core; adapters collect observations but do not redefine local belief update or aggregation mathematics.
- Implement the HTTP replica as a small FastAPI/Uvicorn service with environment-provided stable identity and experiment parameters.
- Count active requests inside each replica service and report the admitted concurrency and measured server processing latency. Always release the counter on success or failure.
- Generate `legacy_signal` and `legacy_likelihood` through the reference tasting model while leaving belief mutation exclusively in the controller.
- Make the flow generator accept complete controller-selected routes rather than perform placement itself.
- Start logical flows concurrently but await the three selected hops of each individual flow in stage order.
- Validate returned slot/flow correlation and replica identity, then fail the slot request on downstream HTTP, payload, correlation, or identity errors; do not present partial telemetry as a completed slot.
- Correlate every hop with slot, flow, stage, replica, Pod, and endpoint metadata while retaining server latency, client latency, concurrency, and legacy observation fields separately.
- Use one non-root runtime image for the local replica and flow-generator services; keep Docker Compose packaging local to Phase 4 and defer Kubernetes manifests to Phase 5.
- Use exact continuation play for the decoupled IBG: branch over every available replica at each player/load-vector subgame, score choices at their predicted final loads, and memoize subgames.
- Enforce exactly one replica per stage in `BR_EIBG`; the paper's binary choose/skip pseudocode is generalized to the formal one-of-M SFC action constraint.
- Keep the existing belief-driven 30-sample utility grid, utility kernel, learning, embedding, equilibrium, and reporting logic around the corrected solver. “Exact” refers to the SPNE recursion over that sampled grid.
- Break exact utility ties by lowest replica ID so repeated seeded runs remain deterministic.
- Keep `BR_EIBG` as the project's exact small-instance policy. A scalable approximation would be a separate future project and is not part of this roadmap.
- Derive one-based solver replica IDs from zero-based StatefulSet Pod ordinals and require the full expected Ready ordinal set before solving a stage.
- Store the Phase 5 deterministic replica profiles in one ConfigMap mounted by both replicas and the controller.
- Use the existing HTTP client with the in-cluster ServiceAccount token and CA for namespace-scoped Pod discovery; grant only Pod `get` and `list` permissions.
- Keep simulation observations stage-local, but let Kubernetes defer physical traffic until all stage placements form complete routes; convert returned hop telemetry into the existing observation contract before applying unchanged learning logic.
- Preserve final assigned replica load as the congestion input to the legacy observation model in both backends; keep actual HTTP admission concurrency as separate Kubernetes telemetry.
- Derive controlled observation samples from a deterministic replica seed plus slot, flow, and final congestion so observation generation does not disturb the solver's NumPy stream.
- Validate the supported three-stage/five-replica/three-flow case over seeds 2050, 2051, and 2052, requiring mathematical parity while treating Kubernetes timing and infrastructure metadata as backend-specific.
- Apply the one-shot controller Job only after StatefulSet and flow-generator rollouts complete; do not race validation traffic against endpoint replacement.
- Provide one post-roadmap experiment launcher that creates/reuses kind, rebuilds and loads the runtime image, deploys and waits for workloads, starts a fresh controller Job, and follows its logs.
- In observable experiment mode, retain one evolving replica/belief state across slots and stop only on the existing equilibrium test, bounded by an explicit maximum iteration count.
- Emit compact live iteration output from structured JSONL events, retain the complete local trace under ignored `runs/`, and keep the Phase 6 one-slot comparison output compatible.
- Measure slot duration with a monotonic clock; wall-clock timestamps are not valid elapsed-time sources under WSL clock correction.
- Let the experiment launcher accept positive flow, stage, and per-stage replica counts, while retaining three flows, three stages, and five replicas as the default and only Phase 6 parity-validated target.
- Generate experiment stage Services, StatefulSets, and the shared profile ConfigMap from the requested dimensions; remove stale higher-numbered stage resources between runs.
- Preserve all validated profiles exactly and deterministically extend new stage/replica identities from the validated profile templates with unique observation seeds. This changes experiment configuration only, not `BR_EIBG` or its mathematics.
- Require every flow-generator route to contain the same positive contiguous stage sequence beginning at stage 1, rather than embedding a three-stage assumption in the traffic contract.
- Keep Kubernetes CSV export host-side: `--csv 1` converts the completed structured trace into the five legacy report files under `/mnt/e/WSL/Ubuntu-24.04/CSV`, avoiding cluster volumes and preserving the default JSONL-only behavior when disabled.

## Deliberately deferred

- DPDK, VPP, SR-IOV, hugepages, NUMA tuning, real telecom CNFs, and line-rate claims.
- Prometheus/Grafana until basic controller-provided telemetry works.
- Budgeted/coupled IBG migration.
- Large-scale testbed sizing and remote/dedicated Linux hardware.

These omissions still allow validation of Kubernetes orchestration, sequential placement, asymmetric observations, congestion effects, belief learning, utility, SLA behavior, fairness, and control-loop runtime.
