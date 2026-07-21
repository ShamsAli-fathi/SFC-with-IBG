"""Versioned controller learning-signal modes.

The default mode is the accepted separated physical/observation model.  The
physical-only option exists solely for controlled, same-deployment diagnostic
comparisons: it changes the controller's learning observation, never the
replica's physical processing, route execution, realized utility, or SLA.
"""

SEPARATED_LEARNING_SIGNAL_MODE = "separated-v1"
PHYSICAL_ONLY_DIAGNOSTIC_LEARNING_SIGNAL_MODE = (
    "physical-only-diagnostic-v1"
)

LEARNING_SIGNAL_MODES = frozenset(
    {
        SEPARATED_LEARNING_SIGNAL_MODE,
        PHYSICAL_ONLY_DIAGNOSTIC_LEARNING_SIGNAL_MODE,
    }
)


def require_learning_signal_mode(mode: str) -> str:
    """Validate and normalize a declared controller learning-signal mode."""
    if not isinstance(mode, str):
        raise ValueError("learning signal mode must be a string")
    normalized = mode.strip()
    if normalized not in LEARNING_SIGNAL_MODES:
        choices = ", ".join(sorted(LEARNING_SIGNAL_MODES))
        raise ValueError(
            f"unsupported learning signal mode {mode!r}; expected one of {choices}"
        )
    return normalized


def is_physical_only_diagnostic_mode(mode: str) -> bool:
    return (
        require_learning_signal_mode(mode)
        == PHYSICAL_ONLY_DIAGNOSTIC_LEARNING_SIGNAL_MODE
    )
