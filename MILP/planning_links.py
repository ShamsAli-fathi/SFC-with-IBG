"""Explicit deterministic planning-link example generation.

The generated coefficients are a reproducible heterogeneous test/demo input,
not measured network latency and not a calibration claim.  Generation is
always explicit: ordinary MILP execution never substitutes this profile for a
requested file or for ``--planning-link-ms``.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from numbers import Integral

from .cli import _positive_integer, _stage_count
from .experiment_profile import MILP_PLANNING_LINK_PROFILE_VERSION
from .phase0_contract import MILPDimensions, required_directed_pairs


MILP_DETERMINISTIC_PLANNING_LINK_SOURCE = (
    "deterministic-heterogeneous-example-v1-not-calibrated"
)


def deterministic_planning_link_cost_ms(
    source_stage: int,
    source_replica: int,
    target_stage: int,
    target_replica: int,
) -> float:
    """Return one stable heterogeneous example coefficient in milliseconds."""

    stage_span = target_stage - source_stage
    replica_distance = abs(target_replica - source_replica)
    endpoint_term = source_replica + (2 * target_replica)
    return round(1.0 + 0.75 * stage_span + 0.2 * replica_distance + 0.01 * endpoint_term, 6)


def build_deterministic_planning_link_document(
    *,
    stage_count: int,
    replicas_per_stage: int,
) -> dict[str, object]:
    """Build a complete canonical explicit profile for a uniform topology."""

    if (
        isinstance(stage_count, bool)
        or not isinstance(stage_count, Integral)
        or stage_count < 2
    ):
        raise ValueError("stage_count must be an integer of at least L=2")
    if (
        isinstance(replicas_per_stage, bool)
        or not isinstance(replicas_per_stage, Integral)
        or replicas_per_stage < 1
    ):
        raise ValueError("replicas_per_stage must be a positive integer")
    stage_count = int(stage_count)
    replicas_per_stage = int(replicas_per_stage)
    dimensions = MILPDimensions(
        flow_count=1,
        replicas_per_stage=(replicas_per_stage,) * stage_count,
    )
    return {
        "contract_version": MILP_PLANNING_LINK_PROFILE_VERSION,
        "source": MILP_DETERMINISTIC_PLANNING_LINK_SOURCE,
        "dimensions": {
            "stage_count": dimensions.stage_count,
            "replicas_per_stage": list(dimensions.replicas_per_stage),
        },
        "links": [
            {
                "source_stage": source.stage,
                "source_replica": source.replica,
                "target_stage": target.stage,
                "target_replica": target.replica,
                "cost_ms": deterministic_planning_link_cost_ms(
                    source.stage,
                    source.replica,
                    target.stage,
                    target.replica,
                ),
            }
            for source, target in required_directed_pairs(dimensions)
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m MILP.planning_links",
        description=(
            "Print a deterministic heterogeneous example planning-link JSON "
            "profile to stdout. The values are not measured/calibrated latency."
        ),
    )
    parser.add_argument("--stage", type=_stage_count, required=True)
    parser.add_argument("--replica", type=_positive_integer, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    print(
        json.dumps(
            build_deterministic_planning_link_document(
                stage_count=arguments.stage,
                replicas_per_stage=arguments.replica,
            ),
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
