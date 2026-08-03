"""Read-only availability gate for the Phase 2 SciPy/HiGHS backend."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.util import find_spec
from typing import Callable

from .phase0_contract import DEVELOPMENT_BACKEND_FAMILY


class MILPBackendUnavailable(RuntimeError):
    """Raised when the declared free development backend cannot be used."""


@dataclass(frozen=True)
class BackendAvailability:
    family: str
    available: bool
    scipy_version: str | None
    highs_version: str | None
    detail: str


def detect_scipy_highs(
    *,
    module_finder: Callable[[str], object | None] = find_spec,
    module_importer: Callable[[str], object] = import_module,
) -> BackendAvailability:
    """Inspect capability/version without constructing or solving a model."""

    try:
        if module_finder("scipy") is None:
            raise ModuleNotFoundError("SciPy is not installed")
        scipy = module_importer("scipy")
        optimize = module_importer("scipy.optimize")
        if not callable(getattr(optimize, "milp", None)):
            raise ImportError("scipy.optimize.milp is unavailable")
        core = module_importer("scipy.optimize._highspy._core")
        highs_version = ".".join(
            str(getattr(core, name))
            for name in (
                "HIGHS_VERSION_MAJOR",
                "HIGHS_VERSION_MINOR",
                "HIGHS_VERSION_PATCH",
            )
        )
        scipy_version = str(getattr(scipy, "__version__"))
        return BackendAvailability(
            family=DEVELOPMENT_BACKEND_FAMILY,
            available=True,
            scipy_version=scipy_version,
            highs_version=highs_version,
            detail=(
                f"available: SciPy {scipy_version}, embedded HiGHS {highs_version}"
            ),
        )
    except (AttributeError, ImportError, ModuleNotFoundError) as exc:
        return BackendAvailability(
            family=DEVELOPMENT_BACKEND_FAMILY,
            available=False,
            scipy_version=None,
            highs_version=None,
            detail=(
                "SciPy scipy.optimize.milp with embedded HiGHS is required for "
                f"MILP Phase 2 ({type(exc).__name__}: {exc})"
            ),
        )


def require_scipy_highs(
    availability: BackendAvailability | None = None,
) -> BackendAvailability:
    result = availability if availability is not None else detect_scipy_highs()
    if not result.available:
        raise MILPBackendUnavailable(result.detail)
    return result
