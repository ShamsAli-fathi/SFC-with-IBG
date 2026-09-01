"""Behavior-neutral current-controller CPU, RSS, and cgroup accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from numbers import Integral
from pathlib import Path
import resource
import time
from typing import Callable, Mapping


GREEDY_CONTROLLER_RESOURCE_SCHEMA = "greedy-controller-resource-v1"


def _nonnegative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(value)


@dataclass(frozen=True)
class GreedyControllerResourceSnapshot:
    process_cpu_seconds: float
    process_rss_bytes: int
    cgroup_cpu_nr_throttled: int
    cgroup_cpu_throttled_usec: int

    def __post_init__(self) -> None:
        cpu = float(self.process_cpu_seconds)
        if not isfinite(cpu) or cpu < 0:
            raise ValueError("process CPU seconds must be finite and nonnegative")
        object.__setattr__(self, "process_cpu_seconds", cpu)
        for name in (
            "process_rss_bytes",
            "cgroup_cpu_nr_throttled",
            "cgroup_cpu_throttled_usec",
        ):
            object.__setattr__(self, name, _nonnegative_int(name, getattr(self, name)))


@dataclass(frozen=True)
class GreedyControllerResourceDelta:
    process_cpu_seconds: float
    process_rss_bytes: int
    cgroup_cpu_nr_throttled: int
    cgroup_cpu_throttled_usec: int
    schema: str = GREEDY_CONTROLLER_RESOURCE_SCHEMA

    def __post_init__(self) -> None:
        GreedyControllerResourceSnapshot(
            self.process_cpu_seconds,
            self.process_rss_bytes,
            self.cgroup_cpu_nr_throttled,
            self.cgroup_cpu_throttled_usec,
        )
        if self.schema != GREEDY_CONTROLLER_RESOURCE_SCHEMA:
            raise ValueError("unexpected Greedy controller-resource schema")

    def to_mapping(self) -> dict[str, object]:
        return asdict(self)


ResourceSampler = Callable[[], GreedyControllerResourceSnapshot]


def _proc_rss_bytes(path: Path = Path("/proc/self/status")) -> int:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        # Linux ru_maxrss uses KiB; this fallback is a high-water value.
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    values = [line.split() for line in lines if line.startswith("VmRSS:")]
    if len(values) != 1 or len(values[0]) != 3 or values[0][2] != "kB":
        raise RuntimeError("current controller RSS is unavailable")
    return int(values[0][1]) * 1024


def _cgroup_cpu(path: Path = Path("/sys/fs/cgroup/cpu.stat")) -> tuple[int, int]:
    try:
        entries = {
            parts[0]: int(parts[1])
            for line in path.read_text(encoding="utf-8").splitlines()
            if len(parts := line.split()) == 2
        }
    except (OSError, ValueError):
        return 0, 0
    return entries.get("nr_throttled", 0), entries.get("throttled_usec", 0)


def read_current_controller_resources() -> GreedyControllerResourceSnapshot:
    throttled, throttled_usec = _cgroup_cpu()
    return GreedyControllerResourceSnapshot(
        process_cpu_seconds=time.process_time(),
        process_rss_bytes=_proc_rss_bytes(),
        cgroup_cpu_nr_throttled=throttled,
        cgroup_cpu_throttled_usec=throttled_usec,
    )


def controller_resource_delta(
    before: GreedyControllerResourceSnapshot,
    after: GreedyControllerResourceSnapshot,
) -> GreedyControllerResourceDelta:
    if not isinstance(before, GreedyControllerResourceSnapshot) or not isinstance(
        after, GreedyControllerResourceSnapshot
    ):
        raise TypeError("controller resource samples must use the typed contract")
    if after.process_cpu_seconds < before.process_cpu_seconds:
        raise ValueError("controller CPU counter decreased")
    if after.cgroup_cpu_nr_throttled < before.cgroup_cpu_nr_throttled:
        raise ValueError("controller throttling counter decreased")
    if after.cgroup_cpu_throttled_usec < before.cgroup_cpu_throttled_usec:
        raise ValueError("controller throttled-time counter decreased")
    return GreedyControllerResourceDelta(
        process_cpu_seconds=after.process_cpu_seconds - before.process_cpu_seconds,
        process_rss_bytes=after.process_rss_bytes,
        cgroup_cpu_nr_throttled=(
            after.cgroup_cpu_nr_throttled - before.cgroup_cpu_nr_throttled
        ),
        cgroup_cpu_throttled_usec=(
            after.cgroup_cpu_throttled_usec - before.cgroup_cpu_throttled_usec
        ),
    )


def validate_controller_resource_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "process_cpu_seconds",
        "process_rss_bytes",
        "cgroup_cpu_nr_throttled",
        "cgroup_cpu_throttled_usec",
    }:
        raise ValueError("invalid Greedy controller-resource fields")
    GreedyControllerResourceDelta(
        process_cpu_seconds=value["process_cpu_seconds"],
        process_rss_bytes=value["process_rss_bytes"],
        cgroup_cpu_nr_throttled=value["cgroup_cpu_nr_throttled"],
        cgroup_cpu_throttled_usec=value["cgroup_cpu_throttled_usec"],
        schema=value["schema"],
    )
    return value
