SIMULATION_DATAPATH_MODE = "simulation"
KERNEL_DATAPATH_MODE = "kernel"

KNOWN_DATAPATH_MODES = frozenset(
    {
        SIMULATION_DATAPATH_MODE,
        KERNEL_DATAPATH_MODE,
    }
)


def require_datapath_mode(value, *, runtime=False):
    mode = str(value).strip().lower()
    allowed = {KERNEL_DATAPATH_MODE} if runtime else KNOWN_DATAPATH_MODES
    if mode not in allowed:
        expected = ", ".join(sorted(allowed))
        raise ValueError(f"unsupported datapath mode {value!r}; expected {expected}")
    return mode
