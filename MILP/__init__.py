"""Import-safe public boundary for the coupled/budgeted MILP baseline."""

from .contracts import (
    MILP_PHASE1_CONTRACT_VERSION,
    DirectedPlanningLink,
    MILPConfiguration,
    MILPPlacement,
    MILPProblemInput,
    MILPSolverResult,
    ReplicaPlanningInput,
)
from .phase0_contract import (
    MILP_ACTION_CARDINALITY,
    MILP_PHASE0_CONTRACT_VERSION,
    MILPContractError,
    MILPDimensions,
    ReplicaAdmission,
    ReplicaKey,
    SolverResultStatus,
    SolverRunProvenance,
    TwoStageAction,
)
from .model import build_coupled_milp_model
from .runner import (
    MILPSlotExecutionError,
    format_milp_slot_metrics,
    run_and_print_milp_slot,
    run_milp_slot,
)
from .scaling import (
    MILP_PHASE4_SCALE_CONTRACT_VERSION,
    MILPScaleCase,
    MILPScaleEvidence,
    MILPScaleRunResult,
    format_scale_evidence,
    make_scale_case,
    make_scale_ladder,
    run_scale_case,
)
from .simulation import InProcessMILPSimulationAdapter
from .kernel_contracts import (
    MILP_PHASE5_KERNEL_CONTRACT_VERSION,
    MILP_TWO_HOP_ROUTE_CONTRACT_VERSION,
    MILPKernelSlotInput,
    MILPKernelSlotResult,
)
from .kernel_runner import (
    format_milp_kernel_metrics,
    run_milp_kernel_slot,
)
from .slot_contracts import (
    MILP_PHASE3_SLOT_CONTRACT_VERSION,
    MILPMeasuredPairOutcome,
    MILPSelectedObservation,
    MILPSlotInput,
    MILPSlotMetrics,
    MILPSlotResult,
    MeasuredPairLatencyProfile,
)
from .solver import solve_coupled_milp
from .diagnostics import (
    MILP_PHASE6_DIAGNOSTIC_VERSION,
    MILPDiagnosticOptions,
    collect_milp_diagnostics,
    diagnostic_compatibility_manifest,
)
from .replay import (
    MILP_PHASE6_REPLAY_VERSION,
    MILPReplayError,
    replay_milp_solver,
    replay_milp_trace,
)
from .trace_contracts import (
    MILP_PHASE6_TRACE_CONTRACT_VERSION,
    MILPTrace,
    MILPTraceSource,
    build_milp_trace,
)
from .experiment_profile import (
    MILP_ASSIGNED_FLOW_CAPACITY_UNIT,
    MILP_EXPERIMENT_PROFILE_VERSION,
    MILPExperimentProfile,
    build_experiment_profile,
    build_experiment_profile_from_runtime_states,
    experiment_profile_from_document,
)

__all__ = (
    "MILP_ACTION_CARDINALITY",
    "MILP_ASSIGNED_FLOW_CAPACITY_UNIT",
    "MILP_EXPERIMENT_PROFILE_VERSION",
    "MILP_PHASE0_CONTRACT_VERSION",
    "MILP_PHASE1_CONTRACT_VERSION",
    "MILP_PHASE3_SLOT_CONTRACT_VERSION",
    "MILP_PHASE4_SCALE_CONTRACT_VERSION",
    "MILP_PHASE5_KERNEL_CONTRACT_VERSION",
    "MILP_PHASE6_DIAGNOSTIC_VERSION",
    "MILP_PHASE6_REPLAY_VERSION",
    "MILP_PHASE6_TRACE_CONTRACT_VERSION",
    "MILP_TWO_HOP_ROUTE_CONTRACT_VERSION",
    "MILPConfiguration",
    "MILPContractError",
    "MILPDimensions",
    "MILPExperimentProfile",
    "MILPPlacement",
    "MILPProblemInput",
    "MILPSolverResult",
    "MILPSlotExecutionError",
    "MILPSlotInput",
    "MILPSlotMetrics",
    "MILPSlotResult",
    "MILPSelectedObservation",
    "MILPMeasuredPairOutcome",
    "MILPScaleCase",
    "MILPScaleEvidence",
    "MILPScaleRunResult",
    "MILPKernelSlotInput",
    "MILPKernelSlotResult",
    "MILPDiagnosticOptions",
    "MILPReplayError",
    "MILPTrace",
    "MILPTraceSource",
    "MeasuredPairLatencyProfile",
    "InProcessMILPSimulationAdapter",
    "DirectedPlanningLink",
    "ReplicaAdmission",
    "ReplicaKey",
    "ReplicaPlanningInput",
    "SolverResultStatus",
    "SolverRunProvenance",
    "TwoStageAction",
    "build_coupled_milp_model",
    "build_experiment_profile",
    "build_experiment_profile_from_runtime_states",
    "build_milp_trace",
    "collect_milp_diagnostics",
    "diagnostic_compatibility_manifest",
    "format_milp_slot_metrics",
    "format_scale_evidence",
    "format_milp_kernel_metrics",
    "make_scale_case",
    "make_scale_ladder",
    "experiment_profile_from_document",
    "run_and_print_milp_slot",
    "run_milp_slot",
    "run_milp_kernel_slot",
    "run_scale_case",
    "replay_milp_solver",
    "replay_milp_trace",
    "solve_coupled_milp",
)
