"""Opt-in, non-authoritative HTTP mirror for completed posterior updates."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from math import isfinite
from typing import Mapping, Sequence

from fastapi import FastAPI, HTTPException, Request, status
import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .contracts import ReplicaChoice


PosteriorVector = tuple[float, float, float, float]


HYBRID_POSTERIOR_MIRROR_ENV = "HYBRID_POSTERIOR_MIRROR"
HYBRID_POSTERIOR_MIRROR_URL_ENV = "HYBRID_POSTERIOR_MIRROR_URL"
HYBRID_CONTROLLER_POD_UID_ENV = "HYBRID_CONTROLLER_POD_UID"
HYBRID_POSTERIOR_MIRROR_DEFAULT_URL = (
    "http://ibg-hybrid-posterior-mirror.ibg-hybrid-testbed."
    "svc.cluster.local.:8080"
)
HYBRID_POSTERIOR_MIRROR_SCHEMA = "ibg-hybrid-posterior-mirror-v1"
HYBRID_POSTERIOR_UPDATE_SCHEMA = "ibg-hybrid-posterior-update-v1"
HYBRID_POSTERIOR_RECEIPT_SCHEMA = "ibg-hybrid-posterior-receipt-v1"
HYBRID_POSTERIOR_PROVENANCE_SCHEMA = (
    "ibg-hybrid-posterior-mirror-provenance-v1"
)
HYBRID_POSTERIOR_SERIALIZATION = "canonical-compact-json-utf8-v1"
HYBRID_POSTERIOR_SCOPE = "completed-aggregated-posterior-per-sampled-replica"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_digest(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _normalize_posterior(values: Sequence[float]) -> PosteriorVector:
    if isinstance(values, (str, bytes)):
        raise ValueError("posterior must contain four numeric probabilities")
    raw_values = tuple(values)
    if len(raw_values) != 4:
        raise ValueError("posterior must contain four probabilities")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in raw_values
    ):
        raise ValueError("posterior must contain four numeric probabilities")
    posterior = tuple(float(value) for value in raw_values)
    if any(not isfinite(value) or value < 0 for value in posterior):
        raise ValueError("posterior probabilities must be finite and nonnegative")
    if sum(posterior) <= 0:
        raise ValueError("posterior must have positive probability mass")
    return posterior  # type: ignore[return-value]


def canonical_posterior_vector_bytes(values: Sequence[float]) -> bytes:
    """Encode only the four posterior values, with no identity envelope."""

    posterior = _normalize_posterior(values)
    return json.dumps(
        list(posterior),
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


class HybridPosteriorUpdateDocument(BaseModel):
    """One final aggregated posterior copied to the measurement receiver."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_version: str = Field(
        default=HYBRID_POSTERIOR_UPDATE_SCHEMA,
        alias="schema",
    )
    run_id: str = Field(min_length=1, max_length=128)
    slot_id: int = Field(gt=0)
    stage: int = Field(gt=0)
    replica: int = Field(gt=0)
    posterior: tuple[float, float, float, float]

    @field_validator("schema_version")
    @classmethod
    def _schema_is_current(cls, value: str) -> str:
        if value != HYBRID_POSTERIOR_UPDATE_SCHEMA:
            raise ValueError("unsupported Hybrid posterior-update schema")
        return value

    @field_validator("run_id")
    @classmethod
    def _run_id_is_safe(cls, value: str) -> str:
        if any(character.isspace() for character in value):
            raise ValueError("posterior mirror run_id must not contain whitespace")
        return value

    @field_validator("posterior", mode="before")
    @classmethod
    def _posterior_is_valid(
        cls, value: Sequence[float]
    ) -> tuple[float, float, float, float]:
        return _normalize_posterior(value)


class HybridPosteriorReceipt(BaseModel):
    """Receiver acknowledgement of the exact body and vector it accepted."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_version: str = Field(
        default=HYBRID_POSTERIOR_RECEIPT_SCHEMA,
        alias="schema",
    )
    run_id: str
    slot_id: int
    stage: int
    replica: int
    vector_payload_bytes: int
    vector_sha256: str
    application_body_bytes: int
    application_body_sha256: str


@dataclass(frozen=True)
class HybridCanonicalPosteriorUpdate:
    document: HybridPosteriorUpdateDocument
    vector_payload: bytes
    application_body: bytes

    @property
    def receipt(self) -> HybridPosteriorReceipt:
        return HybridPosteriorReceipt(
            run_id=self.document.run_id,
            slot_id=self.document.slot_id,
            stage=self.document.stage,
            replica=self.document.replica,
            vector_payload_bytes=len(self.vector_payload),
            vector_sha256=_sha256(self.vector_payload),
            application_body_bytes=len(self.application_body),
            application_body_sha256=_sha256(self.application_body),
        )


def build_canonical_posterior_update(
    *,
    run_id: str,
    slot_id: int,
    choice: ReplicaChoice,
    posterior: Sequence[float],
) -> HybridCanonicalPosteriorUpdate:
    document = HybridPosteriorUpdateDocument(
        run_id=run_id,
        slot_id=slot_id,
        stage=choice.stage,
        replica=choice.replica,
        posterior=_normalize_posterior(posterior),
    )
    vector_payload = canonical_posterior_vector_bytes(document.posterior)
    application_body = json.dumps(
        document.model_dump(mode="json", by_alias=True),
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return HybridCanonicalPosteriorUpdate(
        document=document,
        vector_payload=vector_payload,
        application_body=application_body,
    )


def posterior_mirror_provenance(enabled: bool) -> Mapping[str, object]:
    if not isinstance(enabled, bool):
        raise TypeError("posterior mirror enabled setting must be boolean")
    return {
        "schema": HYBRID_POSTERIOR_PROVENANCE_SCHEMA,
        "enabled": enabled,
        "serialization": HYBRID_POSTERIOR_SERIALIZATION,
        "scope": HYBRID_POSTERIOR_SCOPE,
        "transport": "http-pod-to-pod" if enabled else "none",
        "authoritative_belief_owner": "controller-local",
    }


def validate_posterior_mirror_provenance(
    value: object,
    *,
    expected_enabled: bool | None = None,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "enabled",
        "serialization",
        "scope",
        "transport",
        "authoritative_belief_owner",
    }:
        raise ValueError("invalid Hybrid posterior-mirror provenance fields")
    enabled = value.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("Hybrid posterior-mirror enabled value must be boolean")
    expected = posterior_mirror_provenance(enabled)
    if dict(value) != expected:
        raise ValueError("Hybrid posterior-mirror provenance is inconsistent")
    if expected_enabled is not None and enabled is not expected_enabled:
        raise ValueError("Hybrid posterior-mirror provenance drifted")
    return value


def _positive_count(value: object, field: str, *, allow_zero: bool = False) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < (0 if allow_zero else 1)
    ):
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{field} must be a {qualifier} integer")
    return value


def validate_hybrid_posterior_mirror_snapshot(
    snapshot: object,
    *,
    expected_slot_id: int | None = None,
    expected_beliefs: Mapping[ReplicaChoice, Sequence[float]] | None = None,
    expected_updated_choices: Sequence[ReplicaChoice] | None = None,
) -> Mapping[str, object]:
    """Validate one complete set of acknowledged posterior-copy messages."""

    if not isinstance(snapshot, Mapping) or set(snapshot) != {
        "schema",
        "run_id",
        "slot_id",
        "serialization",
        "scope",
        "payload_bytes",
        "messages",
        "updates",
    }:
        raise ValueError("invalid Hybrid posterior-mirror snapshot fields")
    if snapshot.get("schema") != HYBRID_POSTERIOR_MIRROR_SCHEMA:
        raise ValueError("unsupported Hybrid posterior-mirror schema")
    run_id = snapshot.get("run_id")
    if (
        not isinstance(run_id, str)
        or not run_id
        or len(run_id) > 128
        or any(character.isspace() for character in run_id)
    ):
        raise ValueError("invalid Hybrid posterior-mirror run identity")
    slot_id = _positive_count(snapshot.get("slot_id"), "posterior mirror slot_id")
    if expected_slot_id is not None and slot_id != expected_slot_id:
        raise ValueError("Hybrid posterior-mirror slot identity drifted")
    if (
        snapshot.get("serialization") != HYBRID_POSTERIOR_SERIALIZATION
        or snapshot.get("scope") != HYBRID_POSTERIOR_SCOPE
    ):
        raise ValueError("Hybrid posterior-mirror encoding or scope drifted")

    payload = snapshot.get("payload_bytes")
    messages = snapshot.get("messages")
    updates = snapshot.get("updates")
    if not isinstance(payload, Mapping) or set(payload) != {
        "posterior_vectors",
        "application_bodies",
    }:
        raise ValueError("invalid Hybrid posterior-mirror payload fields")
    if not isinstance(messages, Mapping) or set(messages) != {
        "posterior_updates"
    }:
        raise ValueError("invalid Hybrid posterior-mirror message fields")
    if not isinstance(updates, list) or not updates:
        raise ValueError("Hybrid posterior-mirror updates must not be empty")

    vector_total = _positive_count(
        payload.get("posterior_vectors"), "posterior-vector byte total"
    )
    body_total = _positive_count(
        payload.get("application_bodies"), "application-body byte total"
    )
    message_total = _positive_count(
        messages.get("posterior_updates"), "posterior-update message total"
    )
    if message_total != len(updates):
        raise ValueError("posterior-update message total does not match updates")

    normalized_updates = []
    identities = []
    calculated_vector_total = 0
    calculated_body_total = 0
    for update in updates:
        if not isinstance(update, Mapping) or set(update) != {
            "stage",
            "replica",
            "vector_payload_bytes",
            "vector_sha256",
            "application_body_bytes",
            "application_body_sha256",
        }:
            raise ValueError("invalid Hybrid posterior-mirror update fields")
        choice = ReplicaChoice(
            _positive_count(update.get("stage"), "posterior update stage"),
            _positive_count(update.get("replica"), "posterior update replica"),
        )
        vector_bytes = _positive_count(
            update.get("vector_payload_bytes"), "posterior-vector bytes"
        )
        body_bytes = _positive_count(
            update.get("application_body_bytes"), "posterior application-body bytes"
        )
        if body_bytes < vector_bytes:
            raise ValueError("posterior application body is smaller than its vector")
        vector_digest = _require_digest(
            update.get("vector_sha256"), "posterior vector digest"
        )
        body_digest = _require_digest(
            update.get("application_body_sha256"), "posterior body digest"
        )
        identities.append(choice)
        normalized_updates.append(
            (choice, vector_bytes, vector_digest, body_bytes, body_digest)
        )
        calculated_vector_total += vector_bytes
        calculated_body_total += body_bytes
    if identities != sorted(set(identities)):
        raise ValueError(
            "posterior-mirror updates must be unique and canonically ordered"
        )
    if vector_total != calculated_vector_total or body_total != calculated_body_total:
        raise ValueError("posterior-mirror payload totals do not match updates")

    if expected_updated_choices is not None:
        expected_choices = sorted(set(expected_updated_choices))
        if identities != expected_choices:
            raise ValueError("posterior-mirror update identities are incomplete")
    if expected_beliefs is not None:
        if set(identities) - set(expected_beliefs):
            raise ValueError("posterior-mirror belief coverage is incomplete")
        for choice, vector_bytes, vector_digest, body_bytes, body_digest in (
            normalized_updates
        ):
            canonical = build_canonical_posterior_update(
                run_id=run_id,
                slot_id=slot_id,
                choice=choice,
                posterior=expected_beliefs[choice],
            )
            receipt = canonical.receipt
            if (
                vector_bytes != receipt.vector_payload_bytes
                or vector_digest != receipt.vector_sha256
                or body_bytes != receipt.application_body_bytes
                or body_digest != receipt.application_body_sha256
            ):
                raise ValueError(
                    "posterior-mirror measurement does not match canonical beliefs"
                )
    return snapshot


class HybridPosteriorMirrorHttpClient:
    """Persistent controller-side sender for non-authoritative copies."""

    def __init__(
        self,
        base_url: str,
        *,
        run_id: str,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.run_id = run_id
        self.timeout_seconds = float(timeout_seconds)
        HybridPosteriorUpdateDocument(
            run_id=run_id,
            slot_id=1,
            stage=1,
            replica=1,
            posterior=(0.25, 0.25, 0.25, 0.25),
        )
        if not self.base_url:
            raise ValueError("posterior-mirror base URL must not be empty")
        if not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("posterior-mirror timeout must be finite and positive")
        self._client = httpx.Client(
            timeout=self.timeout_seconds,
            transport=transport,
        )

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    def close(self) -> None:
        self._client.close()

    def mirror_slot(
        self,
        *,
        slot_id: int,
        beliefs_after: Mapping[ReplicaChoice, Sequence[float]],
        updated_choices: Sequence[ReplicaChoice],
    ) -> Mapping[str, object]:
        if self.is_closed:
            raise RuntimeError("Hybrid posterior-mirror HTTP client is closed")
        choices = sorted(set(updated_choices))
        if not choices:
            raise ValueError("posterior mirror requires at least one sampled replica")
        if set(choices) - set(beliefs_after):
            raise ValueError("posterior mirror lacks an updated replica belief")

        updates = []
        vector_total = 0
        body_total = 0
        for choice in choices:
            canonical = build_canonical_posterior_update(
                run_id=self.run_id,
                slot_id=slot_id,
                choice=choice,
                posterior=beliefs_after[choice],
            )
            response = self._client.post(
                f"{self.base_url}/posterior-update",
                content=canonical.application_body,
                headers={"content-type": "application/json"},
            )
            response.raise_for_status()
            receipt = HybridPosteriorReceipt.model_validate(response.json())
            expected_receipt = canonical.receipt
            if receipt != expected_receipt:
                raise RuntimeError(
                    "Hybrid posterior-mirror receipt does not match sent payload"
                )
            update = {
                "stage": choice.stage,
                "replica": choice.replica,
                "vector_payload_bytes": receipt.vector_payload_bytes,
                "vector_sha256": receipt.vector_sha256,
                "application_body_bytes": receipt.application_body_bytes,
                "application_body_sha256": receipt.application_body_sha256,
            }
            updates.append(update)
            vector_total += receipt.vector_payload_bytes
            body_total += receipt.application_body_bytes

        snapshot = {
            "schema": HYBRID_POSTERIOR_MIRROR_SCHEMA,
            "run_id": self.run_id,
            "slot_id": slot_id,
            "serialization": HYBRID_POSTERIOR_SERIALIZATION,
            "scope": HYBRID_POSTERIOR_SCOPE,
            "payload_bytes": {
                "posterior_vectors": vector_total,
                "application_bodies": body_total,
            },
            "messages": {"posterior_updates": len(updates)},
            "updates": updates,
        }
        return validate_hybrid_posterior_mirror_snapshot(
            snapshot,
            expected_slot_id=slot_id,
            expected_beliefs=beliefs_after,
            expected_updated_choices=choices,
        )


def create_posterior_mirror_app() -> FastAPI:
    """Create the validation/discard receiver with process-local deduplication."""

    application = FastAPI(title="IBG-Hybrid Posterior Mirror", version="0.1.0")
    application.state.received_updates = set()

    @application.get("/health")
    async def health() -> Mapping[str, str]:
        return {
            "status": "ok",
            "schema": HYBRID_POSTERIOR_MIRROR_SCHEMA,
        }

    @application.post(
        "/posterior-update",
        response_model=HybridPosteriorReceipt,
    )
    async def posterior_update(request: Request) -> HybridPosteriorReceipt:
        body = await request.body()
        try:
            document = HybridPosteriorUpdateDocument.model_validate_json(body)
            canonical = build_canonical_posterior_update(
                run_id=document.run_id,
                slot_id=document.slot_id,
                choice=ReplicaChoice(document.stage, document.replica),
                posterior=document.posterior,
            )
        except (ValueError, TypeError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
        if body != canonical.application_body:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="posterior update is not canonical compact JSON",
            )
        identity = (
            document.run_id,
            document.slot_id,
            document.stage,
            document.replica,
        )
        if identity in application.state.received_updates:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="duplicate posterior update",
            )
        application.state.received_updates.add(identity)
        return canonical.receipt

    return application


app = create_posterior_mirror_app()
