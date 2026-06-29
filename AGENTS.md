# Codex Working Agreement

Read `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`, `STATUS.md`, and `Tutorial.md` before planning or changing this repository. Treat them as the project handoff record and update them when architecture, decisions, sequencing, progress, or user-facing workflows materially change.

## Project goal

Convert the existing decoupled Indian Buffet Game (IBG) Python simulation into a lightweight Kubernetes testbed while preserving its equilibrium, utility, belief-update, and reporting logic.

## Guardrails

- The Python files directly under `IBG/` are the reference simulation. The budgeted/coupled path is out of scope unless explicitly requested.
- Preserve the IBG mathematics and behavior. Isolate Kubernetes, traffic, and telemetry concerns behind adapters instead of embedding them in the solver.
- Prefer small, reviewable changes. Plan substantial work before implementation.
- Do not rewrite generated CSV data, pickle files, old copies, or unrelated algorithm variants unless explicitly requested.
- Do not read large result files wholesale; inspect only targeted rows, columns, or summaries.
- Do not claim real DPDK, VPP, SR-IOV, hugepage, or line-rate validation.
- Before declaring a task complete, run the relevant focused tests/checks and report what was actually verified.

## Documentation discipline

- `ARCHITECTURE.md`: stable system structure and data flow.
- `DECISIONS.md`: accepted choices, constraints, and deferred features.
- `ROADMAP.md`: ordered migration phases and their acceptance gates.
- `STATUS.md`: environment facts, current progress, blockers, and the next action.
- `Tutorial.md`: living beginner-friendly report, phase-by-phase operating guide, and explanation of the Python/testbed logic. Update it whenever a phase, script, command, configuration, output, or troubleshooting workflow changes.
