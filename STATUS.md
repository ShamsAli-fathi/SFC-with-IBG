# Project Status

Updated: 2026-06-28

## Completed

- Reviewed the paper draft and its hybrid-testbed proposal.
- Read the Python files directly under `IBG/` and identified the active decoupled simulation path.
- Established the lightweight target architecture and migration boundary.
- Created the repository handoff documents; no implementation was changed.

## Environment facts

- Host: Windows 11 Enterprise, Intel i7-10750H (6 cores/12 threads), approximately 16 GB RAM.
- Hardware virtualization is enabled.
- The repository is currently being accessed through WSL2 Ubuntu at `/mnt/e/WSL/Ubuntu-24.04/projects/SFC-with-IBG`.
- Docker, kind, kubectl, and Helm are not installed in this WSL environment.
- C has limited free space; WSL and Docker's large data disks should be placed on another drive.
- The current project root is a Git repository on branch `main`, with `origin` configured for `ShamsAli-fathi/SFC-with-IBG`.

## Current state

The existing simulation remains untouched. No cluster, manifests, container image, HTTP CNF, controller adapter, or testbed-specific refactor has been created yet.

## Next action

Verify the current WSL2 storage arrangement, then install and verify Docker Desktop with its large data root outside C. Install `kubectl` and `kind` inside Ubuntu and create a minimal three-node smoke-test cluster before changing Python code.

## New-thread handoff prompt

> We are continuing the IBG Kubernetes testbed project in `/mnt/e/WSL/Ubuntu-24.04/projects/SFC-with-IBG`. The reference Python simulation is directly under `IBG/`. Read `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, and `STATUS.md`, then inspect the current environment and relevant files. Do not modify the IBG implementation yet. Confirm the documented state, identify any inconsistencies, and guide me through Docker installation and the three-node kind smoke test as the first milestone.
