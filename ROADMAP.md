# IBG Testbed Expansion Roadmap

Work proceeds in order. A phase starts only after the previous phase's checks pass and `STATUS.md` records the result. This roadmap replaces the completed lightweight-migration roadmap as the active plan; it does not invalidate its Phase 6 simulation/Kubernetes parity evidence.

## Scope and terminology

The frozen baseline is the decoupled exact IBG testbed: the Python solver, utility grid, learning rule, equilibrium rule, FastAPI replica contract, flow-generator contract, and the supported three-flow/three-stage/five-replica validation remain the behavioral reference.

`Kernel` means the ordinary Linux socket/TCP/IP path already used by the HTTP workloads. The later comparison target is `dpdk-vpp`: VPP running in Linux user space with its approved DPDK I/O backend. VPP can also integrate with the Linux control plane or use non-DPDK interfaces, but that is not a third comparison arm in this roadmap. The immediate work is to make the Kernel baseline explicit; DPDK/VPP is a later target, not an implemented capability or a current validation claim.

In every mode, FastAPI remains responsible for `/health`, `/process`, replica identity, the legacy observation signal and likelihood, and application-level latency/concurrency telemetry. A datapath may forward traffic and contribute transport telemetry, but it must not generate observations, update beliefs, alter final-load legacy congestion, or cause unselected replicas to emit samples. This preserves the paper's asymmetric and partial-observation requirement.

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
- Define `kernel`, `vpp`, and future `dpdk` as explicit datapath modes behind traffic/telemetry adapters; do not add datapath branches to `IBG/claude.py`, replica utility functions, or learning code.
- Require each selected hop to retain slot, flow, stage, replica, endpoint, Pod, and node correlation. Observations remain exactly one legacy sample per selected hop; transport counters and latency are supplemental telemetry.
- Keep the current report factual: DPDK/VPP must remain labelled planned until its corresponding gate is verified.

Gate: architecture, decision, status, and roadmap handoffs describe the frozen mathematical baseline, the Kernel-versus-DPDK/VPP comparison, and coupled IBG as separate scopes.

## Phase 1: Controlled mathematical and parameter revisions

Status: planned.

Suggested Codex reasoning: `xhigh` — changes to the IBG mathematics, stochastic assumptions, utility/observation parameters, or equilibrium behavior can invalidate the established behavioral baseline.

- Accept mathematical or parameter changes only from explicit user instructions supplied during this phase. Record the intended formula, parameter domain/default, affected paths, and expected behavioral consequence before implementation.
- Keep each change small and independently reviewable. Do not combine an unverified mathematical revision with Kernel, DPDK/VPP, coupled-IBG, or unrelated infrastructure work.
- Add or update deterministic characterization fixtures for every intentional behavior change, including seeded stochastic effects where applicable. Preserve prior fixtures when they remain valid; deliberately update expected values only when the approved mathematical change requires it.
- Revalidate solver decisions, placement, observation/learning behavior, utility, SLA, fairness, equilibrium, reporting, and simulation/Kubernetes parity to the extent affected by each change.
- Update `ARCHITECTURE.md`, `DECISIONS.md`, `STATUS.md`, and the validation evidence whenever a revision changes a stable contract, accepted formula, default parameter, or supported comparison claim.

Gate: every approved revision has an explicit record, focused deterministic tests, documented expected behavior, and passing affected parity/regression checks. The resulting decoupled FastAPI/Kubernetes behavior becomes the new frozen Kernel baseline for later datapath comparison.

## Phase 2: Establish an explicit Kernel datapath baseline

Status: planned.

Suggested Codex reasoning: `high` — the existing HTTP path is functionally valid, but it needs a stable mode contract and evidence suitable for a later comparison.

- Expose the existing Kubernetes HTTP route as the named `kernel` datapath mode without changing route selection, FastAPI request semantics, or solver inputs.
- Add mode-aware traffic/telemetry adapter contracts and trace metadata so each completed slot records the active datapath and its mode-specific transport measurements.
- Verify that all traffic remains limited to controller-selected routes and that no mode-specific metric is converted into a legacy observation.
- Capture reproducible Kernel baseline runs at the supported configuration, including host, image, Kubernetes, and mode configuration needed for later comparison.

Gate: Kernel-mode runs reproduce simulation placements, legacy observations, beliefs, utilities, SLA, fairness, and equilibrium within the existing Phase 6 tolerance, while producing complete correlated Kernel telemetry.

## Phase 3: Design and prove the DPDK/VPP integration boundary

Status: planned.

Suggested Codex reasoning: `xhigh` — DPDK resource ownership plus VPP topology, interfaces, lifecycle, routing, and failure handling must be specified before changing runtime workloads.

- Audit and reserve the required DPDK resources on the target host: NIC ownership, IOMMU/VFIO, hugepages, CPU/NUMA placement, container privileges, and Kubernetes device resources. Define a safe rollback procedure.
- Select and document the DPDK/VPP topology, its DPDK I/O backend, and the Linux-facing interfaces for this host (for example, VPP forwarding between the flow generator and selected FastAPI replicas). Keep Kubernetes Service discovery and FastAPI application endpoints intact.
- Define lifecycle, readiness, configuration, cleanup, and failure behavior for DPDK/VPP components and their Kubernetes resources. `kernel` mode must remain independently runnable.
- Specify how DPDK/VPP counters and per-hop transport timing are correlated to the existing slot/flow/stage/replica route identity without expanding the observation set. Add focused control-boundary tests before requiring a cluster deployment.

Gate: the host preflight and documented DPDK/VPP design demonstrate safe resource ownership and can forward only a selected, correlated route to its FastAPI endpoint, report a clear readiness/failure state, and leave the legacy observation contract unchanged.

## Phase 4: Implement the DPDK/VPP-backed FastAPI route

Status: planned.

Suggested Codex reasoning: `xhigh` — this joins privileged DPDK resources, Kubernetes networking, VPP lifecycle, selected-route enforcement, and controller telemetry without authorization to alter IBG behavior.

- Add deployable DPDK/VPP resources and a `dpdk-vpp` traffic/telemetry adapter behind the existing complete-slot traffic port.
- Route each selected logical hop through the configured DPDK/VPP path and then to the same FastAPI `/process` contract. Do not replace FastAPI replicas with synthetic datapath observations.
- Preserve concurrent flows, sequential hops within a flow, route/identity validation, cleanup, and explicit failure rather than partial-success reporting.
- Emit DPDK/VPP-specific metadata only as supplemental telemetry, clearly separating it from FastAPI latency/concurrency and legacy observation fields.

Gate: a local and a small-cluster DPDK/VPP-mode run complete selected multi-hop routes, reject a DPDK/VPP or downstream failure cleanly, and retain complete per-hop correlation with no observations from idle replicas.

## Phase 5: Validate Kernel and DPDK/VPP modes against the IBG baseline

Status: planned.

Suggested Codex reasoning: `xhigh` — comparison must separate mathematical equivalence from genuine datapath timing and counter differences.

- Run controlled seeds at the supported three-flow/three-stage/five-replica configuration for simulation, `kernel`, and `dpdk-vpp` modes.
- Require parity for placements, utility grids, legacy signals/likelihoods, beliefs, utility, SLA, fairness, and equilibrium. Runtime and datapath telemetry may differ and must be reported rather than normalized away.
- Verify asymmetric/partial observation behavior directly: only selected replicas provide legacy observations in every mode.
- Publish a reproducible comparison command and a bounded evidence report; make no line-rate, hardware-offload, or DPDK claim from these results.

Gate: Kernel and DPDK/VPP modes are mathematically equivalent to the controlled simulation for the supported seeds, with explained and complete mode-specific telemetry and only the measured comparison claims supported by the hardware configuration.

## Future coupled-IBG track

Status: awaiting user requirements; not scheduled.

Coupled IBG is a separate mathematical and experimental scope. It must begin with an explicit problem definition, state/action and utility changes, observation and learning semantics, baselines, and acceptance fixtures. It must not be introduced as a datapath-mode option or silently alter the validated decoupled solver.
