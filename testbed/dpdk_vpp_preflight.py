"""Read-only host preflight for the planned DPDK/VPP datapath."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import platform
import shutil


PREFLIGHT_SCHEMA_VERSION = "dpdk_vpp_preflight_v1"


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    passed: bool
    required: bool
    detail: str


def _rooted(root: Path, absolute_path: str) -> Path:
    return root / absolute_path.lstrip("/")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _hugepage_total(root: Path) -> int:
    for line in _read_text(_rooted(root, "/proc/meminfo")).splitlines():
        if line.startswith("HugePages_Total:"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                return 0
    return 0


def _iommu_group_count(root: Path) -> int:
    path = _rooted(root, "/sys/kernel/iommu_groups")
    try:
        return sum(1 for entry in path.iterdir() if entry.is_dir())
    except OSError:
        return 0


def _default_route_interfaces(root: Path) -> set[str]:
    interfaces = set()
    lines = _read_text(_rooted(root, "/proc/net/route")).splitlines()
    for line in lines[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "00000000":
            interfaces.add(fields[0])
    return interfaces


def _pci_network_interfaces(root: Path) -> tuple[list[str], list[str]]:
    path = _rooted(root, "/sys/class/net")
    default_routes = _default_route_interfaces(root)
    interfaces = []
    safe_candidates = []
    try:
        entries = sorted(path.iterdir(), key=lambda item: item.name)
    except OSError:
        entries = []
    for entry in entries:
        if entry.name == "lo" or not (entry / "device").exists():
            continue
        interfaces.append(entry.name)
        # If the default route is not visible (for example inside a restricted
        # network namespace), do not guess that a PCI NIC is safe to detach.
        if default_routes and entry.name not in default_routes:
            safe_candidates.append(entry.name)
    return interfaces, safe_candidates


def collect_dpdk_vpp_preflight(
    *,
    root: Path | str = Path("/"),
    command_resolver=shutil.which,
    machine: str | None = None,
    cpu_count: int | None = None,
) -> dict:
    """Collect deterministic, read-only prerequisites without changing the host."""

    root = Path(root)
    machine = machine or platform.machine()
    cpu_count = cpu_count if cpu_count is not None else (os.cpu_count() or 0)
    hugepages = _hugepage_total(root)
    iommu_groups = _iommu_group_count(root)
    vfio_path = _rooted(root, "/dev/vfio/vfio")
    interfaces, safe_candidates = _pci_network_interfaces(root)
    commands = {
        name: command_resolver(name)
        for name in ("vpp", "vppctl", "dpdk-testpmd", "dpdk-devbind.py")
    }

    checks = [
        PreflightCheck(
            "supported_architecture",
            machine in {"x86_64", "aarch64"},
            True,
            f"machine={machine}",
        ),
        PreflightCheck(
            "minimum_cpu_visibility",
            cpu_count >= 2,
            True,
            f"online_cpus={cpu_count}; dedicated placement still requires configuration",
        ),
        PreflightCheck(
            "vpp_runtime",
            bool(commands["vpp"] and commands["vppctl"]),
            True,
            f"vpp={commands['vpp'] or 'missing'}, "
            f"vppctl={commands['vppctl'] or 'missing'}",
        ),
        PreflightCheck(
            "dpdk_tooling",
            bool(commands["dpdk-testpmd"] and commands["dpdk-devbind.py"]),
            True,
            f"dpdk-testpmd={commands['dpdk-testpmd'] or 'missing'}, "
            f"dpdk-devbind.py={commands['dpdk-devbind.py'] or 'missing'}",
        ),
        PreflightCheck(
            "hugepages",
            hugepages > 0,
            True,
            f"HugePages_Total={hugepages}",
        ),
        PreflightCheck(
            "iommu_groups",
            iommu_groups > 0,
            True,
            f"iommu_group_count={iommu_groups}",
        ),
        PreflightCheck(
            "vfio_device",
            vfio_path.exists(),
            True,
            f"path={vfio_path}, exists={vfio_path.exists()}",
        ),
        PreflightCheck(
            "separate_dataplane_interface",
            bool(safe_candidates),
            True,
            "pci_network_interfaces="
            f"{interfaces or ['none']}, non_default_route_candidates="
            f"{safe_candidates or ['none']}",
        ),
    ]
    blockers = [check.name for check in checks if check.required and not check.passed]
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "ready": not blockers,
        "checks": [asdict(check) for check in checks],
        "blockers": blockers,
        "host_changes_performed": False,
    }


def format_dpdk_vpp_preflight(report: dict) -> str:
    lines = [
        "DPDK/VPP host preflight: "
        + ("READY" if report["ready"] else "BLOCKED"),
    ]
    for check in report["checks"]:
        mark = "PASS" if check["passed"] else "FAIL"
        lines.append(f"  [{mark}] {check['name']}: {check['detail']}")
    if report["blockers"]:
        lines.append("  blockers: " + ", ".join(report["blockers"]))
    lines.append("  host changes performed: no")
    return "\n".join(lines)


def require_dpdk_vpp_preflight(report: dict) -> None:
    if not report.get("ready"):
        blockers = ", ".join(report.get("blockers", ())) or "unknown"
        raise RuntimeError(f"DPDK/VPP host preflight failed: {blockers}")
