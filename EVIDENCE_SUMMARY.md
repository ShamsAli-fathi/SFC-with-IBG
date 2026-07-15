# Phase 4 Evidence Summary

> Opt-in document: do not read or edit this file in a future task unless the user explicitly requests it in that task.

Updated: 2026-07-15

## Purpose and scope

This file inventories evidence for the completed latency/utility model, calibration, and explicit Kubernetes `kernel` baseline. It does not change or extend the decoupled exact solver, linear utility, selected-only processing-latency signal, hard 250 ms SLA, one-of-M no-rejection behavior, or datapath implementation.

The evidence categories must remain separate:

- **Synthetic design calibration** evaluates the declared FastAPI latency/utility model. It is not a measured Kernel, NIC, DPDK/VPP, or line-rate capacity result.
- **Localhost FastAPI conformance** checks the live HTTP service contract and scheduling tolerance on localhost. It is not Kubernetes telemetry.
- **Live Kubernetes telemetry** measures the selected HTTP routes in the kind cluster. It is distributional evidence, not deterministic mathematical parity.
- **Mathematical replay** reruns captured signals through a specific code version. It is code-version-sensitive and must not be generalized across changed IBG parameters.

## Evidence inventory

| Evidence | Source and provenance | What is currently supported | Boundary |
|---|---|---|---|
| Phase 2 model calibration | `python scripts/phase2_calibrate.py --samples 5000 --seed 2050`; reproduced 2026-07-15 under current HEAD | Gate passed; load horizon 12; crossings 3/5/7/11; minimum classification accuracy 94.42%; sensitivity and illustrative SLA checks passed | Synthetic FastAPI design values only; no cluster or datapath-capacity claim |
| Phase 2 localhost conformance | Recorded in `ARCHITECTURE.md`, `ROADMAP.md`, and `STATUS.md`; 40 observations over four states at baseline and post-capacity loads | Historical accepted result: correlation/signal/likelihood checks passed, minimum per-point classification 80%, maximum overshoot 6.78 ms | Raw localhost output was not identified in the repository during this audit; do not present it as newly reproduced |
| Phase 3 live Kernel baseline | `runs/ibg-experiment-20260713T110905Z.jsonl`; seed 2050; 3 flows, 3 stages, 5 replicas/stage; `kernel`; image `ibg-testbed:kernel-phase3`; Docker 29.6.1; kind 0.32.0; Kubernetes 1.36.1 | Live-telemetry report passes: 9 iterations, 81 selected hops, equilibrium, complete selected-only correlations, ordered load-1 state means, nondecreasing observed congestion groups, 83.95% classification, and 98.77% server-overshoot tolerance pass rate | Lightweight HTTP/Kubernetes Kernel baseline only; not DPDK/VPP, hardware offload, real CNF, or line-rate evidence |
| Phase 3 latency distribution | Same trace and live-telemetry report | Processing mean/p50/p95/max: 16.33/13.13/36.59/52.60 ms; server overshoot: 2.07/0.97/7.52/10.54 ms; transport overhead: 6.85/6.43/11.31/17.87 ms | Transport overhead includes HTTP, DNS, network, and scheduling effects; it is not a direct consecutive-Pod link measurement and has no deterministic ceiling |
| Phase 3 mathematical replay | `python scripts/phase3_kernel_baseline.py runs/ibg-experiment-20260713T110905Z.jsonl` | Historical Phase 3 code, which used global belief retention 0.6, reported zero drift across nine slots and 81 placements/observations | Current HEAD uses retention 0.8. On 2026-07-15 the validator stopped at `replay placement drift for flow 1 stage 1`; current-HEAD zero-drift parity is therefore not established by this trace |
| Current-head Kernel evidence set | Seed 2050: `./scripts/run_experiment.py --seed 2050 --flow 3 --stage 3 --replica 5 --max-iterations 100`, `runs/ibg-experiment-20260715T122305Z.jsonl`; seeds 2051/2052: same command with `--skip-build`, traces `runs/ibg-experiment-20260715T123505Z.jsonl` and `runs/ibg-experiment-20260715T123533Z.jsonl`; each validated 2026-07-15 with `.venv/bin/python scripts/phase3_kernel_baseline.py <trace>` | All three retention-0.8 runs reached equilibrium and replayed exactly: 31 slots, 279 placements/observations, and zero belief/mathematical drift. Seeds 2051 and 2052 each passed every live check, including 100% server-overshoot tolerance across 81 and 99 hops; seed 2050 replayed exactly but passed 89/99 hops (89.90%). | The pooled live rate is 269/279 (96.42%), but that is descriptive evidence only: it does not redefine the existing per-trace 95% scheduling gate or erase the seed-2050 failure. This remains lightweight HTTP/Kubernetes Kernel evidence, not a DPDK/VPP or hardware claim. |
| Exploratory 10-flow Kernel run | `./scripts/run_experiment.py --flow 10 --stage 3 --replica 5 --max-iterations 100 --skip-build`; seed 2050; trace `runs/ibg-experiment-20260715T125302Z.jsonl`; validated 2026-07-15 with `.venv/bin/python scripts/phase3_kernel_baseline.py <trace>` | Reached equilibrium in 10 slots with 300 selected hops; all placements/observations replayed exactly with zero belief/mathematical drift. Classification was 95.67%; 286/300 hops (95.33%) met the server-overshoot tolerance; processing latency mean/p95 was 22.99/42.56 ms and transport-overhead mean/p95 was 26.07/42.69 ms. | Exploratory only: the formal Phase 3 live gate is fixed at three flows. Its validator therefore reports `supported_configuration=false`; it also cannot establish complete load-1 state ordering and observes one small state-4 load-2-to-load-3 mean reversal. Neither result is a replay/mathematical discrepancy or a claim of accepted operation above the validated size. |
| Focused current regression checks | `python -m pytest -q tests/test_characterization.py tests/test_calibration.py tests/test_kernel_baseline.py`; run 2026-07-15 | 16 tests passed, including the characterized retention value 0.8 and focused calibration/Kernel report behavior | Focused suite only; not a live cluster run and not the full test suite |

## Phase 3 trace details

The accepted trace contains one `run_started` event, nine `iteration_completed` events, and one `run_completed` event. Every iteration contains nine placements and nine selected observations. The final iteration records equilibrium.

The recomputed live-telemetry summary from that trace reports:

| Metric | Result |
|---|---:|
| Selected hops | 81 |
| Classification accuracy | 83.95% |
| Server-overshoot tolerance pass rate | 98.77% |
| Processing latency mean / p50 / p95 / max | 16.33 / 13.13 / 36.59 / 52.60 ms |
| Transport overhead mean / p50 / p95 / max | 6.85 / 6.43 / 11.31 / 17.87 ms |
| Load-1 state means, states 1 through 4 | 49.06 / 39.27 / 21.31 / 12.52 ms |

The live telemetry remains useful because changing the controller's belief-retention weight does not retroactively change the HTTP measurements stored in the trace. Replay parity is different: retention affects beliefs and later placements, so it must be established with a trace generated by the same active parameter set.

## Current evidence gap

Commit `550822a` changed global belief retention from 0.6 to 0.8 after the accepted Phase 3 trace was captured. Consequently:

1. The trace remains valid historical live Kernel telemetry.
2. Its historical zero-drift replay is valid only for the pre-change Phase 3 code version.
3. It cannot prove current-HEAD replay parity under retention 0.8.
4. The fresh supported-size retention-0.8 evidence set closes that replay gap: all 31 slots across seeds 2050, 2051, and 2052 replay exactly.
5. Live scheduling is variable in this three-run set: seed 2050 passed 89/99 hops (89.90%), while seeds 2051 and 2052 passed 81/81 and 99/99 (100%). The pooled 269/279 rate (96.42%) is descriptive, not a new aggregate acceptance rule.

Use wording such as: “The accepted Phase 3 Kernel trace passes its live statistical telemetry gate. Three current retention-0.8 traces replay with zero mathematical drift; two meet the per-trace 95% live scheduling threshold, while one records 89.90%, showing live scheduling variability rather than a mathematical discrepancy.”

## Claim boundaries

The evidence supports a small, controlled decoupled IBG testbed with exact continuation play at the validated 3-flow/3-stage/5-replica size, selected-only processing-latency learning signals, linear latency utility, and a hard 250 ms end-to-end SLA.

It does not support claims of DPDK, VPP, SR-IOV, hugepages, hardware offload, real telecom CNFs, line rate, large-scale solver performance, accepted utility beyond 12 assigned flows per replica, flow rejection, or coupled IBG behavior.
