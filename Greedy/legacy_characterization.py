"""Import-free static characterization of the historical ``Greedy/`` files."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


LEGACY_ROOT = Path(__file__).resolve().parent
LEGACY_SOURCE_FILES = (
    "budgeted.py",
    "claude.py",
    "header.py",
    "header_b.py",
    "main.py",
    "report.py",
    "test.py",
)


class LegacyDisposition(str, Enum):
    REUSE_WITH_COMPATIBILITY_TESTS = "reuse-with-compatibility-tests"
    REFERENCE_ONLY = "reference-only"
    RETIRE = "retire"


@dataclass(frozen=True)
class LegacyCallableClassification:
    disposition: LegacyDisposition
    reason: str


@dataclass(frozen=True)
class LegacyCharacterization:
    import_time_execution_files: tuple[str, ...]
    experiment_loop_range: tuple[int, int]
    hard_coded_flow_count: int
    hard_coded_stage_count: int
    hard_coded_replica_count: int
    active_budgeted_flag: int
    global_random_calls: tuple[str, ...]
    explicit_seed_calls: tuple[str, ...]
    csv_write_files: tuple[str, ...]
    top_level_callable_names: tuple[str, ...]

    @property
    def hard_coded_total_replica_count(self) -> int:
        return self.hard_coded_stage_count * self.hard_coded_replica_count


def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    current: ast.AST = node.func
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _source_trees(root: Path) -> dict[str, ast.Module]:
    return {
        filename: ast.parse((root / filename).read_text(encoding="utf-8"), filename)
        for filename in LEGACY_SOURCE_FILES
    }


def _constant_assignments(nodes: list[ast.stmt]) -> dict[str, object]:
    assignments: dict[str, object] = {}
    for node in nodes:
        for descendant in ast.walk(node):
            if not isinstance(descendant, (ast.Assign, ast.AnnAssign)):
                continue
            targets = descendant.targets if isinstance(descendant, ast.Assign) else [descendant.target]
            value_node = descendant.value
            if value_node is None:
                continue
            try:
                value = ast.literal_eval(value_node)
            except (ValueError, TypeError):
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = value
    return assignments


def _top_level_callables(tree: ast.Module, filename: str) -> tuple[str, ...]:
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(f"{filename}:{node.name}")
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.append(f"{filename}:{node.name}.{child.name}")
    return tuple(names)


def characterize_legacy_sources(root: Path = LEGACY_ROOT) -> LegacyCharacterization:
    """Inspect syntax only; no historical module is imported or executed."""
    root = Path(root)
    trees = _source_trees(root)
    main_tree = trees["main.py"]
    main_loop = next(node for node in main_tree.body if isinstance(node, ast.For))
    if not isinstance(main_loop.iter, ast.Call) or _call_name(main_loop.iter) != "range":
        raise ValueError("legacy main experiment loop is no longer a range")
    loop_range = tuple(ast.literal_eval(argument) for argument in main_loop.iter.args)
    if len(loop_range) != 2:
        raise ValueError("legacy main experiment loop must have two range bounds")
    assignments = _constant_assignments(main_loop.body)

    import_time_files: list[str] = []
    random_calls: set[str] = set()
    seed_calls: set[str] = set()
    csv_writers: set[str] = set()
    callable_names: list[str] = []
    for filename, tree in trees.items():
        callable_names.extend(_top_level_callables(tree, filename))
        executable = [
            node
            for node in tree.body
            if not isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
        ]
        if executable:
            import_time_files.append(filename)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name.startswith(("random.", "np.random.", "numpy.random.", "uuid.uuid4")):
                random_calls.add(name)
            if name.endswith(".seed") or name == "seed":
                seed_calls.add(name)
            if name.endswith(".to_csv") or name in {"open", "pd.read_csv"}:
                csv_writers.add(filename)

    return LegacyCharacterization(
        import_time_execution_files=tuple(sorted(import_time_files)),
        experiment_loop_range=(int(loop_range[0]), int(loop_range[1])),
        hard_coded_flow_count=int(assignments["number_of_flows"]),
        hard_coded_stage_count=int(assignments["num_of_stages"]),
        hard_coded_replica_count=int(assignments["num_of_replicas"]),
        active_budgeted_flag=int(assignments["is_budgeted"]),
        global_random_calls=tuple(sorted(random_calls)),
        explicit_seed_calls=tuple(sorted(seed_calls)),
        csv_write_files=tuple(sorted(csv_writers)),
        top_level_callable_names=tuple(sorted(callable_names)),
    )


def _entry(disposition: LegacyDisposition, reason: str) -> LegacyCallableClassification:
    return LegacyCallableClassification(disposition, reason)


LEGACY_CALLABLE_CLASSIFICATIONS = {
    "budgeted.py:link_utility": _entry(LegacyDisposition.REFERENCE_ONLY, "Historical state-pair link deduction; link cost is excluded from Greedy selection."),
    "budgeted.py:_draw_from_belief_vec": _entry(LegacyDisposition.RETIRE, "Uses the global NumPy stream and obsolete Gaussian mixture."),
    "budgeted.py:build_utility_grids_budgeted": _entry(LegacyDisposition.RETIRE, "Builds stochastic Pandas/Monte-Carlo grids for the two-stage path."),
    "budgeted.py:backward_budgeted_memoized": _entry(LegacyDisposition.REFERENCE_ONLY, "Its two-stage immediate-sum shape is relevant, but its stochastic grid implementation retires."),
    "budgeted.py:embedding_budgeted": _entry(LegacyDisposition.REFERENCE_ONLY, "Useful only to characterize the active two-stage route shape."),
    "claude.py:backward_d_memoized_simple": _entry(LegacyDisposition.REFERENCE_ONLY, "Dormant per-stage path demonstrates stochastic scoring and replica-zero rejection."),
    "header.py:Replica.__init__": _entry(LegacyDisposition.REFERENCE_ONLY, "Documents historical replica fields that do not define the active schema."),
    "header.py:Replica.__repr__": _entry(LegacyDisposition.RETIRE, "Legacy console formatting exposes hidden state."),
    "header.py:Replica.utility_kernel": _entry(LegacyDisposition.REFERENCE_ONLY, "Historical inverse-latency utility is superseded by the active linear utility."),
    "header.py:Replica.eval_util": _entry(LegacyDisposition.REFERENCE_ONLY, "Historical Monte-Carlo averaging is not the deterministic Greedy expectation."),
    "header.py:Replica.local_update": _entry(LegacyDisposition.REUSE_WITH_COMPATIBILITY_TESTS, "Reuse the active frozen IBG update behavior, not this copied method."),
    "header.py:Replica.tasting": _entry(LegacyDisposition.RETIRE, "Collapses the signal model and uses global NumPy randomness."),
    "header.py:Replica.aggregation": _entry(LegacyDisposition.REUSE_WITH_COMPATIBILITY_TESTS, "Reuse the active frozen IBG aggregation behavior, not this copied method."),
    "header.py:update": _entry(LegacyDisposition.REUSE_WITH_COMPATIBILITY_TESTS, "Preserve selected-only orchestration through IBG.learning.apply_observations."),
    "header.py:backward_d": _entry(LegacyDisposition.RETIRE, "Obsolete per-stage solver construction."),
    "header.py:delay_gen": _entry(LegacyDisposition.RETIRE, "Hard-coded random profile generation is outside the active profile contract."),
    "header.py:predicting": _entry(LegacyDisposition.REFERENCE_ONLY, "Demonstrates positive-only selection and the replica-zero sentinel."),
    "header.py:embedding": _entry(LegacyDisposition.REFERENCE_ONLY, "Demonstrates the replica-zero negative-index load mutation defect."),
    "header.py:is_equilibrium": _entry(LegacyDisposition.REUSE_WITH_COMPATIBILITY_TESTS, "Reuse the strict active predicate with an explicit 0.04 threshold."),
    "header.py:log_results": _entry(LegacyDisposition.RETIRE, "Direct legacy CSV writes are replaced by validated host-side evidence."),
    "header.py:create_belief_csv": _entry(LegacyDisposition.RETIRE, "Direct legacy CSV writes are replaced by validated host-side evidence."),
    "header.py:pdf_cal": _entry(LegacyDisposition.RETIRE, "Uses a single truncated-normal likelihood instead of exact convolved learning likelihood."),
    "header.py:_lookup_utility": _entry(LegacyDisposition.RETIRE, "Budgeted Pandas/array compatibility shim is unnecessary."),
    "header.py:_iter_embed_choices": _entry(LegacyDisposition.RETIRE, "Budgeted two-choice compatibility shim is unnecessary."),
    "header.py:aggregate_utility_per_flow": _entry(LegacyDisposition.REFERENCE_ONLY, "Documents the historical two-stage link-deducted metric only."),
    "header.py:aggregate_utility_total": _entry(LegacyDisposition.REFERENCE_ONLY, "Documents the historical two-stage link-deducted metric only."),
    "header.py:latency": _entry(LegacyDisposition.REFERENCE_ONLY, "Documents historical synthetic state-pair and congestion latency only."),
    "header.py:jain_index": _entry(LegacyDisposition.REUSE_WITH_COMPATIBILITY_TESTS, "Reuse the active IBG Jain helper with a compatibility test."),
    "header.py:SLA_v_b_v2": _entry(LegacyDisposition.REFERENCE_ONLY, "Historical 15-ms excess is retained only as divergence evidence."),
    "header_b.py:update_b": _entry(LegacyDisposition.REFERENCE_ONLY, "Selected-only shape is informative but depends on obsolete tasting semantics."),
    "header_b.py:SLA_v_b": _entry(LegacyDisposition.RETIRE, "State-based SLA is not an active latency SLA."),
    "report.py:SLA_v": _entry(LegacyDisposition.RETIRE, "State-based route SLA is superseded by strict raw end-to-end latency."),
    "report.py:csv_gen_SLA": _entry(LegacyDisposition.RETIRE, "Direct wide CSV mutation is outside Phase 0 and bypasses trace validation."),
    "report.py:csv_gen_util": _entry(LegacyDisposition.RETIRE, "Direct wide CSV mutation is outside Phase 0 and bypasses trace validation."),
    "report.py:plot_sla_violations": _entry(LegacyDisposition.RETIRE, "Plotting and Chart work are outside the Greedy baseline contract."),
    "report.py:csv_gen_jain": _entry(LegacyDisposition.RETIRE, "Direct wide CSV mutation is outside Phase 0 and bypasses trace validation."),
    "report.py:csv_gen_time": _entry(LegacyDisposition.RETIRE, "Direct wide CSV mutation is outside Phase 0 and bypasses trace validation."),
    "test.py:fill_column_with_trend": _entry(LegacyDisposition.RETIRE, "Fabricating missing SLA values is incompatible with validated evidence."),
}
