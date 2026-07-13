#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "IBG"))

from testbed.kernel_baseline import build_kernel_baseline_report
from testbed.profiles import load_profiles
from testbed.validation import replay_kernel_trace


def read_events(trace_path):
    with trace_path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def main():
    parser = argparse.ArgumentParser(
        description="Validate and summarize a Phase 3 Kernel JSONL trace."
    )
    parser.add_argument("trace", type=Path)
    parser.add_argument(
        "--profiles",
        type=Path,
        default=ROOT / "deploy/kubernetes/profiles.json",
    )
    arguments = parser.parse_args()
    events = read_events(arguments.trace)
    profiles = load_profiles(arguments.profiles)
    report = build_kernel_baseline_report(events, profiles)
    report["replay"] = replay_kernel_trace(events, profiles)
    report["gate_passed"] = (
        report["gate_passed"] and report["replay"]["gate_passed"]
    )
    print(f"PHASE3_KERNEL_BASELINE={json.dumps(report, sort_keys=True)}")
    if not report["gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
