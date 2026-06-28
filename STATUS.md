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
- Created the repository handoff documents; no implementation was changed.

## Environment facts

- Host: Windows 11 Enterprise, Intel i7-10750H (6 cores/12 threads), approximately 16 GB RAM.
- Hardware virtualization is enabled.
- Ubuntu 24.04 runs under WSL2 with `systemd` enabled. Its `ext4.vhdx` is stored at `E:\WSL\Ubuntu-24.04`.
- The active checkout is `/home/shams/projects/SFC-with-IBG`; the previous `/mnt/e/WSL/Ubuntu-24.04/projects/SFC-with-IBG` checkout remains temporarily as a backup.
- Native Docker Engine is active under `systemd`, normal-user Docker access is configured, and its data root is `/var/lib/docker` inside the E-hosted ext4 filesystem.
- `%UserProfile%\.wslconfig` requests 10 GB RAM, 6 processors, and a 4 GB E-hosted swap file. A WSL shutdown/restart is still required to activate these values; the current instance reports 7.6 GiB RAM, 12 processors, and 2 GiB swap.
- C has limited free space; the WSL distribution and its Docker/cluster data are therefore kept on E.
- The current project root is a Git repository on branch `IBG`, with `origin` configured for `ShamsAli-fathi/SFC-with-IBG`.

## Current state

The existing simulation remains untouched. The three-node smoke-test cluster and its kind configuration exist, but no application manifests, container image, HTTP CNF, controller adapter, or testbed-specific refactor has been created yet.

## Next action

Run `wsl --shutdown` from Windows, reopen Ubuntu, verify the 10 GB/6 CPU/4 GB swap limits and Docker service, and restart the existing kind node containers if Docker did not restore them automatically. Then characterize the reference simulation with focused tests before refactoring it.

## New-thread handoff prompt

> We are continuing the IBG Kubernetes testbed project in `/home/shams/projects/SFC-with-IBG` on branch `IBG`. The reference Python simulation is directly under `IBG/`. Read `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, and `STATUS.md`, then inspect the current environment and relevant files. Do not modify the IBG implementation yet. Confirm the documented state and complete the native Docker Engine, Kubernetes CLI, and three-node kind smoke-test milestone inside WSL2.
