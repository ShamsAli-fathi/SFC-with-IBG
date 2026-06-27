# Project Decisions

## Accepted direction

- Use WSL2 Ubuntu rather than a native-Windows-only workflow.
- Place the WSL distribution, Docker Desktop application, and Docker/cluster data on a spacious non-C drive where supported; small Windows components may remain on C.
- Use kind with one control-plane node and two worker nodes. kind uses containerd internally.
- Start with the decoupled IBG only. Preserve its mathematical and learning logic with minimal alterations.
- Small-scale target: three stages, 30 replicas per stage, and 15 logical flows per slot. Large-scale parameters come later.
- Represent stages with three StatefulSets of 30 Pods. Use stable ordinal identities but no persistent storage.
- Use tiny kernel-path HTTP services as CNF stand-ins. They expose health/processing behavior and observable latency/load.
- Run the Python IBG controller in the cluster with a ServiceAccount and narrowly scoped RBAC.
- Admit flows sequentially for placement, then exercise their selected paths concurrently to create contention.
- Preserve the existing metric concepts (aggregate utility, SLA violations, Jain fairness, runtime, and beliefs) while adding slot, Pod, node, placement, and latency metadata.

## Deliberately deferred

- DPDK, VPP, SR-IOV, hugepages, NUMA tuning, real telecom CNFs, and line-rate claims.
- Prometheus/Grafana until basic controller-provided telemetry works.
- Budgeted/coupled IBG migration.
- Large-scale testbed sizing and remote/dedicated Linux hardware.

These omissions still allow validation of Kubernetes orchestration, sequential placement, asymmetric observations, congestion effects, belief learning, utility, SLA behavior, fairness, and control-loop runtime.
