import json
import math
from collections.abc import Mapping


LEARNING_SIGNAL_SCHEMA = "learning_signal_v1"
LEARNING_SIGNAL_ENCODING = "canonical-json-utf8"
LEARNING_SIGNAL_FIELDS = (
    "stage",
    "flow_id",
    "replica_id",
    "assigned_load",
    "signal_latency_ms",
    "state_likelihood",
)


def build_learning_signal_snapshot(observations):
    """Measure the selected-only logical observation contract.

    This is a canonical projection of the information carried into learning,
    not the byte length of the larger flow-generator response or a wire-byte
    measurement.
    """
    snapshot = _snapshot_from_observations(observations)
    return validate_learning_signal_snapshot(snapshot)


def _snapshot_from_observations(observations):
    records = [_learning_signal_record(item) for item in observations]
    records.sort(
        key=lambda item: (
            item["stage"],
            item["flow_id"],
            item["replica_id"],
        )
    )
    if not records:
        raise ValueError("learning signal must contain at least one selected hop")

    selected_hops = [(item["stage"], item["flow_id"]) for item in records]
    if len(set(selected_hops)) != len(selected_hops):
        raise ValueError("learning signal contains duplicate stage/flow records")

    logical_payload = _canonical_payload(records)
    return {
        "schema": LEARNING_SIGNAL_SCHEMA,
        "encoding": LEARNING_SIGNAL_ENCODING,
        "selection_scope": "selected_hops_only",
        "fields": list(LEARNING_SIGNAL_FIELDS),
        "records": len(records),
        "logical_payload_bytes": len(logical_payload),
        "mean_bytes_per_selected_hop": len(logical_payload) / len(records),
    }


def validate_learning_signal_snapshot(
    snapshot,
    *,
    expected_records=None,
    observations=None,
):
    expected_fields = {
        "schema",
        "encoding",
        "selection_scope",
        "fields",
        "records",
        "logical_payload_bytes",
        "mean_bytes_per_selected_hop",
    }
    if not isinstance(snapshot, dict) or set(snapshot) != expected_fields:
        raise ValueError("invalid learning-signal snapshot fields")
    if snapshot["schema"] != LEARNING_SIGNAL_SCHEMA:
        raise ValueError("unsupported learning-signal schema")
    if snapshot["encoding"] != LEARNING_SIGNAL_ENCODING:
        raise ValueError("unsupported learning-signal encoding")
    if snapshot["selection_scope"] != "selected_hops_only":
        raise ValueError("learning signal must be selected-hops-only")
    if snapshot["fields"] != list(LEARNING_SIGNAL_FIELDS):
        raise ValueError("invalid learning-signal record fields")

    records = snapshot["records"]
    logical_bytes = snapshot["logical_payload_bytes"]
    mean_bytes = snapshot["mean_bytes_per_selected_hop"]
    if not _positive_integer(records):
        raise ValueError("learning-signal records must be a positive integer")
    if not _positive_integer(logical_bytes):
        raise ValueError(
            "learning-signal logical payload bytes must be a positive integer"
        )
    if (
        not isinstance(mean_bytes, (int, float))
        or isinstance(mean_bytes, bool)
        or not math.isfinite(mean_bytes)
        or mean_bytes <= 0
    ):
        raise ValueError(
            "learning-signal mean bytes per selected hop must be positive"
        )
    if not math.isclose(mean_bytes, logical_bytes / records, abs_tol=1e-12):
        raise ValueError("learning-signal mean byte count is inconsistent")

    if expected_records is not None:
        if not _positive_integer(expected_records):
            raise ValueError("expected learning-signal records must be positive")
        if records != expected_records:
            raise ValueError(
                "learning-signal records must equal flows times configured stages"
            )

    if observations is not None:
        expected = _snapshot_from_observations(observations)
        if snapshot != expected:
            raise ValueError(
                "learning-signal footprint does not match selected observations"
            )
    return snapshot


def _learning_signal_record(observation):
    stage = _positive_identifier(observation, "stage")
    flow_id = _positive_identifier(observation, "flow_id")
    replica_id = _positive_identifier(observation, "replica_id")
    assigned_load = _positive_identifier(observation, "congestion")
    signal = _finite_number(observation, "signal")
    if signal <= 0:
        raise ValueError("learning signal latency must be positive")

    likelihood = _read(observation, "likelihood")
    if not isinstance(likelihood, (list, tuple)) or len(likelihood) != 4:
        raise ValueError("learning signal must contain four state likelihoods")
    likelihood = [float(value) for value in likelihood]
    if any(not math.isfinite(value) or value < 0 for value in likelihood):
        raise ValueError("learning-signal likelihoods must be non-negative")
    if sum(likelihood) <= 0:
        raise ValueError("learning-signal likelihoods must have positive mass")

    return {
        "stage": stage,
        "flow_id": flow_id,
        "replica_id": replica_id,
        "assigned_load": assigned_load,
        "signal_latency_ms": signal,
        "state_likelihood": likelihood,
    }


def _canonical_payload(records):
    document = {"schema": LEARNING_SIGNAL_SCHEMA, "signals": records}
    return json.dumps(
        document,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _positive_identifier(observation, name):
    value = _read(observation, name)
    if not _positive_integer(value):
        raise ValueError(f"learning-signal {name} must be a positive integer")
    return value


def _finite_number(observation, name):
    value = _read(observation, name)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"learning-signal {name} must be finite")
    return float(value)


def _read(observation, name):
    if isinstance(observation, Mapping):
        try:
            return observation[name]
        except KeyError as error:
            raise ValueError(f"learning signal is missing {name}") from error
    try:
        return getattr(observation, name)
    except AttributeError as error:
        raise ValueError(f"learning signal is missing {name}") from error


def _positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
