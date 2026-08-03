"""Compatibility entry point for the retired prototype module name.

The former module ran fifty experiments during import.  Phase 1 deliberately
routes explicit execution to the configuration-only CLI; production solving
starts in Phase 2.
"""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
