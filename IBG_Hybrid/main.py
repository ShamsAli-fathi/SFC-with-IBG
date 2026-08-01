"""Import-safe executable entry point for one Hybrid simulation slot."""

from __future__ import annotations

from .contracts import HybridConfiguration
from .runner import make_default_hybrid_slot_input, run_and_print_hybrid_slot


DEFAULT_CONFIGURATION = HybridConfiguration()


def main() -> int:
    """Run the authoritative default Phase 5 pure simulation slot."""

    run_and_print_hybrid_slot(make_default_hybrid_slot_input())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
