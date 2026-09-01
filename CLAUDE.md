# Claude Working Agreement

Companion to `AGENTS.md` (which targets a different assistant — **do not edit it**).
The guardrails below are the same project rules restated for Claude Code, plus the
practical repo facts Claude needs. Where this file and `AGENTS.md` overlap, they must
agree; if they ever diverge, `AGENTS.md` and the four handoff documents win.

## Read first

Before planning or changing anything, read `ARCHITECTURE.md`, `DECISIONS.md`,
`ROADMAP.md`, and `STATUS.md`. They are the project handoff record. Update them when
architecture, decisions, sequencing, or progress materially changes.

Exception: during an explicitly authorized iterative visual tweak to an
already-authorized `Chart/` plot (range, title, label, styling), do not reread or
update the handoffs unless the user asks to record the choice as final.

## Project goal

Build the SFC-with-IBG testbed incrementally. The implemented roadmap migrates the
decoupled Indian Buffet Game (IBG) Python simulation into a lightweight Kubernetes
testbed while preserving its equilibrium, utility, belief-update, and reporting logic.
Coupled, budgeted, datapath, or new baseline extensions require explicit scope first.

The paper this work implements is `misc/vesal_tex.tex`. When a policy or metric
question turns on "what does the paper say", read it there rather than inferring.

## Environment

- **There is no `python` on PATH.** Use `.venv/bin/python` and `.venv/bin/pytest`.
- Working branch is `IBG`; `main` is the PR target.
- Focused tests: `.venv/bin/pytest tests/test_greedy_phase8.py -q`
- A policy area's suite: `.venv/bin/pytest tests/ -k greedy -q`
- Launchers live in `scripts/` (`run_greedy_kernel.py`, `run_milp_kernel.py`,
  `run_hybrid_kernel_*.py`); trace summarizers are the `*_summary.py` scripts.
- Run traces are JSONL under `runs/`. Read targeted records, never whole files.

## Code areas

| Path | Status |
|---|---|
| `IBG/` | Reference simulation. Exact chapter is **frozen**. |
| `IBG_Hybrid/` | Hybrid policy. Frozen unless the user opens that scope. |
| `MILP/` | MILP baseline. |
| `Greedy/` | Greedy baseline — the actively developed area. |
| `Chart/` | User-controlled legacy plot scripts. See restrictions below. |
| `deploy/`, `tests/`, `scripts/` | Manifests, suites, launchers. |

## Guardrails

- Preserve the IBG mathematics and behavior. Keep Kubernetes, traffic, and telemetry
  behind adapters instead of embedding them in the solver.
- Preserve the separated jitter contract. Physical selected-processing latency uses
  nonnegative `half-normal-additive-v1` scales 6/5.25/4/3.25 ms for states 1–4. The
  active `physical-only-v1` outcome mode uses observed selected processing for
  realized utility and the 110-ms SLA; reversible `physical-plus-pair-v1` restores the
  historical physical-plus-pair outcome. Physical, pair, and raw end-to-end values all
  stay recorded. The selected-only learning signal adds an independent nonnegative
  `half-normal-observation-v1` disturbance with scales 7.2/6.3/4.8/3.9 ms, and its
  four-state likelihood must remain the exact convolution of the two half-normal laws.
- Never collapse the physical and observation distributions, feed observation-only
  noise into SLA/realized utility, or change either scale table without explicit user
  direction and new calibration evidence. The older 8/7/5.5/4.5-ms values are
  version-bounded history, not active scales.
- Preserve the Phase 4.1 Kernel runtime: each public forwarder runs two Uvicorn workers
  at request/limit 25m/1 CPU and 128/256 MiB, with matched 30-second idle keep-alive on
  its downstream HTTPX client and Uvicorn server; the local private-processor client
  keeps the processor-compatible default window and each private processor stays
  single-worker. Do not retune resources, connection limits/windows, or normalize the
  raw pair residual without new authorization and controlled evidence.
- Opt-in diagnostics are additive only and must never change `link_cost_ms`, processing
  latency, SLA, utility, selection, or learning: `forwarding_path_v3` (with
  `http_client_path_v2`), `solver_resource_v1` (`--memory 1` only), and `netem_v1`
  (`--netem 1`, replica-Pod `eth0` egress delay/jitter only, off by default).
  Existing traces cannot be backfilled. Packet loss stays deferred — the no-rejection
  route contract fails a slot on a dropped request; do not add retries or imputation.
- Prefer small, reviewable changes. Plan substantial work before implementing.
- Do not rewrite generated CSV data, pickles, old copies, or unrelated algorithm
  variants unless asked.
- Do not claim real DPDK, VPP, SR-IOV, hugepage, or line-rate validation. DPDK/VPP
  scope is deferred entirely; `kernel` is the only runtime mode.
- Before declaring a task complete, run the relevant focused tests and report what was
  actually verified — including failures.

## Files with access restrictions

Read or edit these **only when the user asks for them in the current request**:

- `Tutorial.md` — user-directed beginner guide.
- `Report.md` — user-directed paper-vs-testbed comparison.
- `EVIDENCE_SUMMARY.md` — user-directed Phase 4 evidence inventory.
- `Chart/` — user-controlled legacy plots. When directed, read only its `.py` scripts.
  Preserve each script's original visual design and embedded text. Never stage, commit,
  or push `Chart/` content without explicit approval for that content.
- `AGENTS.md` — another assistant's working agreement. Read it; never edit it.
- `ibg backup/` — pre-correction snapshot; do not inspect without an explicit request.

## Contract and versioning discipline

This repo versions its contracts by name (for example `pure-greedy-budgeted-l2-v2`,
`greedy-kernel-slot-evidence-v2`, `greedy-experiment-jsonl-v2`). When behavior changes:

- Bump only the contracts actually affected; leave unrelated ones alone.
- Keep historical traces immutable and readable through an explicitly version-bounded
  compatibility path. New writers must not fabricate old fields.
- Refuse mixed-generation CSV rather than inventing an implicit migration.
- Record the change in `DECISIONS.md` with its reasoning, not just in code.

## Cross-policy comparison honesty

Greedy, Hybrid, IBG-Exact, and MILP are compared against each other. When their inputs
or semantics are not actually matched, say so and record it as an unresolved comparison
mismatch (see the admission-capacity entry in `DECISIONS.md`) rather than implying a
same-input performance claim.

## Documentation discipline

- `ARCHITECTURE.md` — stable system structure and data flow.
- `DECISIONS.md` — accepted choices, constraints, deferred features.
- `ROADMAP.md` — ordered phases and their acceptance gates.
- `STATUS.md` — environment facts, current progress, blockers, next action.
