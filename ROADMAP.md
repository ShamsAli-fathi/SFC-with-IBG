# IBG Testbed Roadmap

Work proceeds in order. A phase starts only after the previous phase's checks pass and `STATUS.md` records the result.

## Codex reasoning guidance

The suggested reasoning effort is a starting point for GPT-5.3-Codex or another Codex model that supports `low`, `medium`, `high`, and `xhigh`. Raise it one level when a phase exposes unexplained test failures, mathematical discrepancies, concurrency bugs, or unsafe infrastructure changes. Use the closest supported level if the selected model offers a different set.

## Phase 0: Python environment

Status: complete.

Suggested Codex reasoning: `low` — routine environment setup, dependency installation, and direct verification.

- Create a repository-local Python 3.12 virtual environment at `.venv`.
- Install the reference simulation and test dependencies from `requirements.txt`.
- Verify imports for NumPy, pandas, SciPy, Matplotlib, scikit-learn, and pytest.
- Compile the Python sources without running the 48-experiment `IBG/main.py` entry point.

Gate: the clean virtual environment installs successfully, required imports work, and all existing Python sources compile.

## Phase 1: Protect the mathematics

Status: complete.

Suggested Codex reasoning: `high` — preserving stochastic mathematical behavior requires careful fixture design and equivalence analysis.

- Add deterministic characterization tests with fixed Python and NumPy seeds.
- Cover utility calculation, per-stage selection, embedding, belief updates, equilibrium, aggregate utility, SLA, and Jain fairness.
- Extract one configurable experiment slot from the monolithic runner without changing solver, utility, belief, or equilibrium behavior.
- Replace the provisional myopic policy with memoized `BR_EIBG` continuation play that enforces one replica per stage.

Gate: fixed fixtures reproduce the reference results around orchestration extraction, a non-myopic fixture proves continuation reasoning, and a three-flow/five-replica/three-stage exact run completes successfully.

## Phase 2: Introduce adapter boundaries

Status: complete.

Suggested Codex reasoning: `high` — interface boundaries must preserve reference behavior while separating simulation and infrastructure concerns.

- Define interfaces for replica discovery, traffic execution, observation collection, and result storage.
- Implement simulation-backed adapters first using the reference functions.
- Keep the legacy observation signal separate from measured latency telemetry.

Gate: the adapter-driven simulation matches the Phase 1 reference fixtures for the same seeds and inputs.

## Phase 3: Build the HTTP replica

Status: complete.

Suggested Codex reasoning: `medium` — the service is bounded, with clear endpoint contracts and focused local tests.

- Implement lightweight `/health` and `/process` endpoints.
- Expose stable stage/replica identity, flow and slot IDs, concurrent load, processing latency, and a belief-compatible observation.
- Configure hidden state and capacity as deterministic experiment parameters.

Gate: local tests verify identity, concurrency accounting, latency telemetry, observation format, and failure behavior.

## Phase 4: Build the flow generator

Status: complete.

Suggested Codex reasoning: `high` — concurrent multi-hop execution, correlation, cleanup, and partial failures create subtle state and timing risks.

- Accept complete three-stage routes from the controller.
- Admit placements sequentially, then run logical flows concurrently.
- Execute each flow through its selected stage endpoints and return per-hop telemetry only for selected replicas.

Gate: a local container-network test completes concurrent three-hop flows and returns complete, correctly correlated telemetry.

## Phase 5: Connect Kubernetes

Status: complete.

Suggested Codex reasoning: `high` — StatefulSet identity, discovery, RBAC, readiness, and controller integration require coordinated infrastructure changes.

- Deploy three headless Services and three StatefulSets with stable replica ordinals.
- Add deterministic replica profiles, the flow-generator Deployment, the controller Job, and narrow discovery RBAC.
- Map Pod readiness and ordinal identity to solver-side `(stage, replica)` records without changing the solver.

Gate: a small cluster case with three stages, two replicas per stage, and three flows completes one controller slot successfully.

## Phase 6: Validate behavior

Status: complete.

Suggested Codex reasoning: `xhigh` — cross-backend validation must explain discrepancies and distinguish mathematical, stochastic, telemetry, and Kubernetes effects.

- Compare simulation-backed and Kubernetes-backed runs using controlled seeds and replica profiles.
- Use exact `BR_EIBG` in both backends.
- Verify placement, asymmetric observations, belief evolution, utility, SLA, fairness, timing, and result metadata.
- Repeat the supported case with three stages, five replicas per stage, and three flows, then quantify any discrepancies from the reference behavior.

Gate: repeated supported-size runs produce complete, comparable results, and discrepancies from the Python reference behavior are measured and documented.

## Post-roadmap operation

The completed testbed has a one-command observable experiment runner. It starts or reuses the kind environment, deploys the supported configuration, runs successive Kubernetes slots over one evolving belief state until the existing equilibrium condition is met, prints concise iteration progress and final replica state, and retains a detailed JSONL trace. This is an operating capability, not an additional migration phase.
