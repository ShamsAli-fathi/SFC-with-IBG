#!/usr/bin/env python3
"""Render Greedy Phase 4 resources offline; never contacts a cluster."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from Greedy.kernel_infrastructure import (
    parse_resource_documents,
    render_kind_configuration,
    render_long_running_resources,
    render_resource_documents,
    static_deployment_input_from_mapping,
)


def render_input(path: str | Path, component: str) -> str:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    deployment = static_deployment_input_from_mapping(value)
    if component == "long-running":
        rendered = render_resource_documents(
            render_long_running_resources(deployment)
        )
        # Parse immediately so explicit CLI rendering fails closed.
        parse_resource_documents(rendered)
        return rendered
    if component == "kind":
        rendered = render_resource_documents((render_kind_configuration(),))
        parse_resource_documents(rendered)
        return rendered
    raise ValueError(f"unsupported render component: {component}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render Greedy static Kubernetes JSON/YAML without Docker or Kubernetes"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--component",
        choices=("long-running", "kind"),
        required=True,
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    print(render_input(args.input, args.component), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
