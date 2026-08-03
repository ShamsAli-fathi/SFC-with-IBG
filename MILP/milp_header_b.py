"""Import-safe tombstone for the invalid legacy budgeted solver.

The old routine used random replica costs, a hard-coded budget, arbitrary
stage skipping, and OR-Tools CBC.  It is intentionally unavailable rather
than silently exposing behavior that conflicts with the Phase 0 contract.
"""


class RetiredMILPPrototypeError(RuntimeError):
    pass


def MILP_solver_budgeted(*_args, **_kwargs):
    raise RetiredMILPPrototypeError(
        "the legacy budgeted solver is retired; use MILP.solve_coupled_milp "
        "with the Phase 1 problem contracts"
    )
