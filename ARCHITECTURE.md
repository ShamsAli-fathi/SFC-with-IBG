# IBG Testbed Architecture

## Current system

`IBG/` is a working pure-Python simulation. Its active path is the small-scale, decoupled per-stage IBG: `IBG/main.py` constructs experiments, `IBG/runner.py` orchestrates one import-safe decoupled slot through adapter contracts, `IBG/claude.py` computes per-stage utility grids and the exact memoized `BR_EIBG` continuation policy, and `IBG/header.py` contains the replica, learning, embedding, and metric logic. Simulation adapters provide stage-scoped discovery, embedding, reference observations, and CSV storage. Kubernetes adapters provide readiness-filtered discovery and complete-route traffic/telemetry while reusing the same solver, embedding, learning, equilibrium, and metric functions. The separate budgeted/coupled code is not part of the current migration.

## IBG Exact solver contract

For each decoupled stage, the solver first builds the existing belief-driven utility grid using 30 Monte Carlo quality samples per replica and one utility value for every possible load from 1 through the number of flows. `BR_EIBG` then solves the sequential one-replica-per-stage game exactly with respect to that sampled grid.

Each subgame is identified by the next player and the full vector of loads already assigned to the stage's replica slots. The solver branches over every active replica, recursively solves the continuation game, evaluates the current player's choice at its predicted final load, and selects the best continuation-consistent action. Subgames are memoized by load vector, and exact ties select the lowest replica ID for deterministic behavior. The former `backward_d_memoized_simple` name remains only as a compatibility wrapper around `br_eibg_exact`.

This one-of-M generalization is intentionally limited to small instances. With `N` flows and `M` active replicas, the number of cached load vectors through the terminal depth is `C(N+M, M)`. The supported three-flow/five-replica case has 56 states. Scaling beyond this exact testbed would require a different approximate algorithm and is outside the current project.

## Target testbed

```text
Windows 11
  -> WSL2 Ubuntu + native Docker Engine
    -> kind cluster
      -> 1 control-plane node
      -> 2 worker nodes
        -> Stage 1 StatefulSet: 5 HTTP CNF Pods
        -> Stage 2 StatefulSet: 5 HTTP CNF Pods
        -> Stage 3 StatefulSet: 5 HTTP CNF Pods
      -> Python IBG controller Pod
      -> lightweight flow-generator Pod
```

The three kind nodes are cluster machines; the three stage StatefulSets are workloads scheduled across the two workers. Each StatefulSet uses stable Pod ordinals to map directly to `(stage, replica)` and does not use persistent volumes.

Kubernetes schedules the long-running replica Pods onto worker nodes. The IBG solver does not reschedule Pods; it selects one already-running Pod endpoint per stage for each logical flow. A flow therefore becomes a three-hop route through selected stage Pods.

Development tools, source code, Docker Engine, and cluster state live inside the Ubuntu filesystem. Windows provides the WSL2 host only; Docker Desktop is not part of the testbed.

## Runtime flow

1. The controller discovers healthy replica Pods and their stable identities through the Kubernetes API.
2. A slot admits 3 logical flows in one randomized sequential order.
3. The exact decoupled `BR_EIBG` solver selects one replica at each of the three stages for every flow.
4. The controller records/applies those assignments.
5. The flow generator exercises the selected three-Pod paths concurrently through lightweight HTTP requests.
6. Only selected replicas return per-request signals such as latency and concurrent load.
7. The controller updates replica beliefs using the existing learning rule and records utility, SLA, fairness, timing, placement, and belief results.

The HTTP Pods are test doubles, not real AMF/SMF/UPF functions. Their `/health` and `/process` behavior supplies real Kubernetes networking and configurable congestion without specialized dataplane hardware. Measured request latency and concurrency are recorded as testbed telemetry. The legacy belief-compatible observation remains a separate signal until a validated calibration allows measured latency to replace it without silently changing the IBG mathematics.

## HTTP replica contract

The Phase 3 replica service is a small FastAPI/Uvicorn application. `GET /health` reports readiness, stable stage/replica identity, Pod name, and current concurrency. `POST /process` accepts positive `slot_id` and `flow_id` values and returns the same identity plus admitted concurrency, measured processing latency, `legacy_signal`, and the four-state `legacy_likelihood` vector.

Replica identity, hidden state, capacity, base delay, and congestion delay are deterministic environment configuration. The service increments a shared request counter before simulated work, applies an additional delay for overlapping requests, and decrements the counter in a `finally` block. Its default observation source delegates to the reference `Replica.tasting()` model; it does not update beliefs locally.

## Flow-generator contract

The Phase 4 flow generator is a separate FastAPI service. `POST /run-slot` accepts a slot ID and a nonempty set of complete three-hop routes supplied by the controller. Every route must contain stages 1, 2, and 3 in that order, with an explicit replica identity and HTTP endpoint for each hop.

The generator starts all logical flows concurrently, while each flow awaits its own hops sequentially. It calls only the selected replica endpoints, validates that each response matches the requested slot, flow, stage, and replica, and returns correlated per-hop telemetry containing slot, flow, stage, replica, Pod, endpoint, admitted concurrency, server and client latency, and the unchanged legacy observation fields. A downstream failure, identity mismatch, or correlation mismatch fails the slot request explicitly rather than returning partial results as if the slot had completed.

For local validation, the replica and flow-generator processes share one non-root container image and run on a private Docker Compose network. This exercises real service-to-service HTTP without introducing Kubernetes concerns before Phase 5.

## Kubernetes integration contract

The `ibg-testbed` namespace contains three headless Services and three two-replica StatefulSets for the Phase 5 gate, plus a ClusterIP flow-generator Service, one flow-generator Deployment, and a one-shot controller Job. The StatefulSet ordinal is converted to the one-based solver replica ID. A shared ConfigMap supplies deterministic solver and runtime profiles, so the controller and HTTP replica agree on state, capacity, delay, cost, congestion penalty, and processing delays.

The controller uses its mounted ServiceAccount token and CA with the existing HTTP client to list only namespace-scoped replica Pods. Discovery accepts only Running, Ready Pods and requires the exact ordinal set expected for every stage. Narrow RBAC permits `get` and `list` on Pods but does not permit Secret reads or Pod creation. Pod DNS through each headless Service becomes the selected hop endpoint; node and Pod identities are retained as placement metadata.

Simulation keeps its existing stage-by-stage observation path. For Kubernetes, the runner's optional slot-traffic port defers physical execution until all three stages have been placed. The flow generator then runs all complete routes, and its correlated hop telemetry is converted into the existing `Observation` contract before the unchanged learning and equilibrium logic runs.

## Migration boundary

Keep the solver and belief mathematics as pure Python. Add replaceable adapters for replica discovery, placement publication, HTTP traffic/telemetry, and result storage. This keeps the simulation logic testable without a cluster and lets testbed integration be verified separately.

The adapter boundary uses four ports: replica discovery, traffic execution, observation collection, and result storage. Simulation implementations delegate to the reference embedding and tasting behavior. The learning core applies collected likelihoods through the existing local-update and aggregation methods. Each observation carries the legacy signal separately from optional measured latency so future HTTP telemetry cannot silently alter belief mathematics.

The current `IBG/` files remain the behavioral reference. Migration proceeds through the gated phases in `ROADMAP.md`; cluster-specific code must not be embedded into `IBG/claude.py` or the replica utility and belief functions.
