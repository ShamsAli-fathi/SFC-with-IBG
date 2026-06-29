# IBG Testbed Architecture

## Current system

`IBG/` is a working pure-Python simulation. Its active path is the small-scale, decoupled per-stage IBG: `IBG/main.py` constructs experiments, `IBG/runner.py` orchestrates one import-safe decoupled slot through adapter contracts, `IBG/claude.py` computes per-stage policy/utility grids, and `IBG/header.py` contains the replica, learning, embedding, and metric logic. Simulation adapters currently provide stage-scoped replica discovery, logical traffic execution, selected-replica observations, and reference CSV result storage. The separate budgeted/coupled code is not part of the current migration.

## Target testbed

```text
Windows 11
  -> WSL2 Ubuntu + native Docker Engine
    -> kind cluster
      -> 1 control-plane node
      -> 2 worker nodes
        -> Stage 1 StatefulSet: 30 HTTP CNF Pods
        -> Stage 2 StatefulSet: 30 HTTP CNF Pods
        -> Stage 3 StatefulSet: 30 HTTP CNF Pods
      -> Python IBG controller Pod
      -> lightweight flow-generator Pod
```

The three kind nodes are cluster machines; the three stage StatefulSets are workloads scheduled across the two workers. Each StatefulSet uses stable Pod ordinals to map directly to `(stage, replica)` and does not use persistent volumes.

Kubernetes schedules the long-running replica Pods onto worker nodes. The IBG solver does not reschedule Pods; it selects one already-running Pod endpoint per stage for each logical flow. A flow therefore becomes a three-hop route through selected stage Pods.

Development tools, source code, Docker Engine, and cluster state live inside the Ubuntu filesystem. Windows provides the WSL2 host only; Docker Desktop is not part of the testbed.

## Runtime flow

1. The controller discovers healthy replica Pods and their stable identities through the Kubernetes API.
2. A slot admits 15 logical flows in one randomized sequential order.
3. The unchanged decoupled solver selects one replica at each of the three stages for every flow.
4. The controller records/applies those assignments.
5. The flow generator exercises the selected three-Pod paths concurrently through lightweight HTTP requests.
6. Only selected replicas return per-request signals such as latency and concurrent load.
7. The controller updates replica beliefs using the existing learning rule and records utility, SLA, fairness, timing, placement, and belief results.

The HTTP Pods are test doubles, not real AMF/SMF/UPF functions. Their `/health` and `/process` behavior supplies real Kubernetes networking and configurable congestion without specialized dataplane hardware. Measured request latency and concurrency are recorded as testbed telemetry. The legacy belief-compatible observation remains a separate signal until a validated calibration allows measured latency to replace it without silently changing the IBG mathematics.

## HTTP replica contract

The Phase 3 replica service is a small FastAPI/Uvicorn application. `GET /health` reports readiness, stable stage/replica identity, Pod name, and current concurrency. `POST /process` accepts positive `slot_id` and `flow_id` values and returns the same identity plus admitted concurrency, measured processing latency, `legacy_signal`, and the four-state `legacy_likelihood` vector.

Replica identity, hidden state, capacity, base delay, and congestion delay are deterministic environment configuration. The service increments a shared request counter before simulated work, applies an additional delay for overlapping requests, and decrements the counter in a `finally` block. Its default observation source delegates to the reference `Replica.tasting()` model; it does not update beliefs locally.

## Migration boundary

Keep the solver and belief mathematics as pure Python. Add replaceable adapters for replica discovery, placement publication, HTTP traffic/telemetry, and result storage. This keeps the simulation logic testable without a cluster and lets testbed integration be verified separately.

The adapter boundary uses four ports: replica discovery, traffic execution, observation collection, and result storage. Simulation implementations delegate to the reference embedding and tasting behavior. The learning core applies collected likelihoods through the existing local-update and aggregation methods. Each observation carries the legacy signal separately from optional measured latency so future HTTP telemetry cannot silently alter belief mathematics.

The current `IBG/` files remain the behavioral reference. Migration proceeds through the gated phases in `ROADMAP.md`; cluster-specific code must not be embedded into `IBG/claude.py` or the replica utility and belief functions.
