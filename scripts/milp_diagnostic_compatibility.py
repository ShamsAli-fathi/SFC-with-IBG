#!/usr/bin/env python3
"""Print the static MILP Phase 6 diagnostic compatibility audit."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from MILP.diagnostics import (
    MILP_PHASE6_DIAGNOSTIC_VERSION,
    diagnostic_compatibility_manifest,
)


def main() -> None:
    report = {
        "schema": MILP_PHASE6_DIAGNOSTIC_VERSION,
        "diagnostics": [
            {
                "name": item.name,
                "disposition": item.disposition.value,
                "reason": item.reason,
            }
            for item in diagnostic_compatibility_manifest()
        ],
    }
    print(f"MILP_DIAGNOSTIC_COMPATIBILITY={json.dumps(report, sort_keys=True)}")


if __name__ == "__main__":
    main()
