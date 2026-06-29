# Project Decisions

## Accepted direction

- Use WSL2 Ubuntu for the development workflow; Windows supplies only the WSL2 host and its resource configuration.
- Run native Docker Engine inside Ubuntu under `systemd`; do not use Docker Desktop.
- Keep the Ubuntu distribution, source checkout, Docker data, and cluster data in the E-hosted WSL ext4 filesystem. Do not place Docker's data root on a Windows-mounted `/mnt/*` filesystem.
- Limit WSL2 to 10 GB RAM and 6 processors, with a 4 GB swap file on E.
- Use kind with one control-plane node and two worker nodes. kind uses containerd internally.
- Start with the decoupled IBG only. Preserve its mathematical and learning logic with minimal alterations.
- Small-scale target: three stages, 30 replicas per stage, and 15 logical flows per slot. Large-scale parameters come later.
- Represent stages with three StatefulSets of 30 Pods. Use stable ordinal identities but no persistent storage.
- Use tiny kernel-path HTTP services as CNF stand-ins. They expose health/processing behavior and observable latency/load.
- Run the Python IBG controller in the cluster with a ServiceAccount and narrowly scoped RBAC.
- Admit flows sequentially for placement, then exercise their selected paths concurrently to create contention.
- Preserve the existing metric concepts (aggregate utility, SLA violations, Jain fairness, runtime, and beliefs) while adding slot, Pod, node, placement, and latency metadata.
- Follow the ordered gates in `ROADMAP.md`. Complete and verify one phase before starting the next.
- Characterize the reference behavior before refactoring, then introduce simulation-backed adapter contracts before Kubernetes implementations.
- Treat measured HTTP latency and the legacy belief observation as separate fields initially. Replacing the legacy signal with measured latency requires an explicit, validated mathematical decision.
- Make the slot runner depend on explicit discovery, traffic, observation, and result-sink ports. Keep simulation implementations as the behavioral baseline for future infrastructure adapters.
- Apply observation likelihoods in the controller learning core; adapters collect observations but do not redefine local belief update or aggregation mathematics.

## Deliberately deferred

- DPDK, VPP, SR-IOV, hugepages, NUMA tuning, real telecom CNFs, and line-rate claims.
- Prometheus/Grafana until basic controller-provided telemetry works.
- Budgeted/coupled IBG migration.
- Large-scale testbed sizing and remote/dedicated Linux hardware.

These omissions still allow validation of Kubernetes orchestration, sequential placement, asymmetric observations, congestion effects, belief learning, utility, SLA behavior, fairness, and control-loop runtime.
