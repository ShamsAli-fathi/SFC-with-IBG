# IBG Testbed Roadmap

Work proceeds in order. A phase starts only after the previous phase's checks pass and `STATUS.md` records the result.

## Phase 0: Python environment

Status: complete.

- Create a repository-local Python 3.12 virtual environment at `.venv`.
- Install the reference simulation and test dependencies from `requirements.txt`.
- Verify imports for NumPy, pandas, SciPy, Matplotlib, scikit-learn, and pytest.
- Compile the Python sources without running the 48-experiment `IBG/main.py` entry point.

Gate: the clean virtual environment installs successfully, required imports work, and all existing Python sources compile.

## Phase 1: Protect the mathematics

Status: complete.

- Add deterministic characterization tests with fixed Python and NumPy seeds.
- Cover utility calculation, per-stage selection, embedding, belief updates, equilibrium, aggregate utility, SLA, and Jain fairness.
- Extract one configurable experiment slot from the monolithic runner without changing solver, utility, belief, or equilibrium behavior.

Gate: fixed fixtures reproduce the reference results before and after orchestration extraction.

## Phase 2: Introduce adapter boundaries

Status: not started.

- Define interfaces for replica discovery, traffic execution, observation collection, and result storage.
- Implement simulation-backed adapters first using the reference functions.
- Keep the legacy observation signal separate from measured latency telemetry.

Gate: the adapter-driven simulation matches the Phase 1 reference fixtures for the same seeds and inputs.

## Phase 3: Build the HTTP replica

Status: not started.

- Implement lightweight `/health` and `/process` endpoints.
- Expose stable stage/replica identity, flow and slot IDs, concurrent load, processing latency, and a belief-compatible observation.
- Configure hidden state and capacity as deterministic experiment parameters.

Gate: local tests verify identity, concurrency accounting, latency telemetry, observation format, and failure behavior.

## Phase 4: Build the flow generator

Status: not started.

- Accept complete three-stage routes from the controller.
- Admit placements sequentially, then run logical flows concurrently.
- Execute each flow through its selected stage endpoints and return per-hop telemetry only for selected replicas.

Gate: a local container-network test completes concurrent three-hop flows and returns complete, correctly correlated telemetry.

## Phase 5: Connect Kubernetes

Status: not started.

- Deploy three headless Services and three StatefulSets with stable replica ordinals.
- Add deterministic replica profiles, the flow-generator Deployment, the controller Job, and narrow discovery RBAC.
- Map Pod readiness and ordinal identity to solver-side `(stage, replica)` records without changing the solver.

Gate: a small cluster case with three stages, two replicas per stage, and three flows completes one controller slot successfully.

## Phase 6: Validate and scale

Status: not started.

- Compare simulation-backed and Kubernetes-backed runs using controlled seeds and replica profiles.
- Verify placement, asymmetric observations, belief evolution, utility, SLA, fairness, timing, and result metadata.
- Scale to three stages, 30 replicas per stage, and 15 logical flows per slot.

Gate: repeated target-scale runs complete without unsupported dataplane claims, and discrepancies from the reference behavior are measured and documented.
