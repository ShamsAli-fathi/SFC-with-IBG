# Codex Working Agreement

Read `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`, and `STATUS.md` before planning or changing this repository. Treat them as the project handoff record and update them when architecture, decisions, sequencing, or progress materially changes. Exception: during an explicitly authorized iterative visual adjustment to an already-authorized Chart plot (for example, range, title, label, or styling), do not reread or update handoffs unless the user explicitly asks to record the choice as final.

## Project goal

Build the SFC-with-IBG testbed incrementally. The current implemented roadmap migrates the active decoupled Indian Buffet Game (IBG) Python simulation into a lightweight Kubernetes testbed while preserving its equilibrium, utility, belief-update, and reporting logic. Future coupled, budgeted, datapath, or baseline extensions require explicit scope before changing the current behavior.

## Guardrails

- The Python files directly under `IBG/` are the reference simulation. The budgeted/coupled path is out of scope unless explicitly requested.
- Preserve the IBG mathematics and behavior. Isolate Kubernetes, traffic, and telemetry concerns behind adapters instead of embedding them in the solver.
- Preserve the active `half-normal-additive-v1` selected-processing jitter model: jitter is nonnegative additive delay with state-1-through-state-4 scales 6/5.25/4/3.25 ms, and sampling, likelihood, and expected-latency calculations must remain distributionally consistent. These scales have passed local calibration and tests but still require a fresh normal-build live gate before the revised branch is complete.
- A potential separation between physical processing jitter and observation-only learning-signal jitter is under discussion; it is not designed or authorized. Do not add a second signal, alter SLA/utility inputs, or change likelihood semantics without explicit user direction.
- The earlier 8/7/5.5/4.5-ms values were physical-jitter scales, not validated observation-noise scales, and their prior results were still considered too accurate for the user's intended belief uncertainty. Do not reuse those values as an observation-noise prescription without new calibration evidence.
- Prefer small, reviewable changes. Plan substantial work before implementation.
- Do not rewrite generated CSV data, pickle files, old copies, or unrelated algorithm variants unless explicitly requested.
- Do not read large result files wholesale; inspect only targeted rows, columns, or summaries.
- Do not read or edit `Tutorial.md` unless the user explicitly asks for it in the current request.
- Do not read or edit `Report.md` unless the user explicitly asks for it in the current request.
- Do not read or edit `EVIDENCE_SUMMARY.md` unless the user explicitly asks for it in the current request.
- Treat `Chart/` as a user-controlled legacy plot-script area. Do not inspect it unless the user explicitly directs that work in the current request; then read only its `.py` scripts. Edit those scripts only on explicit request, and never stage, commit, or push any `Chart/` content without the user's explicit approval for that content. Preserve the original script's visual design/theme and embedded text unless the user explicitly directs a change. Once a plot script is authorized, handle iterative visual tuning locally; do not read or update handoffs for those non-final tweaks unless the user explicitly requests a final record.
- Do not claim real DPDK, VPP, SR-IOV, hugepage, or line-rate validation.
- Before declaring a task complete, run the relevant focused tests/checks and report what was actually verified.

## Documentation discipline

- `ARCHITECTURE.md`: stable system structure and data flow.
- `DECISIONS.md`: accepted choices, constraints, and deferred features.
- `ROADMAP.md`: ordered migration phases and their acceptance gates.
- `STATUS.md`: environment facts, current progress, blockers, and the next action.
- `Tutorial.md`: user-directed beginner-friendly report and operating guide. It is outside the default handoff workflow and may be read or edited only when explicitly requested by the user.
- `Report.md`: user-directed comparison of the paper draft and lightweight testbed. It is outside the default handoff workflow and may be read or edited only when explicitly requested by the user.
- `EVIDENCE_SUMMARY.md`: user-directed Phase 4 evidence inventory. It is outside the default handoff workflow and may be read or edited only when explicitly requested by the user.
