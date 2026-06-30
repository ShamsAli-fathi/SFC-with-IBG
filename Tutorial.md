# IBG Testbed Tutorial

This is the living report and usage guide for the SFC-with-IBG project. It is written for readers who know basic Python and terminal commands but may be new to WSL, Docker, Kubernetes, or the Indian Buffet Game implementation.

Updated through: completed Phase 6 and observable equilibrium operation, 2026-06-30.

This file is user-directed. Agents must not read or edit it unless the user explicitly requests that action in the current task.

## 1. What this project is

The project is converting an existing decoupled Indian Buffet Game (IBG) Python simulation into a lightweight Kubernetes testbed.

The important rule is that the IBG mathematics must stay stable. Kubernetes now replaces simulated discovery and traffic with real Pods and HTTP requests, but it does not redefine replica utility, policy selection, belief updates, equilibrium, or reporting.

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

The migration roadmap is complete through Phase 6.

| Phase | Status | Main result |
|---|---|---|
| 0: Python environment | Complete | Project-local Python 3.12 virtual environment and dependencies. |
| 1: Protect mathematics | Complete | Exact memoized `BR_EIBG`, deterministic characterization tests, and an import-safe one-slot runner. |
| 2: Adapter boundaries | Complete | Simulation implementations for discovery, traffic, observations, and result storage. |
| 3: HTTP replica | Complete | Configurable FastAPI replica with health, processing, concurrency, latency, and legacy observation fields. |
| 4: Flow generator | Complete | Concurrent logical flows with sequential three-hop execution on a local container network. |
| 5: Connect Kubernetes | Complete | StatefulSets, Services, deterministic profiles, discovery/RBAC, flow generator, and one-slot controller integration. |
| 6: Validate behavior | Complete | Three controlled supported-size Kubernetes runs match the simulation mathematics exactly. |

The most recent full verification passed 63 Python tests. The exact-solver gate completed three flows across three stages with five replicas per stage. The Phase 4 container gate completed three concurrent flows with three ordered hops per flow, and the Stage 1 service reported admitted concurrency values `[1, 2, 3]`, proving that the flows overlapped.

The Phase 5 bring-up gate used two replicas per stage and completed all nine placements and observations. Phase 6 then expanded the live kind testbed to five replicas per stage. For seeds 2050, 2051, and 2052, all 27 placements, sampled utility values, observations, beliefs, utility metrics, SLA results, Jain fairness values, and equilibrium results matched the controlled simulation. Kubernetes averaged about 0.309 seconds per validation slot versus 0.051 seconds in-process; that expected difference is infrastructure overhead, not mathematical drift.

The post-roadmap operator command also runs one evolving Kubernetes experiment until equilibrium. The verified seed-2050 run reached equilibrium in 9 slots, printed every flow order, placement, observation, metric, and belief-change maximum, and saved the initial and final state in an 11-event JSONL trace.

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

Phase 1 captured the mathematical behavior in deterministic tests and extracted one simulation slot into `IBG/runner.py`. The original provisional policy was later corrected: `IBG/claude.py` now implements the real memoized `BR_EIBG` continuation algorithm while keeping the surrounding utility, learning, equilibrium, and reporting pipeline intact.

### Run the mathematical characterization tests

```bash
source .venv/bin/activate
python -m pytest -q tests/test_characterization.py tests/test_runner.py
```

These tests check utility, selection, embedding, belief updates, equilibrium, aggregate utility, SLA behavior, Jain fairness, and equivalence between the original orchestration and the extracted runner.

Run the exact-solver size gate directly with:

```bash
python -m pytest -q tests/test_runner.py \
  -k three_stages_with_three_flows_and_five_replicas
```

This gate uses three flows, five replicas in each of three stages, and verifies all nine placements and selected-replica observations.

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

The solver does not need to know whether replicas and observations come from Python simulation objects or Kubernetes Pods. The original adapter boundary has four ports:

1. Replica discovery.
2. Traffic execution.
3. Observation collection.
4. Result storage.

Kubernetes adds an optional slot-traffic port. Simulation still collects its observations stage by stage. Kubernetes first records all three stage placements, uses the slot-traffic port to execute the resulting complete routes, and then converts returned hop telemetry into the same `Observation` objects used by the learning core. The adapters change infrastructure and timing boundaries, not the solver mathematics.

### Verify adapter equivalence

```bash
source .venv/bin/activate
python -m pytest -q tests/test_adapters.py tests/test_runner.py
```

These tests prove that explicit simulation adapters produce the same placements, utilities, beliefs, metrics, and equilibrium result as the default runner for controlled seeds.

### When you would use these interfaces

Use `IBG/ports.py` when adding a new backend. The Kubernetes implementation satisfies these contracts instead of placing Kubernetes API calls inside `IBG/claude.py` or `IBG/header.py`.

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

## 10. Phase 5 guide: connect Python to kind

### What Phase 5 provides

The Kubernetes application runs in namespace `ibg-testbed`:

| Component | Kubernetes object | Purpose |
|---|---|---|
| Stage 1 | Headless Service + five-replica StatefulSet | Stable Stage 1 replica identities and direct Pod DNS. |
| Stage 2 | Headless Service + five-replica StatefulSet | Stable Stage 2 replica identities and direct Pod DNS. |
| Stage 3 | Headless Service + five-replica StatefulSet | Stable Stage 3 replica identities and direct Pod DNS. |
| Flow generator | ClusterIP Service + one-replica Deployment | Receives complete routes and drives concurrent HTTP traffic. |
| IBG controller | ServiceAccount + one-shot Job | Runs controlled validation slots or a bounded experiment until equilibrium. |
| Profiles | ConfigMap | Gives replicas and the controller the same deterministic parameters. |
| Discovery permission | Role + RoleBinding | Allows the controller to read Pod identity/readiness without broader cluster access. |

The historical Phase 5 bring-up gate deliberately used two replicas per stage and three flows. The current manifests represent the completed Phase 6 target: five replicas per stage and three flows.

### How the Python-to-container connection actually works

There are three distinct connections. Keeping them separate makes the system much easier to reason about.

```text
1. Image delivery

repository files
  -> docker build
  -> local image: ibg-testbed:phase6
  -> kind load docker-image
  -> containerd image store inside each kind node

2. Kubernetes control traffic

Python controller Job
  -> HTTPS request with ServiceAccount token
  -> Kubernetes API server
  -> list Ready replica Pods and their node/identity metadata

3. Testbed data traffic

Python controller
  -> HTTP POST complete routes to flow-generator Service
  -> flow-generator Pod
  -> HTTP POST to selected StatefulSet Pod DNS names
  -> replica telemetry
  -> flow generator
  -> controller observations
  -> existing IBG belief and metric logic
```

The host's `.venv` Python process is not reaching into Kubernetes containers. The controller is itself a Python process inside a container created by the Kubernetes Job. The same image contains `IBG/` and `testbed/`. Kubernetes turns that image into three roles by changing the container command and environment:

- StatefulSets use the image's default command and run `testbed.cnf_service`.
- The Deployment overrides the command to run `testbed.flow_generator`.
- The Job overrides the command to run `testbed.kubernetes_controller`.

The Job command is:

```text
python3 -m testbed.kubernetes_controller
```

kind nodes are Docker containers, but Pods inside those nodes are managed by the node's containerd runtime. A normal local `docker build` puts an image only in Docker Engine's image store. `kind load docker-image` copies that image into every kind node's containerd store. This is why the manifests can use `imagePullPolicy: Never`: no external registry is needed for this local testbed.

The `kubectl` commands run from WSL and the Python controller both call the Kubernetes API, but they authenticate differently. `kubectl` uses the user credentials in the local kubeconfig. The controller uses its mounted ServiceAccount credential. Neither one connects to a replica through the Docker socket.

When Kubernetes starts the controller Job, it automatically provides:

- `KUBERNETES_SERVICE_HOST` and the HTTPS API port.
- A token for the namespace-owned `ibg-controller` ServiceAccount.
- The cluster CA certificate used to verify the API server.

`KubernetesApi` in `testbed/kubernetes_adapters.py` reads those values and uses `httpx` to call the Kubernetes API. Its label query asks for Pods with `app.kubernetes.io/name=ibg-replica` and the current `ibg.stage` label. It accepts only Running and Ready Pods.

The profile ConfigMap is mounted as `/etc/ibg/profiles.json` in both replica and controller containers. The downward API also places each StatefulSet Pod's own name in `POD_NAME`. This lets separate Python processes agree on identity and experiment parameters without importing state from the host process.

The RoleBinding makes that identity's permissions namespace-scoped. The Role permits only Pod `get` and `list` in `ibg-testbed`. The API server authenticates the token, checks the RoleBinding, and either returns the Pod list or rejects the request. The controller does not need permission to create Pods, modify StatefulSets, or read Secrets.

Each StatefulSet Pod has a stable zero-based ordinal:

```text
stage-2-0 -> solver replica 1
stage-2-1 -> solver replica 2
```

The adapter adds one because the IBG model uses one-based replica IDs. For a selected Stage 2 replica 2, it constructs this endpoint:

```text
http://stage-2-1.stage-2.ibg-testbed.svc.cluster.local:8080
```

The first name is the Pod, `stage-2` is the headless Service, and `ibg-testbed` is the namespace. CoreDNS resolves that stable name directly to the Pod IP. Kubernetes decides which worker node runs the Pod; the IBG solver decides which already-running Pod endpoint a flow uses. Those are different decisions.

After all placements are known, the controller sends one `/run-slot` request to `http://flow-generator:8080`. The normal ClusterIP Service resolves to the flow-generator Pod. The generator starts the three flows concurrently, but each flow awaits Stage 1, then Stage 2, then Stage 3. It calls only the selected StatefulSet Pod names. Returned latency, concurrency, identity, signal, and likelihood fields travel back to the controller and become the existing `Observation` objects. The unchanged learning core then updates beliefs and calculates equilibrium and metrics.

### Check the cluster baseline

From the repository root:

```bash
kind get clusters
kubectl config current-context
kubectl cluster-info
kubectl get nodes -o wide
kubectl get pods -A
```

Expected baseline:

- Current context is `kind-ibg`.
- One control-plane node and two worker nodes are Ready.
- CoreDNS and the other `kube-system` Pods are Running.

### Build and load the application image

```bash
cd /home/shams/projects/SFC-with-IBG
docker build \
  --tag ibg-testbed:phase6 \
  --file deploy/local/Dockerfile .

kind load docker-image ibg-testbed:phase6 --name ibg
```

Run both commands again after changing Python source that must run inside the cluster. Rebuilding without reloading leaves kind using the older image stored in its nodes.

### Deploy the application

For a fresh namespace:

```bash
kubectl apply -k deploy/kubernetes
```

Wait for the long-running workloads:

```bash
kubectl rollout status statefulset/stage-1 \
  --namespace ibg-testbed --timeout=180s
kubectl rollout status statefulset/stage-2 \
  --namespace ibg-testbed --timeout=180s
kubectl rollout status statefulset/stage-3 \
  --namespace ibg-testbed --timeout=180s
kubectl rollout status deployment/flow-generator \
  --namespace ibg-testbed --timeout=180s
```

The base Kustomization intentionally contains only long-running resources. It does not contain the controller Job. Wait for all 15 replicas and the flow generator before applying the Job so validation traffic cannot race a rollout.

Apply and verify the controlled Phase 6 Job:

```bash
kubectl delete job ibg-controller \
  --namespace ibg-testbed --ignore-not-found
kubectl apply -f deploy/kubernetes/controller-job.yaml

kubectl wait --namespace ibg-testbed \
  --for=condition=complete job/ibg-controller --timeout=180s

kubectl get pods --namespace ibg-testbed -o wide
kubectl logs --namespace ibg-testbed job/ibg-controller
```

Success includes three log lines beginning with:

```text
PHASE6_RESULT=
```

Each JSON result contains:

- Nine placements: three flows multiplied by three stages.
- Pod, node, replica, and endpoint metadata for every placement.
- Three complete flow records, each with three correlated hops.
- Nine selected-replica observations.
- Updated beliefs, aggregate utility, SLA violations, Jain fairness, equilibrium, and elapsed time.

The verified Job completed seeds 2050, 2051, and 2052 with all nine placements and observations in every slot. Shared selected replicas reported admitted concurrency of 2 in two runs, proving that concurrent flows overlapped inside the cluster.

### Run the focused tests

```bash
source .venv/bin/activate
python -m pytest -q tests/test_kubernetes_adapters.py
python -m pytest -q
```

The first command covers profile loading, StatefulSet ordinal mapping, readiness rejection, route construction, and telemetry conversion. The full suite currently contains 63 passing tests.

### Inspect the discovery permissions

```bash
kubectl auth can-i list pods \
  --as=system:serviceaccount:ibg-testbed:ibg-controller \
  --namespace=ibg-testbed

kubectl auth can-i get secrets \
  --as=system:serviceaccount:ibg-testbed:ibg-controller \
  --namespace=ibg-testbed
```

The first command should say `yes`; the second should say `no`.

### Repeat only the validation Job

A completed Job does not rerun when `kubectl apply` sees it again. Delete and recreate just that Job:

```bash
kubectl delete job ibg-controller \
  --namespace=ibg-testbed --ignore-not-found
kubectl apply -f deploy/kubernetes/controller-job.yaml
kubectl wait --namespace=ibg-testbed \
  --for=condition=complete job/ibg-controller --timeout=180s
kubectl logs --namespace=ibg-testbed job/ibg-controller
```

### Remove the Kubernetes application

This removes the project namespace and its application workloads, but leaves the kind cluster itself intact:

```bash
kubectl delete -k deploy/kubernetes --wait=true
```

Do not run `kind delete cluster` unless deleting the whole local cluster is intentional.

### Verify Phase 6 simulation/Kubernetes parity

The controller Job emits the detailed Kubernetes summaries consumed by the comparison tool. Compare all three results with controlled simulation runs using:

```bash
kubectl logs --namespace ibg-testbed job/ibg-controller \
  | .venv/bin/python scripts/phase6_compare.py --kubernetes-log -
```

Success prints `PHASE6_COMPARISON=<json>` and exits with status 0. The verified comparison matched all 27 placements and observation signals and reported `mathematical_max_abs: 0.0`. Kubernetes-specific timing, Pod, node, endpoint, admitted-concurrency, and measured-latency fields are validated for completeness but are not required to equal in-process simulation timing.

### Run one observable experiment until equilibrium

For normal operation, use the one-command launcher from the repository root:

```bash
./scripts/run_experiment.py
```

It performs the complete sequence:

1. Create the three-node `ibg` kind cluster if it does not exist.
2. Build `ibg-testbed:phase6` from the current source.
3. Load the image into every kind node.
4. Apply the base Kubernetes resources.
5. Restart and wait for all three StatefulSets and the flow-generator Deployment.
6. Create a fresh `ibg-experiment` controller Job.
7. Poll and render the controller log until the Job exits.
8. Verify Job completion and save the complete structured trace under `runs/`.

The default seed is 2050 and the safety limit is 100 iterations. Change them with:

```bash
./scripts/run_experiment.py --seed 2051 --max-iterations 50
```

When the current image is already loaded and the source has not changed, skip the rebuild and workload restart:

```bash
./scripts/run_experiment.py --skip-build
```

Do not use `--skip-build` after changing `IBG/` or `testbed/`; the controller would otherwise run the older image already stored in kind.

The live output begins with the static state and initial beliefs of all 15 replicas. Every iteration then prints:

- Flow order at each stage.
- The selected replica for each flow and stage.
- Observation congestion, signal, and measured processing latency.
- Aggregate utility, SLA violations, Jain fairness, slot duration, and maximum belief change.
- Whether the existing equilibrium rule succeeded.

At equilibrium it prints the final state of every replica, replacing the old need to add a manual `for key, value in replica_list.items()` loop. Slot duration uses a monotonic clock, so a WSL wall-clock adjustment cannot create an impossible elapsed time.

The `runs/ibg-experiment-<timestamp>.jsonl` file contains one `run_started` event, one `iteration_completed` event per slot, and one `run_completed` event. It retains the full placements, observations, utility grids, traffic telemetry, beliefs before and after each slot, and final replica state. `runs/` is intentionally ignored by Git.

The verified seed-2050 run reached equilibrium in 9 iterations. Its final trace contained 11 events, and corrected slot durations ranged from approximately 0.307 to 0.394 seconds.

There is no scaling phase. The exact load-vector solver is intentionally limited to the supported small instance.

## 11. IBG Exact: Python scripts and logic

“IBG Exact” is the name used in this tutorial for the preserved, active decoupled Python reference path. It means that later backends must reproduce this path's behavior. It does not bring the budgeted/coupled implementation into scope.

### 11.1 Active script map

| File | Responsibility |
|---|---|
| `IBG/main.py` | Creates experiments and replicas, repeats slots until equilibrium, and selects the default decoupled path. |
| `IBG/runner.py` | Runs one complete decoupled slot and returns a structured `SlotResult`. |
| `IBG/claude.py` | Builds sampled utility grids and solves the exact memoized `BR_EIBG` continuation policy. |
| `IBG/header.py` | Defines `Replica` and the reference utility, embedding, observation, belief, equilibrium, and fairness functions. |
| `IBG/ports.py` | Defines the infrastructure-neutral adapter contracts, including optional complete-slot traffic execution. |
| `IBG/simulation_adapters.py` | Implements the ports using the original in-process simulation behavior and provides no-op/in-memory result sinks for tests. |
| `IBG/learning.py` | Applies collected observations through the existing local and aggregate belief-update rules. |
| `IBG/result_sinks.py` | Stores a completed slot using the reference CSV reporting layout. |
| `IBG/report.py` | Calculates SLA violations and writes or plots reference report data. |
| `testbed/kubernetes_adapters.py` | Discovers Ready Pods, maps stable identities, builds complete routes, calls the flow generator, and converts telemetry to observations. |
| `testbed/kubernetes_controller.py` | Runs controlled validation slots or one evolving in-cluster experiment and emits structured results. |
| `testbed/profiles.py` | Loads and validates the deterministic profile ConfigMap shared by replicas and controller. |
| `testbed/experiment.py` | Retains replica state across slots, bounds iteration count, measures belief deltas, and emits run lifecycle events. |
| `testbed/validation.py` | Builds comparable simulation/Kubernetes summaries and checks mathematical parity. |
| `scripts/phase6_compare.py` | Compares controlled Kubernetes Job results with the simulation backend. |
| `scripts/run_experiment.py` | Builds, deploys, runs, renders, and saves one Kubernetes experiment through equilibrium. |

The simulation and Kubernetes entry points join at the same slot runner:

```text
IBG/main.py                         testbed/kubernetes_controller.py
  | simulation replica objects       | ConfigMap profiles + Pod discovery
  +------------------+---------------+
                     v
             IBG/runner.py: run_decoupled_slot
       -> discover stage replicas through an adapter
       -> IBG/claude.py: calculate utility and policy
       -> execute placement through an adapter
       -> simulation: collect stage observations immediately
       -> Kubernetes: execute complete routes after all placements
            -> convert returned hop telemetry to observations
       -> IBG/learning.py: update beliefs
       -> IBG/header.py + IBG/report.py: calculate metrics/equilibrium
       -> result sink
  -> Phase 6 validation runs one independent slot per controlled seed
  -> observable operation retains one replica set and repeats until equilibrium
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

Higher sampled delay `q`, higher congestion, or higher `gamma` lowers utility. Because every flow must select exactly one replica per stage, the solver chooses the continuation-consistent replica with the highest utility even when every available value is negative.

### 11.3 What happens inside one slot

`run_decoupled_slot` performs these common placement steps:

1. Save the beliefs from the start of the slot for the equilibrium check.
2. Process stages in order from 1 to 3.
3. Shuffle the flow order for the current stage, matching the reference behavior.
4. Discover only replicas belonging to that stage.
5. Ask the solver for a policy and utility grid.
6. Embed every flow into its selected replica and record the assignment.
7. Add total and per-flow utility for the stage.
8. Choose the backend's observation timing.

For simulation, each stage immediately collects the reference in-process observations and applies the existing local and aggregate belief updates before moving on.

For Kubernetes, physical traffic must use complete three-hop routes. The optional slot-traffic executor therefore waits until all stage placements exist, sends the routes to the flow generator, and receives correlated hop telemetry. The observation collector groups that telemetry by stage and converts it into the same `Observation` data class. The same `apply_observations` function then performs local and aggregate belief updates.

After observations are applied, the runner calculates SLA violations, Jain fairness, monotonic elapsed time, and equilibrium and sends the structured result to the result sink. Kubernetes results also retain the complete traffic telemetry.

The slot result includes flow order by stage, placements, complete routes by flow, utility grids, observations, aggregate utility, SLA violations, Jain fairness, equilibrium, and elapsed time.

### 11.4 Policy and utility logic

For every replica in the current stage, `br_eibg_exact` first:

1. Draws 30 delay-like samples using the replica's current belief.
2. Calculates expected utility for each possible congestion level from 1 to the number of flows.
3. Builds a utility table whose rows are replicas and columns are congestion levels.
4. Creates the sampled utility grid used by the exact game solver.

`BREIBGPolicy` then solves the sequential game:

1. Represent a subgame by the next player and the full vector of replica loads already chosen.
2. Try every available replica as the current player's action.
3. Recursively solve how all later players respond to that action.
4. Evaluate the current player's selected replica using its predicted final load, not its immediate load.
5. Select the action with the highest continuation-consistent utility.
6. Cache each load-vector subgame so it is solved only once.

The document's elementary pseudocode describes a binary choose/skip decision for one replica. The SFC model formally requires exactly one of the stage's replicas, so the implementation generalizes the branch to all active replicas. With three flows and five replicas, only 56 distinct load-vector states are solved, instead of repeatedly walking every path in the raw game tree.

The number of cached states grows as the number of possible load vectors, `C(N+M, M)` for `N` flows and `M` replicas through the terminal depth. This is why the supported project size remains three flows and five replicas per stage. Larger approximate algorithms are outside this project.

“Exact” means the recursion finds the exact continuation equilibrium for the utility grid it receives. The grid itself deliberately preserves the existing 30-sample Monte Carlo quality estimate, so it remains a sampled estimate of the paper's belief-weighted utility integral.

`embedding` walks through the shuffled flow list, asks the policy for a replica, updates the current replica loads, and appends the selected replica to that flow's route.

### 11.5 Observation and belief logic

Only selected replicas produce observations.

`Replica.tasting` combines replica capacity, congestion, and state-dependent random noise. `pdf_cal` converts the resulting value into:

- The most likely state, called the signal.
- A normalized four-state likelihood vector.

`local_update` combines the replica's current belief with that likelihood. `aggregation` then keeps 60% of the previous belief and mixes in 40% of the mean local observations for that replica.

Unselected replicas do not receive an observation and therefore do not change through this step.

For controlled Phase 6 runs, simulation and Kubernetes derive the observation noise from the configured replica observation seed plus slot ID, flow ID, and final assigned congestion. This makes a request stable without consuming the solver's NumPy random stream.

The legacy observation model receives final assignment load: the number of flows ultimately assigned to that replica in the slot. The HTTP service also reports actual admitted concurrency, which describes how requests overlapped at runtime. These are deliberately separate fields. Final assignment load preserves the reference learning mathematics; admitted concurrency and measured latency describe Kubernetes execution.

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

The tests do this before comparing exact fixtures or old/new orchestration. Controlled testbed profiles additionally provide one observation seed per replica, allowing the two backends to reproduce request observations without changing solver sampling. A normal `IBG/main.py` run remains stochastic and can produce different placements, observations, iteration counts, and metrics.

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

This builds the shared non-root runtime image for the replica, flow-generator, and controller processes. It installs only runtime dependencies from `requirements-runtime.txt`, copies both `IBG/` and `testbed/`, and runs as numeric user `10001`. Kubernetes selects the process role by overriding the image command where required.

### `deploy/local/compose.yaml`

This defines the three configured replica services and the flow generator on one private container network. It also defines health checks and exposes only the flow generator on host port `18081`.

### `testbed/profiles.py`

This validates the deterministic profile document. A profile contains the hidden state and capacity used by the legacy observation model, the delay and congestion penalty used by the solver, and the base/congestion delays used by the HTTP service.

### `testbed/kubernetes_adapters.py`

This is the infrastructure bridge. It talks to the Kubernetes API with the controller ServiceAccount, filters Pods by stage and readiness, maps Pod ordinals to one-based replica IDs, records stable DNS and node metadata, sends complete routes to the flow generator, and converts returned telemetry into `Observation` objects.

It does not contain utility, policy, or belief-update formulas.

### `testbed/kubernetes_controller.py`

This is the entry point run by the controller Job. It loads profiles, seeds Python and NumPy, waits for all required services, assembles the Kubernetes adapter bundle, and checks that every placement and observation is present.

With the base controller manifest, it runs one independent slot for each Phase 6 seed and prints `PHASE6_RESULT=<json>`. When the launcher supplies `MAX_ITERATIONS`, it retains one replica set across slots until equilibrium and emits `IBG_EVENT=<json>` lifecycle records.

### `testbed/experiment.py`

This module owns the backend-neutral outer experiment loop. It snapshots initial beliefs, calls the existing slot runner repeatedly, calculates the maximum belief change, emits iteration events, stops on the unchanged equilibrium result, and raises an explicit error if the maximum iteration count is exhausted.

### `testbed/validation.py` and `scripts/phase6_compare.py`

The validation module converts both backends into the same detailed summary shape. The comparison script reads the controller's three `PHASE6_RESULT` lines, reruns controlled simulation with the same seeds and profiles, and compares placements, utility grids, observations, beliefs, utility, SLA, fairness, and equilibrium. Runtime and infrastructure metadata are reported separately.

### `scripts/run_experiment.py`

This executable operator script coordinates Docker, kind, kubectl, the experiment Job, readable logs, and local JSONL retention. It polls logs instead of using a filesystem watcher, which avoids WSL watcher-limit failures while still updating output approximately every half second.

### `deploy/kubernetes/`

This directory contains the namespace, deterministic JSON profile ConfigMap, discovery RBAC, three headless Services and five-replica StatefulSets, flow-generator Service and Deployment, controller Job, and Kustomization. The Kustomization applies only long-running resources; `controller-job.yaml` is applied after rollout completion.

## 13. Test suite map

| Test file | What it protects |
|---|---|
| `tests/test_characterization.py` | Utility, solver, embedding, observations, belief updates, metrics, and equilibrium fixtures. |
| `tests/test_runner.py` | Equivalence of the extracted slot and original orchestration; safe import behavior. |
| `tests/test_adapters.py` | Adapter contracts and equivalence with simulation behavior. |
| `tests/test_cnf_service.py` | HTTP replica identity, concurrency, latency, configuration, observation parity, and cleanup. |
| `tests/test_flow_generator.py` | Concurrent flows, ordered hops, selected endpoints, correlation, validation, and failures. |
| `tests/test_kubernetes_adapters.py` | Profiles, Ready-Pod discovery, StatefulSet ordinals, complete Kubernetes routes, and telemetry-to-observation conversion. |
| `tests/test_validation.py` | Supported profile coverage, controlled backend parity, metadata completeness, and discrepancy detection. |
| `tests/test_experiment.py` | Stateful repetition, belief deltas, equilibrium completion, and maximum-iteration failure. |
| `tests/test_run_experiment.py` | Job environment overrides, readable event rendering, and watcher-free JSONL log polling. |

Run everything before declaring a change complete:

```bash
source .venv/bin/activate
python -m pytest -q
```

The current complete suite contains 63 tests.

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

Check Docker, the kind node containers, and the current context separately:

```bash
systemctl status docker --no-pager
docker ps -a --filter label=io.x-k8s.kind.cluster
kind get clusters
kubectl config current-context
kubectl cluster-info
```

After a WSL or Docker restart, wait for the node containers and API server before changing manifests. If the `ibg` containers exist but are stopped, start Docker first and inspect their state. Recreating the cluster should be a last resort because it discards the current cluster state.

### Pods report `ErrImageNeverPull`

The Kubernetes manifests deliberately use `imagePullPolicy: Never`. Build and load the local image into kind:

```bash
docker build --tag ibg-testbed:phase6 \
  --file deploy/local/Dockerfile .
kind load docker-image ibg-testbed:phase6 --name ibg
```

Then recreate the affected Pod or reapply the workload.

### The controller Job failed

Inspect the Pod and logs before deleting anything:

```bash
kubectl get pods --namespace ibg-testbed -o wide
kubectl describe job ibg-controller --namespace ibg-testbed
kubectl logs --namespace ibg-testbed job/ibg-controller
```

Common causes are an old image still loaded in kind, incomplete replica readiness, denied RBAC, invalid profile data, or a flow-generator/replica identity mismatch. After fixing the cause, rebuild and reload the image when Python changed, then delete and recreate only the Job as shown in Phase 5.

For an observable run, inspect `ibg-experiment` instead:

```bash
kubectl describe job ibg-experiment --namespace ibg-testbed
kubectl logs --namespace ibg-testbed job/ibg-experiment
```

If the final event says equilibrium was not reached, rerun with a larger explicit bound only after inspecting the belief deltas:

```bash
./scripts/run_experiment.py --max-iterations 200 --skip-build
```

### The controller cannot discover replicas

Check readiness, labels, ordinals, and permissions:

```bash
kubectl get pods --namespace ibg-testbed \
  --selector=app.kubernetes.io/name=ibg-replica \
  --show-labels
kubectl auth can-i list pods \
  --as=system:serviceaccount:ibg-testbed:ibg-controller \
  --namespace=ibg-testbed
```

The adapter intentionally refuses partial stage membership. For the current supported deployment, ordinals `0` through `4` must all be Ready in every stage.

## 15. How to maintain this tutorial

Only update this file when the user explicitly requests it. When an update is requested, check at minimum:

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
