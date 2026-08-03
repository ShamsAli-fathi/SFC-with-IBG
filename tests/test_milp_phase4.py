from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import random
import subprocess
import sys

import numpy as np
import pytest

from MILP.benchmark import build_parser, main
from MILP.contracts import MILPSolverResult
from MILP.phase0_contract import SolverResultStatus, SolverRunProvenance
from MILP.scaling import (
    MILP_PHASE4_BACKEND_PARITY,
    MILP_PHASE4_MEMORY_SCOPE,
    MILP_PHASE4_SCALE_CONTRACT_VERSION,
    MILP_PHASE4_SYNTHETIC_PROFILE_VERSION,
    MILP_SCALE_LADDER,
    build_scale_slot_input,
    format_scale_evidence,
    make_scale_case,
    make_scale_ladder,
    run_scale_case,
)


ROOT = Path(__file__).resolve().parents[1]


def test_scale_ladder_is_runtime_configured_and_ends_at_default_boundary():
    cases = make_scale_ladder(cutoff_seconds=1.25)

    assert tuple(
        (
            case.configuration.dimensions.flow_count,
            case.configuration.dimensions.stage_count,
            case.configuration.dimensions.replicas_per_stage[0],
        )
        for case in cases
    ) == MILP_SCALE_LADDER
    assert cases[-1].name == "15x3x10"
    assert cases[-1].configuration.cutoff_seconds == 1.25
    assert all(case.configuration.action_cardinality == 2 for case in cases)


def test_synthetic_scale_profile_is_complete_deterministic_and_rng_neutral():
    case = make_scale_case(
        flow_count=3,
        stage_count=4,
        replicas_per_stage=2,
        cutoff_seconds=2.0,
        profile_seed=55,
        root_seed=66,
        slot_id=7,
    )
    random.seed(101)
    np.random.seed(102)
    python_before = random.getstate()
    numpy_before = np.random.get_state()

    first = build_scale_slot_input(case)
    second = build_scale_slot_input(case)

    assert first == second
    assert first.problem.configuration.dimensions.stage_count == 4
    assert len(first.problem.replicas) == 8
    assert len(first.problem.planning_links) == 24
    assert len(first.measured_pair_profiles) == 24
    assert first.problem.planning_links != tuple(
        # Outcome profiles are deliberately a different contract and shape.
        first.measured_pair_profiles
    )
    assert random.getstate() == python_before
    numpy_after = np.random.get_state()
    assert numpy_after[0] == numpy_before[0]
    assert np.array_equal(numpy_after[1], numpy_before[1])
    assert numpy_after[2:] == numpy_before[2:]


def test_tiny_scale_case_proves_oracle_parity_and_retains_complete_evidence():
    case = make_scale_case(
        flow_count=1,
        stage_count=2,
        replicas_per_stage=1,
        cutoff_seconds=2.0,
    )

    result = run_scale_case(case, verify_oracle=True)
    evidence = result.evidence

    assert evidence.contract_version == MILP_PHASE4_SCALE_CONTRACT_VERSION
    assert evidence.profile_version == MILP_PHASE4_SYNTHETIC_PROFILE_VERSION
    assert evidence.solver_status is SolverResultStatus.PROVEN_OPTIMAL
    assert evidence.optimality_proven
    assert evidence.slot_executed
    assert evidence.oracle_verified
    assert evidence.oracle_complete_placements == 1
    assert evidence.oracle_objective_utility == pytest.approx(
        evidence.incumbent_objective_utility
    )
    assert evidence.variable_count == 9
    assert evidence.constraint_count == 15
    assert evidence.requested_cutoff_seconds == 2.0
    assert evidence.backend_parity == MILP_PHASE4_BACKEND_PARITY
    assert evidence.memory_scope == MILP_PHASE4_MEMORY_SCOPE
    assert evidence.peak_process_rss_after_bytes >= evidence.peak_process_rss_before_bytes
    assert evidence.peak_process_rss_growth_bytes >= 0
    assert result.slot_result is not None
    with pytest.raises(FrozenInstanceError):
        evidence.optimality_proven = False


def test_timeout_without_incumbent_is_honest_scale_evidence_and_skips_slot():
    case = make_scale_case(
        flow_count=15,
        stage_count=3,
        replicas_per_stage=10,
        cutoff_seconds=0.25,
    )

    def timed_without(problem):
        return MILPSolverResult(
            SolverRunProvenance(
                status=SolverResultStatus.TIME_LIMIT_WITHOUT_INCUMBENT,
                requested_cutoff_seconds=problem.configuration.cutoff_seconds,
                model_build_seconds=0.2,
                solve_seconds=0.25,
                backend_name="fixture",
                backend_version="1",
                termination_reason="time limit without incumbent",
                best_bound_utility=123.0,
                variable_count=5475,
                constraint_count=14115,
            )
        )

    result = run_scale_case(case, solver=timed_without)
    evidence = result.evidence

    assert evidence.solver_status is SolverResultStatus.TIME_LIMIT_WITHOUT_INCUMBENT
    assert not evidence.optimality_proven
    assert not evidence.slot_executed
    assert result.slot_result is None
    assert evidence.incumbent_objective_utility is None
    assert evidence.best_bound_utility == 123.0
    assert evidence.relative_gap is None
    assert evidence.simulation_seconds is None
    assert "optimal=0" in format_scale_evidence(evidence)
    assert "incumbent=none" in format_scale_evidence(evidence)


def test_actual_15x3x10_boundary_is_cutoff_bounded_and_never_overclaims_optimality():
    result = run_scale_case(
        make_scale_case(
            flow_count=15,
            stage_count=3,
            replicas_per_stage=10,
            cutoff_seconds=1.0,
        )
    )
    evidence = result.evidence

    assert evidence.requested_cutoff_seconds == 1.0
    assert evidence.variable_count == 5475
    assert evidence.constraint_count == 14115
    assert evidence.solver_status in (
        SolverResultStatus.PROVEN_OPTIMAL,
        SolverResultStatus.TIME_LIMIT_WITH_INCUMBENT,
        SolverResultStatus.TIME_LIMIT_WITHOUT_INCUMBENT,
    )
    assert evidence.optimality_proven == (
        evidence.solver_status is SolverResultStatus.PROVEN_OPTIMAL
    )
    if evidence.slot_executed:
        assert result.slot_result is not None
        assert len(result.slot_result.observations) == 30
        assert len(result.slot_result.measured_pairs) == 15
    else:
        assert evidence.incumbent_objective_utility is None


@pytest.mark.parametrize(
    "arguments",
    [
        ["--cutoff", "0"],
        ["--cutoff", "nan"],
        ["--cutoff", "1", "--profile-seed", "-1"],
        ["--cutoff", "1", "--root-seed", "-1"],
        ["--cutoff", "1", "--stage", "1"],
    ],
)
def test_benchmark_cli_rejects_invalid_cutoff_seed_and_dimensions(arguments):
    with pytest.raises(SystemExit):
        build_parser().parse_args(arguments)


def test_guarded_benchmark_prints_one_compact_line_and_preserves_cutoff(capsys):
    exit_code = main(
        [
            "--flow",
            "1",
            "--stage",
            "2",
            "--replica",
            "1",
            "--cutoff",
            "2.125",
            "--verify-oracle",
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert exit_code == 0
    assert len(lines) == 1
    assert lines[0].startswith("MILP scale=1x2x1 cutoff=2.125s")
    assert "status=proven-optimal optimal=1" in lines[0]
    assert "vars=9 constraints=15" in lines[0]


def test_verbose_benchmark_prints_start_banner_and_final_summary(capsys):
    exit_code = main(
        [
            "--flow",
            "1",
            "--stage",
            "2",
            "--replica",
            "1",
            "--cutoff",
            "2",
            "--verbose",
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert exit_code == 0
    assert lines[0] == (
        "MILP benchmark starting: scale=1x2x1 cutoff=2s "
        "HiGHS-progress=enabled"
    )
    assert lines[-1].startswith("MILP scale=1x2x1 cutoff=2s")
    assert len(lines) >= 2


def test_phase4_imports_are_silent_file_safe_and_rng_neutral(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    code = (
        "import importlib, random, numpy as np; "
        "random.seed(71); np.random.seed(72); "
        "p=random.getstate(); n=np.random.get_state(); "
        "[importlib.import_module(x) for x in "
        "('MILP.scaling','MILP.benchmark','MILP')]; "
        "assert random.getstate()==p; a=np.random.get_state(); "
        "assert a[0]==n[0] and np.array_equal(a[1],n[1]) and a[2:]==n[2:]"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert tuple(tmp_path.iterdir()) == ()
