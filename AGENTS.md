# Codex Working Agreement

Read `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`, and `STATUS.md` before planning or changing this repository. Treat them as the project handoff record and update them when architecture, decisions, sequencing, or progress materially changes. Exception: during an explicitly authorized iterative visual adjustment to an already-authorized Chart plot (for example, range, title, label, or styling), do not reread or update handoffs unless the user explicitly asks to record the choice as final.

## Project goal

Build the SFC-with-IBG testbed incrementally. The current implemented roadmap migrates the active decoupled Indian Buffet Game (IBG) Python simulation into a lightweight Kubernetes testbed while preserving its equilibrium, utility, belief-update, and reporting logic. Future coupled, budgeted, datapath, or baseline extensions require explicit scope before changing the current behavior.

## Guardrails

- The Python files directly under `IBG/` are the reference simulation. The budgeted/coupled path is out of scope unless explicitly requested.
- Preserve the IBG mathematics and behavior. Isolate Kubernetes, traffic, and telemetry concerns behind adapters instead of embedding them in the solver.
- Preserve the active separated jitter contract. Actual selected processing latency uses nonnegative `half-normal-additive-v1` physical scales 6/5.25/4/3.25 ms for states 1--4. The active `physical-only-v1` outcome mode uses the observed selected processing total for realized utility and the 90-ms SLA; the reversible `physical-plus-pair-v1` mode restores the historical physical-plus-pair outcome. Both physical, pair, and raw end-to-end values remain recorded. The selected-only learning signal adds an independent nonnegative `half-normal-observation-v1` disturbance with state scales 7.2/6.3/4.8/3.9 ms. Its four-state likelihood must remain the exact convolution of the physical and observation half-normal laws.
- Do not collapse the physical and observation distributions, feed observation-only noise into SLA/realized utility, or change either scale table without explicit user direction and new calibration evidence.
- The earlier 8/7/5.5/4.5-ms values were physical-jitter scales and were still considered too accurate for the user's intended belief uncertainty. They are not the active physical or observation scales and must remain version-bounded historical values.
- Preserve the current Phase 4.1 Kernel runtime configuration while its remaining transient residual is diagnosed: each public forwarder runs two Uvicorn workers with request/limit 25m/1 CPU and 128/256 MiB. Its downstream public-forwarder HTTPX client and Uvicorn server use matched 30-second idle keep-alive windows, while its separate local private-processor HTTPX client retains the processor-compatible default idle window; each private processor remains single-worker and unchanged. This configuration follows fixed-route, cgroup, and connection-lifetime A/B evidence for concurrent public-forwarder HTTP queueing; it does not alter the solver, learning, SLA, utility, or pair-cost semantics. Do not retune these resources, connection limits/windows, or normalize the raw pair residual without new explicit authorization and controlled evidence.
- Preserve the opt-in forwarding-path diagnostic boundary. Historical `forwarding_path_v1`/`v2` traces remain summarizable; active `forwarding_path_v3` retains their aggregates and adds source HTTP-client pool/connect/send/receive milestones through `http_client_path_v2`. This is same-clock diagnostic telemetry only. It must never change or replace `link_cost_ms`, processing latency, SLA, utility, selection, or learning. The recorded 30-second client/server keep-alive A/B confirms connection reuse but not stable pair cost; do not alter it without new controlled evidence.
- Preserve the opt-in `solver_resource_v1` boundary. Only `--memory 1` samples current controller-process RSS and records exact-policy memo-cache entries; ordinary runs emit no solver-resource block. Memory bytes/MiB and cache-entry counts are separate units. This instrumentation must not change the exact recurrence, placement, selected-only learning, outcome metrics, runtime resources, or raw pair measurement. Existing traces cannot be backfilled, and no heuristic is authorized yet.
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
