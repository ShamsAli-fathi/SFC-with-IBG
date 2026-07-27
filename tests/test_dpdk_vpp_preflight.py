from pathlib import Path

import pytest

from IBG.datapath import (
    DPDK_VPP_DATAPATH_MODE,
    KERNEL_DATAPATH_MODE,
    require_datapath_mode,
)
from testbed.dpdk_vpp_preflight import (
    collect_dpdk_vpp_preflight,
    format_dpdk_vpp_preflight,
    require_dpdk_vpp_preflight,
)


def _write(path: Path, text: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _ready_root(tmp_path):
    _write(
        tmp_path / "proc/meminfo",
        "MemTotal: 1000 kB\nHugePages_Total: 128\n",
    )
    _write(
        tmp_path / "proc/net/route",
        "Iface Destination Gateway Flags RefCnt Use Metric Mask\n"
        "mgmt0 00000000 00000000 0003 0 0 0 00000000\n",
    )
    (tmp_path / "sys/kernel/iommu_groups/0").mkdir(parents=True)
    _write(tmp_path / "dev/vfio/vfio")
    (tmp_path / "sys/class/net/mgmt0/device").mkdir(parents=True)
    (tmp_path / "sys/class/net/dp0/device").mkdir(parents=True)


def _all_commands(name):
    return f"/usr/bin/{name}"


def test_dpdk_vpp_is_known_but_not_yet_a_deployable_runtime():
    assert require_datapath_mode(DPDK_VPP_DATAPATH_MODE) == DPDK_VPP_DATAPATH_MODE
    assert require_datapath_mode(KERNEL_DATAPATH_MODE, runtime=True) == "kernel"
    with pytest.raises(ValueError, match="unsupported datapath mode"):
        require_datapath_mode(DPDK_VPP_DATAPATH_MODE, runtime=True)


def test_preflight_passes_only_when_all_minimum_host_prerequisites_exist(tmp_path):
    _ready_root(tmp_path)

    report = collect_dpdk_vpp_preflight(
        root=tmp_path,
        command_resolver=_all_commands,
        machine="x86_64",
        cpu_count=4,
    )

    assert report["ready"] is True
    assert report["blockers"] == []
    assert report["host_changes_performed"] is False
    require_dpdk_vpp_preflight(report)
    assert "DPDK/VPP host preflight: READY" in format_dpdk_vpp_preflight(report)


def test_preflight_reports_blockers_without_changing_host(tmp_path):
    _write(tmp_path / "proc/meminfo", "HugePages_Total: 0\n")

    report = collect_dpdk_vpp_preflight(
        root=tmp_path,
        command_resolver=lambda _name: None,
        machine="x86_64",
        cpu_count=4,
    )

    assert report["ready"] is False
    assert {
        "vpp_runtime",
        "dpdk_tooling",
        "hugepages",
        "iommu_groups",
        "vfio_device",
        "separate_dataplane_interface",
    } <= set(report["blockers"])
    assert report["host_changes_performed"] is False
    with pytest.raises(RuntimeError, match="host preflight failed"):
        require_dpdk_vpp_preflight(report)


def test_preflight_does_not_treat_a_nic_as_safe_without_visible_default_route(
    tmp_path,
):
    _ready_root(tmp_path)
    _write(
        tmp_path / "proc/net/route",
        "Iface Destination Gateway Flags RefCnt Use Metric Mask\n",
    )

    report = collect_dpdk_vpp_preflight(
        root=tmp_path,
        command_resolver=_all_commands,
        machine="x86_64",
        cpu_count=4,
    )

    assert report["ready"] is False
    assert "separate_dataplane_interface" in report["blockers"]
