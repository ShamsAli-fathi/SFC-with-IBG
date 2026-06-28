# Project Status

Updated: 2026-06-28

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
- Created the repository handoff documents; no implementation was changed.

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

## Current state

Phase 0 is complete. Phases 1-6 in `ROADMAP.md` have not started. The existing simulation remains untouched; no application manifests, container image, HTTP CNF, controller adapter, characterization tests, or testbed-specific refactor has been created yet.

## Next action

Begin Phase 1 only when requested: add deterministic characterization tests for the reference decoupled simulation before refactoring its orchestration.

## New-thread handoff prompt

> We are continuing the IBG Kubernetes testbed project in `/home/shams/projects/SFC-with-IBG` on branch `IBG`. Read `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`, and `STATUS.md`. Phase 0 is complete; do not begin a later phase without an explicit request. The next planned work is Phase 1 characterization testing of the reference decoupled simulation.
