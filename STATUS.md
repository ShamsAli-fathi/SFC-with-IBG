# Project Status

Updated: 2026-06-28

## Completed

- Reviewed the paper draft and its hybrid-testbed proposal.
- Read the Python files directly under `IBG/` and identified the active decoupled simulation path.
- Established the lightweight target architecture and migration boundary.
- Chose a WSL-only development toolchain with native Docker Engine instead of Docker Desktop.
- Created the repository handoff documents; no implementation was changed.

## Environment facts

- Host: Windows 11 Enterprise, Intel i7-10750H (6 cores/12 threads), approximately 16 GB RAM.
- Hardware virtualization is enabled.
- Ubuntu 24.04 runs under WSL2 with `systemd` enabled. Its `ext4.vhdx` is stored at `E:\WSL\Ubuntu-24.04`.
- The current checkout is at `/mnt/e/WSL/Ubuntu-24.04/projects/SFC-with-IBG`; the active checkout will move to `/home/shams/projects/SFC-with-IBG` so source operations use the native ext4 filesystem.
- Docker, kind, kubectl, and Helm are not installed in this WSL environment.
- C has limited free space; the WSL distribution and its Docker/cluster data are therefore kept on E.
- The current project root is a Git repository on branch `IBG`, with `origin` configured for `ShamsAli-fathi/SFC-with-IBG`.

## Current state

The existing simulation remains untouched. No cluster, manifests, container image, HTTP CNF, controller adapter, or testbed-specific refactor has been created yet.

## Next action

Move the active checkout into `/home/shams/projects`, configure WSL2 resources, install native Docker Engine plus `kubectl`, kind, and Helm inside Ubuntu, and create a minimal three-node smoke-test cluster before changing Python code.

## New-thread handoff prompt

> We are continuing the IBG Kubernetes testbed project in `/home/shams/projects/SFC-with-IBG` on branch `IBG`. The reference Python simulation is directly under `IBG/`. Read `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, and `STATUS.md`, then inspect the current environment and relevant files. Do not modify the IBG implementation yet. Confirm the documented state and complete the native Docker Engine, Kubernetes CLI, and three-node kind smoke-test milestone inside WSL2.
