# IBG Testbed Tutorial

This is the living usage guide for the SFC-with-IBG project. It is written for readers who know basic Python and terminal commands but may be new to WSL, Docker, Kubernetes, or the Indian Buffet Game (IBG) implementation.

Updated through: expansion Phase 2 calibration, 2026-07-13.

This file is user-directed. Agents must not read or edit it unless the user explicitly requests that action in the current task.

## 1. What this project is

The project builds a small service-function-chain testbed around a decoupled Indian Buffet Game. It keeps the IBG controller and learning logic in Python while using FastAPI, Docker, kind, and Kubernetes to exercise selected service routes through real HTTP requests.

For the validated default, the testbed has:

- Three ordered stages.
- Five candidate replicas in each stage.
- Three logical flows in each slot.
- One selected replica per stage for every flow.
- Concurrent traffic after all complete routes have been chosen.
- Processing-latency observations from selected replicas only.

The HTTP services are controlled test doubles. They are not telecom CNFs, DPDK, VPP, SR-IOV, hardware-offload, or line-rate implementations.

## 2. The simplest mental model

Think of each logical flow as a customer moving through three counters:

```text
flow
  -> controller chooses one Stage 1 replica
  -> controller chooses one Stage 2 replica
  -> controller chooses one Stage 3 replica
  -> flow generator sends the selected HTTP requests
  -> controller receives selected-hop telemetry
  -> controller updates beliefs and calculates metrics
```

The controller decides the IBG placement. Kubernetes does not choose the route; it only runs the already-created Pods and provides their network identities.

| Term | Meaning in this project |
|---|---|
| Flow | One logical request that traverses every configured stage. |
| Stage | One ordered position in the service chain, numbered from 1. |
| Replica | One candidate service instance in a stage. |
| Slot | One complete placement, traffic, observation, and belief-update iteration. |
| Assigned load | Final number of flows assigned to one replica in a slot. |
| Hidden state | Fixed, unobserved replica performance state: 1 is bad and 4 is good. |
| Belief | Four probabilities representing uncertainty about a replica's hidden state. |
| Signal | Selected-hop processing latency used by the belief update. |
| Adapter | Boundary between the IBG logic and simulation, HTTP, or Kubernetes infrastructure. |
| Kernel mode | The ordinary Linux socket/TCP/IP path used by the current HTTP testbed. |

## 3. Current project report

The original lightweight Kubernetes migration is complete. The current expansion work has completed the mathematical latency/utility model and its calibration. The next phase makes the existing HTTP route an explicit `kernel` datapath baseline; DPDK/VPP remains future work.

| Expansion phase | Status | Main result |
|---|---|---|
| Foundation and migration | Complete | Exact decoupled solver, FastAPI replicas, flow generator, kind resources, and controlled simulation/Kubernetes parity. |
| 0: Freeze scope | Complete | FastAPI/Kubernetes named as the future Kernel baseline; DPDK/VPP and coupled IBG kept separate. |
| 1: Latency model | Complete | Hidden state causes load-conditioned processing latency; latency is the selected private signal; utility is linear. |
| 2: Calibration | Complete | Accepted state curves, policy units, 12-load utility horizon, sensitivity checks, and localhost FastAPI conformance. |
| 3: Kernel baseline | Planned | Add explicit mode metadata and fresh Kubernetes Kernel evidence. |
| 4--6: DPDK/VPP | Planned | Design, implement, then compare against the Kernel baseline. |
| Coupled IBG | Unscheduled | Requires separate user-defined mathematics and acceptance criteria. |

The current suite has 88 passing tests. This verifies Python behavior, adapters, HTTP contracts, traffic correlation, calibration, and controlled replay fixtures. It does not claim that every configurable cluster size, DPDK/VPP mode, or future heuristic has been validated.

## 4. Where to work

Use an Ubuntu WSL terminal and the active native-Linux checkout:

```bash
cd /home/vhakami/Desktop/projects/vesal/SFC-with-IBG
git branch --show-current
git status --short --branch
```

The active branch is `IBG`. Work from the Linux filesystem, not an older Windows-mounted checkout.

Windows supplies the WSL host. Python, Docker Engine, kind, kubectl, Git, and source code are used inside Ubuntu.

## 5. Prepare and verify Python

The repository uses a project-local virtual environment.

```bash
cd /home/vhakami/Desktop/projects/vesal/SFC-with-IBG
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For later sessions, activation is normally enough:

```bash
cd /home/vhakami/Desktop/projects/vesal/SFC-with-IBG
source .venv/bin/activate
```

Verify the current source:

```bash
python -m pytest -q
python -m compileall -q IBG testbed scripts tests
git diff --check
```

## 6. The active IBG model

### 6.1 Hidden state causes real service behavior

Each replica has one fixed hidden state $\theta\in\{1,2,3,4\}$. State 1 is poor and state 4 is good. The state is known to controlled test configuration but is never exposed as ground truth to a flow or the controller.

For selected replica load $n$, the modeled processing latency is:

$$
Q_\theta(n)=\mu_\theta+a_\theta\max(0,n-1)+b_\theta\max(0,n-\kappa_\theta)^2+\epsilon_\theta.
$$

All latency terms are milliseconds. $\kappa_\theta$ is measured in concurrent-flow units. The final term is positive-truncated Gaussian jitter.

FastAPI actually waits for the sampled modeled delay. It then reports measured server processing latency, which becomes the continuous selected-hop signal:

$$s=q.$$

The controller calculates four likelihoods $f(q\mid\theta,n)$ and uses the whole likelihood vector for the existing posterior and aggregation logic. A reported state estimate is only a convenient category for people reading telemetry; it does not drive the belief update.

Only selected replicas produce an observation. Unselected replicas remain unobserved, preserving the asymmetric and partial-observation model.

### 6.2 Utility and end-to-end metrics

The active stage utility is:

$$
u_k(q)=R_k-\alpha_kq-c_k.
$$

Congestion already affects latency through $Q_\theta(n)$, so the old extra congestion multiplier is not used in the active utility path.

The reported realized end-to-end utility subtracts explicitly weighted transport overhead:

$$
U_i=\sum_k U_{i,k}-\alpha_{\mathrm{link}}\sum_k L_{\mathrm{transport},k}.
$$

Current transport overhead is non-negative client request latency minus server processing latency. It is useful telemetry but is not claimed to be a direct physical Pod-to-Pod link measurement.

The SLA is a per-flow end-to-end latency threshold, not a hidden-state rule.

## 7. Accepted Phase 2 calibration

The current calibration describes the synthetic FastAPI test service. It is not a measurement of Kernel networking capacity and is not a DPDK/VPP claim.

| State | Baseline $\mu$ ms | Ordinary $a$ ms | Knee $b$ ms | Capacity $\kappa$ flows | Jitter $\sigma$ ms | First negative expected utility load |
|---:|---:|---:|---:|---:|---:|---:|
| 1 — bad | 40 | 8 | 12 | 1 | 4 | 3 |
| 2 | 28 | 6 | 8 | 2 | 3 | 5 |
| 3 | 18 | 4 | 5 | 3 | 2 | 7 |
| 4 — good | 10 | 2 | 2 | 5 | 1 | 11 |

The policy values are:

| Value | Accepted setting |
|---|---:|
| Reward per selected stage $R$ | 100 utility units |
| Stage cost $c$ | 1 utility unit |
| Processing-latency weight $\alpha$ | 1 utility unit/ms |
| Transport-latency weight $\alpha_{\mathrm{link}}$ | 1 utility unit/ms |
| End-to-end SLA threshold | 250 ms |
| Calibration horizon | 12 assigned flows per replica |

The intended interpretation is simple: bad replicas become unattractive early, while a good replica remains useful until substantially higher congestion. Negative utility does not currently reject a flow because the one-of-M IBG action model still requires one replica in each stage.

### Reproduce the calibration report

```bash
source .venv/bin/activate
python scripts/phase2_calibrate.py --samples 5000 --seed 2050
```

Success prints one `PHASE2_CALIBRATION=<json>` line and exits with status 0. It checks:

- Ordered latency curves over loads 1 through 12.
- Expected zero crossings 3, 5, 7, and 11.
- Low-load positivity and a feasible state-4 option at the supported load of three.
- Seeded state-classification accuracy.
- Sensitivity to ±10% latency/weight and ±5% reward changes.
- An illustrative three-stage SLA Monte Carlo check with zero transport overhead.

The verified 5,000-sample run had 94.42% minimum categorical state accuracy. The full likelihood vector remains the important learning input.

### Optional live localhost check

Start a configured replica in one terminal:

```bash
source .venv/bin/activate
STATE=4 OBSERVATION_SEED=2104 STAGE=1 REPLICA_ID=1 \
POD_NAME=phase2-state-4 \
python -m uvicorn testbed.cnf_service:app --host 127.0.0.1 --port 8080
```

In another terminal:

```bash
source .venv/bin/activate
python scripts/phase2_calibrate.py \
  --samples 5000 \
  --live-url http://127.0.0.1:8080 \
  --live-state 4
```

The live check sends five requests at load 1 and five after the state capacity knee. It verifies assigned-load correlation, positive modeled/measured latency, signal/likelihood consistency, and repeated categorical accuracy. The localhost timing tolerance is $\max(10\text{ ms},10\%\text{ of modeled latency})$. It is not a Kubernetes tolerance; Phase 3 will measure that separately.

Stop Uvicorn with `Ctrl+C` when finished.

## 8. Run one FastAPI replica manually

The replica exposes `GET /health` and `POST /process`.

Start it as shown above, then inspect health:

```bash
curl -sS http://127.0.0.1:8080/health
```

Send a request with final assigned load explicitly supplied:

```bash
curl -sS -X POST http://127.0.0.1:8080/process \
  -H 'content-type: application/json' \
  -d '{"slot_id":1,"flow_id":1,"assigned_load":1}'
```

Important response fields are:

| Field | Meaning |
|---|---|
| `assigned_load` | Final slot load used to sample latency and likelihood. |
| `modeled_processing_latency_ms` | State/load-conditioned delay sampled by the service. |
| `processing_latency_ms` | Actual measured server time. |
| `signal_latency_ms` | The measured processing latency used as signal $q$. |
| `state_likelihood` | Four load-aware likelihood values used by the controller. |
| `state_estimate` | Most likely category for reporting only. |
| `concurrency` | Actual requests active when this request was admitted. |

Some `legacy_*` response fields remain for transition compatibility. They are not the active learning model.

Run focused HTTP tests with:

```bash
python -m pytest -q tests/test_cnf_service.py tests/test_latency_model.py
```

## 9. Local three-hop Docker testbed

The local Compose topology has three replicas and one flow generator on a private Docker network. It is useful before Kubernetes work because it exercises real service-to-service HTTP.

```bash
docker compose -f deploy/local/compose.yaml up --build --detach --wait
python scripts/phase4_smoke.py
docker compose -f deploy/local/compose.yaml down --remove-orphans
```

The smoke check confirms three concurrent flows, ordered hops within each flow, selected-endpoint routing, and Stage-1 overlap. Exact elapsed times vary by machine.

## 10. Kubernetes and kind

The active testbed uses namespace `ibg-testbed`.

| Component | Kubernetes object | Purpose |
|---|---|---|
| Replica stages | Headless Service + StatefulSet | Stable Pod ordinal identities and direct Pod DNS. |
| Flow generator | ClusterIP Service + Deployment | Executes controller-selected complete routes. |
| Controller | ServiceAccount + Job | Runs placement, traffic, observations, and reporting. |
| Profiles | ConfigMap | Shares replica state, cost, and observation seeds. |
| RBAC | Role + RoleBinding | Restricts controller discovery to Pod `get`/`list`. |

Check the local cluster first:

```bash
kind get clusters
kubectl config current-context
kubectl get nodes -o wide
kubectl get pods -A
```

The expected context is `kind-ibg`, with one control-plane node and two workers.

### Run an observable experiment

The usual entry point builds the current image, loads it into kind, deploys resources, runs an experiment Job, follows its logs, and stores JSONL trace data under ignored `runs/`:

```bash
./scripts/run_experiment.py --flow 3 --stage 3 --replica 5
```

The dimensions configure the existing exact solver. They do not prove that a larger setting is scalable or parity-validated. The formal controlled target remains three flows, three stages, and five replicas per stage.

If the source image has not changed, skip the rebuild:

```bash
./scripts/run_experiment.py --skip-build
```

Do not use `--skip-build` after changing `IBG/` or `testbed/`; kind would use the older loaded image.

### Controlled replay comparison

After a controller validation Job produces its output, compare it against controlled simulation:

```bash
kubectl logs --namespace ibg-testbed job/ibg-controller \
  | .venv/bin/python scripts/phase6_compare.py --kubernetes-log -
```

This checks mathematical fields such as placements, utility grids, processing-latency observations/likelihoods, beliefs, utility, SLA, fairness, and equilibrium. Kubernetes timing and infrastructure metadata remain separate from in-process simulation timing.

## 11. IBG Exact: active code map

| File | Responsibility |
|---|---|
| `IBG/runner.py` | Runs one complete decoupled slot and returns `SlotResult`. |
| `IBG/claude.py` | Builds belief-driven latency utility grids and solves exact memoized `BR_EIBG`. |
| `IBG/header.py` | Defines replicas, utility kernel, learning helpers, embedding, equilibrium, and fairness. |
| `IBG/latency_model.py` | Holds the calibrated state latency law, likelihoods, and utility helpers. |
| `IBG/calibration.py` | Implements reproducible Phase 2 calibration and live-observation checks. |
| `IBG/ports.py` | Defines discovery, traffic, observation, transport-latency, and result ports. |
| `IBG/simulation_adapters.py` | Provides in-process simulation implementations. |
| `testbed/cnf_service.py` | FastAPI replica behavior and telemetry contract. |
| `testbed/flow_generator.py` | Concurrent logical flows with sequential hops per flow. |
| `testbed/kubernetes_adapters.py` | Pod discovery, route execution, and telemetry conversion. |
| `testbed/kubernetes_controller.py` | In-cluster controller entry point. |
| `scripts/phase2_calibrate.py` | Reproduces the accepted calibration report. |
| `scripts/phase6_compare.py` | Compares controller output with controlled simulation. |
| `scripts/run_experiment.py` | Builds, deploys, runs, and records Kubernetes experiments. |

### What exact `BR_EIBG` means

For each stage, the solver samples 30 belief-driven processing latencies per replica/load and converts them into expected utility values. It then recursively explores every currently available replica action for the next flow, predicts later flows' continuation choices, and selects the action with the best continuation-consistent utility.

The full vector of replica loads is the recursive subgame state. Results are memoized, and exact ties choose the lowest replica ID. For $N$ flows and $M$ replicas, terminal load-vector states grow as $C(N+M,M)$. The supported three-flow/five-replica stage has 56 such states.

This solver always chooses one replica. A negative utility means an unattractive assignment, not permission to skip a stage.

## 12. Important boundaries and future work

- FastAPI remains the application and selected-processing-latency source in every future datapath mode.
- Kernel and future DPDK/VPP telemetry must remain supplemental; they cannot silently become belief observations.
- DPDK/VPP, hugepages, SR-IOV, VPP topology, and performance claims are not implemented or validated yet.
- Coupled/budgeted IBG code remains outside the active decoupled path.
- Direct utility sweeps can evaluate more than three flows; this does not expand exact-solver validation.
- If a future experiment needs a per-replica load horizon above 12, extend the calibration before treating those utility values as accepted.

## 13. Troubleshooting

### Python or a package is missing

Activate the environment:

```bash
cd /home/vhakami/Desktop/projects/vesal/SFC-with-IBG
source .venv/bin/activate
```

### Docker permission denied

```bash
systemctl status docker --no-pager
docker info
```

The accepted setup uses native Docker Engine in WSL, not Docker Desktop.

### A port is already in use

Stop old Uvicorn processes with `Ctrl+C`, then clean the local Compose stack if relevant:

```bash
docker compose -f deploy/local/compose.yaml down --remove-orphans
```

### kind cannot use the newest source

Rebuild and reload the image before rerunning a Job:

```bash
docker build --tag ibg-testbed:phase6 --file deploy/local/Dockerfile .
kind load docker-image ibg-testbed:phase6 --name ibg
```

### The controller cannot discover replicas

Check Pod readiness and the controller permission:

```bash
kubectl get pods --namespace ibg-testbed -o wide
kubectl auth can-i list pods \
  --as=system:serviceaccount:ibg-testbed:ibg-controller \
  --namespace=ibg-testbed
```

The controller intentionally rejects a stage with missing Ready ordinals instead of silently running a partial experiment.

## 14. Maintaining this tutorial

Only update this file when the user explicitly requests it. When updating it:

1. Preserve the beginner-friendly explanation and distinguish implemented behavior from plans.
2. Update the project report, equations, commands, tests, and current paths together.
3. Do not present DPDK/VPP, coupled IBG, or larger solver sizes as implemented without their acceptance gates.
4. Keep it consistent with `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`, and `STATUS.md`.
5. Preserve the backup before a major rewrite.

The goal is simple: a new reader should understand what exists, run it safely, recognize success, and know what is intentionally deferred.
