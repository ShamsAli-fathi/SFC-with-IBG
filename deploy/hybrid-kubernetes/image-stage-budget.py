"""Image-local compatibility boundary for the frozen Hybrid L=2 constant."""

HYBRID_STAGE_BUDGET = 2


def require_hybrid_stage_budget(stage_budget):
    """Validate the active, deliberately non-configurable Hybrid budget."""

    if isinstance(stage_budget, bool) or not isinstance(stage_budget, int):
        raise TypeError("stage_budget must be an integer")
    if stage_budget != HYBRID_STAGE_BUDGET:
        raise ValueError(
            "the active Hybrid action model supports exactly "
            f"L={HYBRID_STAGE_BUDGET}; changing L requires deliberate "
            "planner, embedding, traffic, replay, and test changes"
        )
    return HYBRID_STAGE_BUDGET
