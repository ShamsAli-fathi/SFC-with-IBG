# Project Status

Updated: 2026-06-29

## Completed

- Reviewed the paper draft and its hybrid-testbed proposal.
- Read the Python files directly under `IBG/` and identified the active decoupled simulation path.
- Established the lightweight target architecture and migration boundary.
- Chose a WSL-only development toolchain with native Docker Engine instead of Docker Desktop.
- Created the native ext4 checkout at `/home/shams/projects/SFC-with-IBG` and preserved the existing unstaged `requirements.txt` change.
- Installed Docker Engine 29.6.1, kubectl 1.35.6, kind 0.31.0, and Helm 4.2.0 inside Ubuntu.
- Added a reproducible three-node kind configuration and created cluster `ibg` with Kubernetes 1.35.0.
- Verified three Ready nodes, Ready system Pods, a two-replica HTTP deployment, Service DNS/networking, and cleanup of the temporary smoke-test namespace.
- Completed Roadmap Phase 0: created `.venv` with Python 3.12, installed the declared dependencies, verified active IBG imports, and compiled all Python sources without executing `IBG/main.py`.
- Completed Roadmap Phase 1: added eight deterministic characterization/equivalence tests and extracted one decoupled slot into an import-safe runner without changing the solver or belief mathematics.
- Reduced the reference entry point from 48 outer experiments to one by default and verified the existing small configuration (three stages, four replicas per stage, three flows) reaches equilibrium; smoke-test reports were written only under `/tmp`.
- Completed Roadmap Phase 2: defined discovery, traffic, observation, and result-sink ports; added simulation-backed implementations; and kept measured latency separate from the legacy belief signal.
- Expanded the suite to 18 passing tests, including explicit-adapter equivalence, legacy observation-update parity, contract validation, empty-discovery failure, and reference CSV sink behavior.
- Verified an adapter-driven small experiment reaches equilibrium and writes the expected metric and belief row counts under `/tmp`.
- Completed Roadmap Phase 3: implemented the configurable FastAPI/Uvicorn HTTP replica with `/health` and `/process`, stable identity, real concurrent-request accounting, latency telemetry, and the reference legacy observation model.
- Expanded the suite to 32 passing tests, including endpoint contracts, three-request overlap, exact tasting parity, request/config validation, and concurrency cleanup after failures.
- Verified a live localhost Uvicorn process returns HTTP 200 for both endpoints and shuts down cleanly.
- Completed Roadmap Phase 4: implemented a route-driven FastAPI flow generator that runs logical flows concurrently while preserving sequential three-stage execution within each flow.
- Added strict route, response, and replica-identity validation plus correlated per-hop concurrency, latency, Pod, endpoint, and legacy-observation telemetry.
- Added a shared non-root runtime image, a four-service Docker Compose topology, and a repeatable three-flow container-network smoke test.
- Expanded the suite to 42 passing tests, including selected-endpoint routing, inter-flow concurrency, intra-flow stage ordering, telemetry correlation, downstream failures, and identity/correlation mismatches.
- Verified the Phase 4 gate with three concurrent three-hop flows across the local container network; every flow returned stages 1, 2, and 3 in order and the stage-1 service reported admitted concurrency levels 1, 2, and 3.
- Created and maintained the repository handoff documents as implementation progressed.

## Environment facts

- Host: Windows 11 Enterprise, Intel i7-10750H (6 cores/12 threads), approximately 16 GB RAM.
- Hardware virtualization is enabled.
- Ubuntu 24.04 runs under WSL2 with `systemd` enabled. Its `ext4.vhdx` is stored at `E:\WSL\Ubuntu-24.04`.
- The active checkout is `/home/shams/projects/SFC-with-IBG`; the previous `/mnt/e/WSL/Ubuntu-24.04/projects/SFC-with-IBG` checkout remains temporarily as a backup.
- Native Docker Engine is active under `systemd`, normal-user Docker access is configured, and its data root is `/var/lib/docker` inside the E-hosted ext4 filesystem.
- `%UserProfile%\.wslconfig` is active: WSL reports approximately 10 GB RAM, 6 processors, and 4 GB swap.
- The `ibg` kind cluster still exists after the WSL restart, but its node containers did not restore the Kubernetes API automatically. The cluster is not required for Phases 0-4 and can remain stopped until cluster work resumes.
- C has limited free space; the WSL distribution and its Docker/cluster data are therefore kept on E.
- The current project root is a Git repository on branch `IBG`, with `origin` configured for `ShamsAli-fathi/SFC-with-IBG`.
- Docker Hub returned HTTP 403 for the initial Python base-image pull, so the local runtime image uses the official Azure Linux Python 3.12 base from Microsoft Container Registry. This is a packaging workaround, not a change to runtime behavior.

## Current state

Phases 0-4 are complete. Phases 5-6 in `ROADMAP.md` have not started. The reference solver, utility, belief update, equilibrium, and metric functions remain unchanged. The HTTP replica and flow generator now complete concurrent controller-selected routes over a local container network, but no Kubernetes application manifests or Kubernetes-backed adapters have been created yet.

## Next action

Begin Phase 5 only when requested: add the small Kubernetes deployment, stable replica discovery, narrow RBAC, and controller integration without changing the solver.

## New-thread handoff prompt

> We are continuing the IBG Kubernetes testbed project in `/home/shams/projects/SFC-with-IBG` on branch `IBG`. Read `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`, and `STATUS.md`. Phases 0-4 are complete; do not begin a later phase without an explicit request. The next planned work is Phase 5, the small Kubernetes deployment, discovery/RBAC, and one-slot controller integration gate.
