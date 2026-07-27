SIMULATION_DATAPATH_MODE = "simulation"
KERNEL_DATAPATH_MODE = "kernel"
DPDK_VPP_DATAPATH_MODE = "dpdk-vpp"

KNOWN_DATAPATH_MODES = frozenset(
    {
        SIMULATION_DATAPATH_MODE,
        KERNEL_DATAPATH_MODE,
        DPDK_VPP_DATAPATH_MODE,
    }
)
RUNTIME_DATAPATH_MODES = frozenset({KERNEL_DATAPATH_MODE})


def require_datapath_mode(value, *, runtime=False):
    mode = str(value).strip().lower()
    allowed = RUNTIME_DATAPATH_MODES if runtime else KNOWN_DATAPATH_MODES
    if mode not in allowed:
        expected = ", ".join(sorted(allowed))
        raise ValueError(f"unsupported datapath mode {value!r}; expected {expected}")
    return mode
