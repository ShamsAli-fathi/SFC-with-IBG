# Codex Working Agreement

Read `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`, and `STATUS.md` before planning or changing this repository. Treat them as the project handoff record and update them when architecture, decisions, sequencing, or progress materially changes. Exception: during an explicitly authorized iterative visual adjustment to an already-authorized Chart plot (for example, range, title, label, or styling), do not reread or update handoffs unless the user explicitly asks to record the choice as final.

## Project goal

Build the SFC-with-IBG testbed incrementally. The current implemented roadmap migrates the active decoupled Indian Buffet Game (IBG) Python simulation into a lightweight Kubernetes testbed while preserving its equilibrium, utility, belief-update, and reporting logic. Future coupled, budgeted, datapath, or baseline extensions require explicit scope before changing the current behavior.

## Guardrails

- The Python files directly under `IBG/` are the reference simulation. The budgeted/coupled path is out of scope unless explicitly requested.
- Preserve the IBG mathematics and behavior. Isolate Kubernetes, traffic, and telemetry concerns behind adapters instead of embedding them in the solver.
- Preserve the active separated jitter contract. Actual selected processing latency uses nonnegative `half-normal-additive-v1` physical scales 6/5.25/4/3.25 ms for states 1--4 and alone supplies realized utility and SLA inputs. The selected-only learning signal adds an independent nonnegative `half-normal-observation-v1` disturbance with state scales 7.2/6.3/4.8/3.9 ms. Its four-state likelihood must remain the exact convolution of the physical and observation half-normal laws. The local calibration passes, but a fresh normal-build live gate and exact replay are still required before this side branch is complete.
- Do not collapse the physical and observation distributions, feed observation-only noise into SLA/realized utility, or change either scale table without explicit user direction and new calibration evidence.
- The earlier 8/7/5.5/4.5-ms values were physical-jitter scales and were still considered too accurate for the user's intended belief uncertainty. They are not the active physical or observation scales and must remain version-bounded historical values.
- Treat the July 21 exploratory 15-flow/8-replica SLA and iteration-time regression as unresolved. Do not change the 110 ms SLA threshold, claim that the observation-jitter model caused it, or alter the exact solver without a same-environment A/B diagnosis. The likely data-plane hypothesis is public-forwarder CPU throttling/queueing in the pair-RPC residual; the separate controller-admission slowdown is exact-solver CPU work. These are evidence-backed hypotheses, not established causes.
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
