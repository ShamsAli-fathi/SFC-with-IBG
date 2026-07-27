#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from testbed.dpdk_vpp_preflight import (
    collect_dpdk_vpp_preflight,
    format_dpdk_vpp_preflight,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only host preflight for the planned DPDK/VPP datapath."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the versioned preflight report as JSON",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    report = collect_dpdk_vpp_preflight()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_dpdk_vpp_preflight(report))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
