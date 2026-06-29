# IBG Testbed Tutorial

This is the living report and usage guide for the SFC-with-IBG project. It is written for readers who know basic Python and terminal commands but may be new to WSL, Docker, Kubernetes, or the Indian Buffet Game implementation.

Updated through: Phase 4, 2026-06-29.

Whenever a phase adds commands, scripts, services, configuration, outputs, or troubleshooting knowledge, this file must be updated with it. A phase is not fully documented until a new reader can use its result from this guide.

## 1. What this project is

The project is converting an existing decoupled Indian Buffet Game (IBG) Python simulation into a lightweight Kubernetes testbed.

The important rule is that the IBG mathematics must stay stable. Kubernetes will eventually replace simulated discovery and traffic with real Pods and HTTP requests, but it must not silently redefine replica utility, policy selection, belief updates, equilibrium, or reporting.

The testbed models a service function chain with:

- Three ordered stages.
- Multiple replicas available at each stage.
- Logical flows that select one replica at every stage.
- Sequential placement decisions.
- Concurrent HTTP execution after the complete routes are selected.
- Observations from selected replicas only.

The HTTP replicas are controlled test services. They are not real AMF, SMF, UPF, DPDK, VPP, SR-IOV, or line-rate network functions.

## 2. The simplest mental model

Think of one flow as a customer moving through three counters:

```text
flow
  -> choose one Stage 1 replica
  -> choose one Stage 2 replica
  -> choose one Stage 3 replica
  -> collect observations
  -> update beliefs
  -> calculate metrics
```

The controller makes the choices. The replicas do not make placement decisions, and Kubernetes will not choose the IBG route. Kubernetes only runs the already-created services and gives them network identities.

Some useful terms:

| Term | Meaning in this project |
|---|---|
| Flow | One logical request that must pass through all three stages. |
| Stage | One position in the service chain: 1, 2, or 3. |
| Replica | One candidate service instance inside a stage. |
| Slot | One complete IBG iteration over all stages and flows. |
| Placement | The selected replica for each flow at each stage. |
| Congestion | The number of flows sharing a replica. |
| Belief | A four-value probability-like view of a replica's hidden state. |
| Observation | A signal and four-state likelihood returned by a selected replica. |
| Equilibrium | Beliefs changed by less than the configured threshold during a slot. |
| Adapter | A replaceable boundary between the solver and simulation or infrastructure. |

## 3. Current project report

The project currently has working results through Phase 4.

| Phase | Status | Main result |
|---|---|---|
| 0: Python environment | Complete | Project-local Python 3.12 virtual environment and dependencies. |
| 1: Protect mathematics | Complete | Deterministic characterization tests and an import-safe one-slot runner. |
| 2: Adapter boundaries | Complete | Simulation implementations for discovery, traffic, observations, and result storage. |
| 3: HTTP replica | Complete | Configurable FastAPI replica with health, processing, concurrency, latency, and legacy observation fields. |
| 4: Flow generator | Complete | Concurrent logical flows with sequential three-hop execution on a local container network. |
| 5: Connect Kubernetes | Not started | StatefulSets, Services, discovery, RBAC, and controller integration are still future work. |
| 6: Validate behavior | Not started | Controlled comparison between simulation and Kubernetes backends. |
| 7: Scale to target | Not started | Three stages, 30 replicas per stage, and 15 flows per slot. |

The most recent full verification passed 42 Python tests. The Phase 4 container gate completed three concurrent flows with three ordered hops per flow. The Stage 1 service reported admitted concurrency values `[1, 2, 3]`, proving that the flows overlapped.

No Kubernetes application manifests or Kubernetes-backed IBG adapters exist yet. The kind cluster configuration exists, but using it as the project backend belongs to Phase 5.

## 4. Where to work

Use an Ubuntu WSL terminal and work in the native Linux checkout:

```bash
cd /home/shams/projects/SFC-with-IBG
pwd
git branch --show-current
git status --short --branch
```

The expected project directory is:

```text
/home/shams/projects/SFC-with-IBG
```

The development branch is `IBG`. Do not use the older `/mnt/e/...` checkout for active work.

Windows provides the WSL host. Python, Git, Docker Engine, kind, kubectl, and the source checkout are intended to be used inside Ubuntu.

## 5. Phase 0 guide: prepare Python

### What Phase 0 provides

The `.venv` directory is a project-specific virtual environment. It is not global and affects only this repository when activated.

### Create or rebuild the environment

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For later sessions, only activation is normally required:

```bash
cd /home/shams/projects/SFC-with-IBG
source .venv/bin/activate
```

Your prompt may show `(.venv)`. Confirm the interpreter with:

```bash
which python
python --version
```

`which python` should point inside this repository's `.venv` directory.

### Verify the environment

```bash
python -m pip check
python -m compileall -q IBG testbed scripts
python -m pytest -q
```

What success looks like:

- `pip check` reports no broken requirements.
- `compileall` returns without an error.
- The test suite reports all tests passing.

## 6. Phase 1 guide: run and protect IBG Exact

### What Phase 1 provides

Phase 1 captured the current mathematical behavior in deterministic tests. It also extracted one simulation slot into `IBG/runner.py`, allowing later infrastructure work to call one iteration without rewriting the solver.

### Run the mathematical characterization tests

```bash
source .venv/bin/activate
python -m pytest -q tests/test_characterization.py tests/test_runner.py
```

These tests check utility, selection, embedding, belief updates, equilibrium, aggregate utility, SLA behavior, Jain fairness, and equivalence between the original orchestration and the extracted runner.

### Run the reference simulation safely

The simulation writes CSV reports into its current working directory. Use `/tmp` so an experiment does not overwrite or mix with repository data:

```bash
cd /home/shams/projects/SFC-with-IBG
PROJECT_ROOT="$PWD"
RUN_DIR=/tmp/ibg-exact-run
mkdir -p "$RUN_DIR"
cd "$RUN_DIR"
"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/IBG/main.py"
```

The current default is one experiment with three stages, four replicas per stage, and three flows. A single experiment can contain several slots because it repeats until equilibrium.

Typical output files are:

- `aggregate_utility.csv`
- `jain_index.csv`
- `replica_results.csv`
- `sla_violations.csv`
- `time.csv`

Return to the project afterward:

```bash
cd "$PROJECT_ROOT"
```

The default decoupled path is the supported reference. Do not enable or modify the budgeted/coupled path unless that work is explicitly added to scope.

## 7. Phase 2 guide: use the adapter-backed simulation

### What Phase 2 provides

The solver no longer needs to know whether replicas and observations come from a Python simulation or, later, Kubernetes. It talks through four ports:

1. Replica discovery.
2. Traffic execution.
3. Observation collection.
4. Result storage.

The current implementations are simulation-backed, so running `IBG/main.py` still behaves like the reference simulation. The adapters change structure, not mathematics.

### Verify adapter equivalence

```bash
source .venv/bin/activate
python -m pytest -q tests/test_adapters.py tests/test_runner.py
```

These tests prove that explicit simulation adapters produce the same placements, utilities, beliefs, metrics, and equilibrium result as the default runner for controlled seeds.

### When you would use these interfaces

Use `IBG/ports.py` when adding a new backend. A future Kubernetes implementation should satisfy the same contracts instead of placing Kubernetes API calls inside `IBG/claude.py` or `IBG/header.py`.

Use `MemoryResultSink` during tests when results should stay in memory. Use `CsvResultSink` when a run should produce the reference CSV layout.

## 8. Phase 3 guide: run one HTTP replica

### What Phase 3 provides

`testbed/cnf_service.py` runs one configurable replica as a FastAPI service.

It exposes:

- `GET /health` for readiness, identity, and current concurrency.
- `POST /process` for one flow request and its telemetry.

### Start the replica

In terminal A:

```bash
cd /home/shams/projects/SFC-with-IBG
source .venv/bin/activate
STAGE=1 \
REPLICA_ID=1 \
POD_NAME=stage-1-0 \
STATE=4 \
CAPACITY=2000 \
BASE_DELAY_MS=40 \
CONGESTION_DELAY_MS=10 \
python -m uvicorn testbed.cnf_service:app \
  --host 127.0.0.1 --port 8080
```

Keep terminal A open while testing.

The environment values mean:

| Variable | Purpose |
|---|---|
| `STAGE` | Position in the service chain. |
| `REPLICA_ID` | Stable replica number used by the IBG controller. |
| `POD_NAME` | Runtime identity returned in telemetry. |
| `STATE` | Deterministic hidden state from 1 through 4. |
| `CAPACITY` | Capacity used by the legacy observation model. |
| `BASE_DELAY_MS` | Delay applied even when there is no overlap. |
| `CONGESTION_DELAY_MS` | Additional delay for every overlapping request after the first. |

### Check health

In terminal B:

```bash
curl -sS http://127.0.0.1:8080/health
```

The JSON response should identify stage 1, replica 1, and Pod name `stage-1-0`.

### Send one flow request

```bash
curl -sS -X POST http://127.0.0.1:8080/process \
  -H 'content-type: application/json' \
  -d '{"slot_id":1,"flow_id":1}'
```

Important response fields:

- `concurrency`: active requests when this request was admitted.
- `processing_latency_ms`: measured time inside the replica service.
- `legacy_signal`: the reference observation signal.
- `legacy_likelihood`: the four-state likelihood used by the existing learning rule.

Measured latency and the legacy belief observation are intentionally separate. Latency does not silently replace the original learning signal.

Stop the server in terminal A with `Ctrl+C`.

### Run the focused tests

```bash
python -m pytest -q tests/test_cnf_service.py
```

## 9. Phase 4 guide: run the local three-hop testbed

### What Phase 4 provides

Phase 4 adds:

- Three HTTP replicas, one for each stage.
- One flow-generator service.
- A private Docker Compose network.
- A smoke script that sends three concurrent flows.

Each logical flow executes its own hops sequentially:

```text
Stage 1 -> Stage 2 -> Stage 3
```

Different flows execute concurrently, which creates observable contention.

### Start the testbed

```bash
cd /home/shams/projects/SFC-with-IBG
source .venv/bin/activate
docker compose -f deploy/local/compose.yaml \
  up --build --detach --wait
```

Inspect the services:

```bash
docker compose -f deploy/local/compose.yaml ps
```

You should see these four healthy services:

- `stage-1-0`
- `stage-2-0`
- `stage-3-0`
- `flow-generator`

### Run the acceptance smoke test

```bash
python scripts/phase4_smoke.py
```

Expected shape of the success message:

```text
phase4 smoke: 3 flows x 3 hops completed; stage-1 concurrency=[1, 2, 3]; ...
```

The exact elapsed time will vary. The important checks are:

- Three flows completed.
- Each flow returned exactly three hops.
- Every flow used stage order 1, 2, 3.
- The Stage 1 concurrency values were 1, 2, and 3.

### Stop and clean up

Always stop the temporary stack when finished:

```bash
docker compose -f deploy/local/compose.yaml down --remove-orphans
```

### Run the focused tests

```bash
python -m pytest -q tests/test_flow_generator.py
```

The flow generator rejects incomplete or out-of-order routes, duplicate flow IDs, downstream failures, replica identity mismatches, and slot/flow correlation mismatches.

## 10. Future phase guide

These phases are planned but are not usable yet. Do not invent commands or treat the kind configuration as a completed application deployment.

### Phase 5: Connect Kubernetes

Planned result:

- Three headless Services.
- Three StatefulSets with stable replica ordinals.
- Flow-generator Deployment.
- Controller Job.
- ServiceAccount and narrow discovery RBAC.
- Kubernetes-backed discovery and traffic integration.

The first gate will use three stages, two replicas per stage, and three flows for one controller slot.

### Phase 6: Validate behavior

This phase will compare controlled simulation-backed and Kubernetes-backed runs at small scale. It must explain differences in placements, observations, beliefs, metrics, timing, and metadata before scaling begins.

### Phase 7: Scale to target

Only after Phase 6 passes will the testbed scale to three stages, 30 replicas per stage, and 15 flows per slot.

## 11. IBG Exact: Python scripts and logic

“IBG Exact” is the name used in this tutorial for the preserved, active decoupled Python reference path. It means that later backends must reproduce this path's behavior. It does not bring the budgeted/coupled implementation into scope.

### 11.1 Active script map

| File | Responsibility |
|---|---|
| `IBG/main.py` | Creates experiments and replicas, repeats slots until equilibrium, and selects the default decoupled path. |
| `IBG/runner.py` | Runs one complete decoupled slot and returns a structured `SlotResult`. |
| `IBG/claude.py` | Builds utility grids and supplies the replica-selection policy. |
| `IBG/header.py` | Defines `Replica` and the reference utility, embedding, observation, belief, equilibrium, and fairness functions. |
| `IBG/ports.py` | Defines the four infrastructure-neutral adapter contracts and shared data objects. |
| `IBG/simulation_adapters.py` | Implements the ports using the original in-process simulation behavior and provides no-op/in-memory result sinks for tests. |
| `IBG/learning.py` | Applies collected observations through the existing local and aggregate belief-update rules. |
| `IBG/result_sinks.py` | Stores a completed slot using the reference CSV reporting layout. |
| `IBG/report.py` | Calculates SLA violations and writes or plots reference report data. |

The main execution path is:

```text
IBG/main.py
  -> create replicas
  -> IBG/runner.py: run_decoupled_slot
       -> discover stage replicas through an adapter
       -> IBG/claude.py: calculate utility and policy
       -> execute placement through an adapter
       -> collect selected-replica observations through an adapter
       -> IBG/learning.py: update beliefs
       -> IBG/header.py + IBG/report.py: calculate metrics/equilibrium
       -> result sink
  -> repeat until equilibrium
```

### 11.2 Replica model

Each `Replica` contains:

- `stage` and `replica`: stable logical identity.
- `belief`: four values representing uncertainty about hidden state.
- `delay`: a reference delay value.
- `cost`: retained for the budgeted model, not the active decoupled migration.
- `gamma`: strength of the congestion penalty.
- `state`: hidden state from 1 through 4.
- `capacity`: capacity used by the observation model.

The current utility kernel is:

```text
utility = 100 / (q * (1 + gamma * congestion)) - 5
```

Higher sampled delay `q`, higher congestion, or higher `gamma` lowers utility. The solver selects the best replica with positive utility for the current load state.

### 11.3 What happens inside one slot

`run_decoupled_slot` performs these steps:

1. Save the beliefs from the start of the slot for the equilibrium check.
2. Process stages in order from 1 to 3.
3. Shuffle the flow order for the current stage, matching the reference behavior.
4. Discover only replicas belonging to that stage.
5. Ask the solver for a policy and utility grid.
6. Embed every flow into its selected replica and record the assignment.
7. Add total and per-flow utility for the stage.
8. Collect an observation only for each selected replica/flow assignment.
9. Apply local belief updates, then aggregate observations for each selected replica.
10. After all stages, calculate SLA violations, Jain fairness, elapsed time, and equilibrium.
11. Send the structured result to the selected result sink.

The slot result includes placements by stage, complete routes by flow, utility grids, observations, aggregate utility, SLA violations, Jain fairness, equilibrium, and elapsed time.

### 11.4 Policy and utility logic

For every replica in the current stage, `backward_d_memoized_simple`:

1. Draws 30 delay-like samples using the replica's current belief.
2. Calculates expected utility for each possible congestion level from 1 to the number of flows.
3. Builds a utility table whose rows are replicas and columns are congestion levels.
4. Creates a policy lookup that chooses the positive-utility replica with the highest value for the current load state.

`embedding` walks through the shuffled flow list, asks the policy for a replica, updates the current replica loads, and appends the selected replica to that flow's route.

### 11.5 Observation and belief logic

Only selected replicas produce observations.

`Replica.tasting` combines replica capacity, congestion, and state-dependent random noise. `pdf_cal` converts the resulting value into:

- The most likely state, called the signal.
- A normalized four-state likelihood vector.

`local_update` combines the replica's current belief with that likelihood. `aggregation` then keeps 60% of the previous belief and mixes in 40% of the mean local observations for that replica.

Unselected replicas do not receive an observation and therefore do not change through this step.

### 11.6 Equilibrium and metrics

The current equilibrium rule compares every belief component before and after a slot. Equilibrium is reached only when every absolute change is below `0.04`.

The main recorded metrics are:

- Aggregate utility across replicas and stages.
- Utility accumulated per flow.
- SLA violations: a flow violates the current rule if any selected stage replica has hidden state 1 or 2.
- Jain fairness over accumulated per-flow utility.
- Slot runtime.
- Replica belief history.

### 11.7 Randomness and reproducibility

The simulation uses both Python's `random` module and NumPy's random generator. A reproducible experiment must seed both:

```python
import random
import numpy as np

random.seed(2026)
np.random.seed(2026)
```

The tests do this before comparing exact fixtures or old/new orchestration. A normal `IBG/main.py` run is stochastic and can produce different placements, observations, iteration counts, and metrics.

### 11.8 Files outside the active IBG Exact migration

`IBG/budgeted.py` and `IBG/header_b.py` belong to the budgeted/coupled path. They remain in the repository as reference material but are outside the current migration.

Do not “clean up” these files, old experiment helpers, generated CSV files, pickle files, or unrelated algorithm variants as part of testbed work.

## 12. Testbed Python additions

### `testbed/cnf_service.py`

This file turns one logical replica into an HTTP process. It reads stable identity and timing parameters from environment variables, counts active requests under an asynchronous lock, waits for a configurable delay, and returns both measured telemetry and the exact legacy observation format.

It updates no beliefs. Belief mutation remains a controller/IBG responsibility.

### `testbed/flow_generator.py`

This service accepts a complete set of controller-selected routes at `POST /run-slot`.

It starts all flows with `asyncio.gather`, so flows overlap. Inside each individual flow, it awaits Stage 1 before Stage 2 and Stage 2 before Stage 3. It calls only the selected endpoints and validates returned slot, flow, stage, and replica identity.

It returns per-hop Pod identity, endpoint, admitted concurrency, server processing latency, client request latency, and legacy observation fields.

### `scripts/phase4_smoke.py`

This is the Phase 4 operator check. It waits for the local flow generator, creates three complete routes, sends them in one slot request, and asserts route length, stage order, and real overlap at Stage 1.

### `deploy/local/Dockerfile`

This builds the shared non-root runtime image for the replica and flow-generator services. It installs only runtime dependencies from `requirements-runtime.txt` and runs as numeric user `10001`.

### `deploy/local/compose.yaml`

This defines the three configured replica services and the flow generator on one private container network. It also defines health checks and exposes only the flow generator on host port `18081`.

## 13. Test suite map

| Test file | What it protects |
|---|---|
| `tests/test_characterization.py` | Utility, solver, embedding, observations, belief updates, metrics, and equilibrium fixtures. |
| `tests/test_runner.py` | Equivalence of the extracted slot and original orchestration; safe import behavior. |
| `tests/test_adapters.py` | Adapter contracts and equivalence with simulation behavior. |
| `tests/test_cnf_service.py` | HTTP replica identity, concurrency, latency, configuration, observation parity, and cleanup. |
| `tests/test_flow_generator.py` | Concurrent flows, ordered hops, selected endpoints, correlation, validation, and failures. |

Run everything before declaring a change complete:

```bash
source .venv/bin/activate
python -m pytest -q
```

## 14. Common troubleshooting

### `python` or a package is not found

Activate the project environment:

```bash
cd /home/shams/projects/SFC-with-IBG
source .venv/bin/activate
```

If `.venv` does not exist, follow Phase 0 again.

### Docker says permission denied

Confirm Docker is active and your user can access it:

```bash
systemctl status docker --no-pager
docker info
```

Do not switch the project to Docker Desktop as a workaround; the accepted architecture uses native Docker Engine inside WSL.

### Port 8080 or 18081 is already in use

Stop an old Uvicorn process with `Ctrl+C`, then clean up Compose:

```bash
docker compose -f deploy/local/compose.yaml down --remove-orphans
```

### A Compose service is not healthy

Inspect state and logs:

```bash
docker compose -f deploy/local/compose.yaml ps
docker compose -f deploy/local/compose.yaml logs --tail 100
```

Then clean up before retrying.

### Docker Hub returns HTTP 403

The current Dockerfile already uses the Azure Linux Python 3.12 base from Microsoft Container Registry because Docker Hub rejected the original base-image pull. Do not change registries unless there is a verified reason.

### The reference simulation created CSV files in the repository

Do not overwrite or casually delete existing experiment data. Run future experiments from a dedicated directory under `/tmp`, as shown in Phase 1.

### The kind cluster exists but kubectl cannot connect

The cluster's node containers did not automatically restore the Kubernetes API after a previous WSL restart. Phases 0 through 4 do not need the cluster. Cluster recovery and application deployment belong to Phase 5.

## 15. How to maintain this tutorial

Whenever a phase advances, update this file in the same change. At minimum:

1. Update the date and current phase report.
2. Add the exact commands a user should run.
3. Explain every new service, script, manifest, and configuration file.
4. Explain required inputs and expected output fields.
5. Add focused tests and the acceptance-gate command.
6. Add cleanup and rollback instructions.
7. Add troubleshooting learned during implementation.
8. Mark future instructions clearly; never present planned commands as working commands.
9. Preserve the “IBG Exact” chapter when code movement affects the reference path.
10. Keep `ROADMAP.md`, `STATUS.md`, `ARCHITECTURE.md`, and `DECISIONS.md` consistent with this guide.

The goal is simple: a new reader should be able to understand what exists, run it safely, recognize success, and know what is not implemented yet.
