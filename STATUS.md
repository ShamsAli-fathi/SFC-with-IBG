# Project Status

Updated: 2026-06-27

## Completed

- Reviewed the paper draft and its hybrid-testbed proposal.
- Read the root-level Python files in `IBG/` and identified the active decoupled simulation path.
- Established the lightweight target architecture and migration boundary.
- Created the repository handoff documents; no implementation was changed.

## Environment facts

- Host: Windows 11 Enterprise, Intel i7-10750H (6 cores/12 threads), approximately 16 GB RAM.
- Hardware virtualization is enabled.
- WSL, Docker, kind, kubectl, and Helm were not installed when checked.
- C has limited free space; WSL and Docker's large data disks should be placed on another drive.
- `E:\codex git\thesis` was not detected as a Git repository, so there is currently no Git status or commit checkpoint at this root.

## Current state

The existing simulation remains untouched. No cluster, manifests, container image, HTTP CNF, controller adapter, or testbed-specific refactor has been created yet.

## Next action

Install and verify WSL2 Ubuntu and Docker Desktop with their large data roots outside C. Then install `kubectl` and `kind` inside Ubuntu and create a minimal three-node smoke-test cluster before changing Python code.

## New-thread handoff prompt

> We are continuing the IBG Kubernetes testbed project in `E:\codex git\thesis`. Read `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, and `STATUS.md`, then inspect the current environment and relevant files. Do not modify the IBG implementation yet. Confirm the documented state, identify any inconsistencies, and guide me through the WSL2/Docker installation and three-node kind smoke test as the first milestone.
