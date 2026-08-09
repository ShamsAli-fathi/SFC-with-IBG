"""Manual-only Hybrid Kernel controller policy CLI for Infrastructure Phase 7.5."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from typing import Sequence

from .kernel_phase4_validation import (
    _controller_from_environment,
    run_small_live_gate,
)
from .runner import HYBRID_SLOT_POLICY_LOOKAHEAD, HYBRID_SLOT_POLICY_MC


HYBRID_KERNEL_MC_CONTROLLER_VERSION = (
    "ibg-hybrid-kernel-mc-controller-v1"
)
MAX_HYBRID_KERNEL_MC_WORKERS = 2


@dataclass(frozen=True)
class HybridKernelControllerPolicySelection:
    policy_mode: str
    mc_workers: int | None
    explicit_policy: bool

    @property
    def effective_workers(self) -> int:
        return self.mc_workers if self.mc_workers is not None else 1


def _positive_worker_count(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("MC worker count must be positive")
    if parsed > MAX_HYBRID_KERNEL_MC_WORKERS:
        raise argparse.ArgumentTypeError(
            "MC worker count exceeds the controller bound of "
            f"{MAX_HYBRID_KERNEL_MC_WORKERS}"
        )
    return parsed


def parse_policy_arguments(
    arguments: Sequence[str] | None = None,
) -> HybridKernelControllerPolicySelection:
    parser = argparse.ArgumentParser(
        description=(
            "Run the finite Hybrid Kernel controller; deterministic lookahead "
            "is the default and MC is manual-only."
        )
    )
    parser.add_argument(
        "--policy",
        choices=(HYBRID_SLOT_POLICY_LOOKAHEAD, HYBRID_SLOT_POLICY_MC),
        default=None,
    )
    parser.add_argument("--mc-workers", type=_positive_worker_count, default=None)
    parsed = parser.parse_args(arguments)
    policy_mode = parsed.policy or HYBRID_SLOT_POLICY_LOOKAHEAD
    if policy_mode == HYBRID_SLOT_POLICY_MC and parsed.mc_workers is None:
        parser.error("--policy mc requires --mc-workers N")
    if policy_mode != HYBRID_SLOT_POLICY_MC and parsed.mc_workers is not None:
        parser.error("--mc-workers is valid only with --policy mc")
    return HybridKernelControllerPolicySelection(
        policy_mode=policy_mode,
        mc_workers=parsed.mc_workers,
        explicit_policy=parsed.policy is not None,
    )


def main(arguments: Sequence[str] | None = None) -> int:
    selection = parse_policy_arguments(arguments)
    controller, inputs = _controller_from_environment(
        policy_mode=selection.policy_mode,
        mc_workers=selection.effective_workers,
    )
    evidence = run_small_live_gate(
        controller,
        inputs,
        first_slot=int(os.environ.get("SLOT_ID", "1")),
        iterations=int(os.environ.get("MAX_ITERATIONS", "2")),
        policy_mode=selection.policy_mode,
        mc_workers=selection.effective_workers,
    )
    for item in evidence:
        item["controller_contract_version"] = (
            HYBRID_KERNEL_MC_CONTROLLER_VERSION
        )
        item["explicit_policy"] = selection.explicit_policy
        print(json.dumps(item, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
