"""Strict opt-in transport-impairment configuration for Hybrid replicas."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Mapping, Sequence


HYBRID_NETWORK_IMPAIRMENT_SCHEMA = "ibg-hybrid-netem-v1"
HYBRID_NETWORK_IMPAIRMENT_INTERFACE = "eth0"
HYBRID_NETWORK_IMPAIRMENT_DISTRIBUTION = "normal"
HYBRID_NETWORK_IMPAIRMENT_SCOPE = "replica-pod-egress"
HYBRID_NETWORK_IMPAIRMENT_ANNOTATION = (
    "ibg-hybrid.network-impairment"
)
HYBRID_NETEM_INIT_CONTAINER_NAME = "netem"


def _milliseconds(value: float) -> str:
    return f"{value:g}ms"


@dataclass(frozen=True)
class HybridNetworkImpairment:
    """One immutable observed transport configuration for a Hybrid run."""

    enabled: bool = False
    delay_ms: float = 0.0
    jitter_ms: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("Hybrid network impairment enabled must be boolean")
        for name, value in (
            ("delay_ms", self.delay_ms),
            ("jitter_ms", self.jitter_ms),
        ):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(
                    f"Hybrid network impairment {name} must be numeric"
                )
            if not math.isfinite(value) or value < 0:
                raise ValueError(
                    f"Hybrid network impairment {name} must be finite and "
                    "nonnegative"
                )
        if not self.enabled and (self.delay_ms != 0 or self.jitter_ms != 0):
            raise ValueError(
                "disabled Hybrid network impairment must have zero delay and "
                "jitter"
            )
        if self.enabled and self.delay_ms <= 0:
            raise ValueError(
                "enabled Hybrid network impairment requires positive delay_ms"
            )
        if self.jitter_ms > self.delay_ms:
            raise ValueError(
                "Hybrid network impairment jitter_ms cannot exceed delay_ms"
            )

    @classmethod
    def disabled(cls) -> "HybridNetworkImpairment":
        return cls()

    @classmethod
    def enabled_with(
        cls, *, delay_ms: float, jitter_ms: float
    ) -> "HybridNetworkImpairment":
        return cls(
            enabled=True,
            delay_ms=delay_ms,
            jitter_ms=jitter_ms,
        )

    @classmethod
    def from_dict(
        cls, value: Mapping[str, object]
    ) -> "HybridNetworkImpairment":
        if not isinstance(value, Mapping):
            raise ValueError("Hybrid network impairment metadata must be an object")
        expected = {
            "schema",
            "enabled",
            "interface",
            "delay_ms",
            "jitter_ms",
            "distribution",
            "scope",
        }
        if set(value) != expected:
            raise ValueError(
                "Hybrid network impairment metadata has unexpected fields"
            )
        if value.get("schema") != HYBRID_NETWORK_IMPAIRMENT_SCHEMA:
            raise ValueError(
                "Hybrid network impairment metadata has an unsupported schema"
            )
        if value.get("interface") != HYBRID_NETWORK_IMPAIRMENT_INTERFACE:
            raise ValueError(
                "Hybrid network impairment metadata has an unsupported interface"
            )
        if (
            value.get("distribution")
            != HYBRID_NETWORK_IMPAIRMENT_DISTRIBUTION
        ):
            raise ValueError(
                "Hybrid network impairment metadata has an unsupported distribution"
            )
        if value.get("scope") != HYBRID_NETWORK_IMPAIRMENT_SCOPE:
            raise ValueError(
                "Hybrid network impairment metadata has an unsupported scope"
            )
        return cls(
            enabled=value["enabled"],
            delay_ms=value["delay_ms"],
            jitter_ms=value["jitter_ms"],
        )

    @classmethod
    def from_json(cls, value: str) -> "HybridNetworkImpairment":
        if not isinstance(value, str):
            raise ValueError("Hybrid network impairment metadata must be JSON text")
        try:
            document = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(
                "Hybrid network impairment metadata must contain valid JSON"
            ) from error
        return cls.from_dict(document)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": HYBRID_NETWORK_IMPAIRMENT_SCHEMA,
            "enabled": self.enabled,
            "interface": HYBRID_NETWORK_IMPAIRMENT_INTERFACE,
            "delay_ms": float(self.delay_ms),
            "jitter_ms": float(self.jitter_ms),
            "distribution": HYBRID_NETWORK_IMPAIRMENT_DISTRIBUTION,
            "scope": HYBRID_NETWORK_IMPAIRMENT_SCOPE,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def tc_command(self) -> tuple[str, ...]:
        """Return Exact-compatible tc syntax, omitting jitter when it is zero."""

        if not self.enabled:
            raise ValueError("disabled Hybrid network impairment has no tc command")
        command = [
            "/usr/sbin/tc",
            "qdisc",
            "replace",
            "dev",
            HYBRID_NETWORK_IMPAIRMENT_INTERFACE,
            "root",
            "netem",
            "delay",
            _milliseconds(self.delay_ms),
        ]
        if self.jitter_ms > 0:
            command.extend(
                (
                    _milliseconds(self.jitter_ms),
                    "distribution",
                    HYBRID_NETWORK_IMPAIRMENT_DISTRIBUTION,
                )
            )
        return tuple(command)

    def init_container(self, *, image: str) -> dict[str, object]:
        if not isinstance(image, str) or not image:
            raise ValueError("Hybrid netem init image must be nonempty")
        command = self.tc_command()
        return {
            "name": HYBRID_NETEM_INIT_CONTAINER_NAME,
            "image": image,
            "imagePullPolicy": "Never",
            "command": [command[0]],
            "args": list(command[1:]),
            "securityContext": {
                "allowPrivilegeEscalation": False,
                "capabilities": {
                    "add": ["NET_ADMIN"],
                    "drop": ["ALL"],
                },
                "runAsNonRoot": False,
                "runAsUser": 0,
            },
            "resources": {
                "requests": {"cpu": "5m", "memory": "16Mi"},
                "limits": {"cpu": "100m", "memory": "32Mi"},
            },
        }


def validate_hybrid_network_impairment_events(
    events: Sequence[Mapping[str, object]],
    *,
    expected: HybridNetworkImpairment | None = None,
) -> HybridNetworkImpairment:
    """Require complete, identical provenance on every event in one trace."""

    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        raise ValueError("Hybrid impairment trace events must be a sequence")
    if not events:
        raise ValueError("Hybrid impairment trace has no events")
    resolved = None
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("Hybrid impairment trace event must be an object")
        if "network_impairment" not in event:
            raise ValueError(
                "Hybrid impairment trace event lacks network_impairment"
            )
        impairment = HybridNetworkImpairment.from_dict(
            event["network_impairment"]
        )
        if resolved is None:
            resolved = impairment
        elif impairment != resolved:
            raise ValueError(
                "Hybrid impairment trace mixes or drifts configurations"
            )
    if expected is not None:
        if not isinstance(expected, HybridNetworkImpairment):
            raise ValueError(
                "expected Hybrid network impairment has an invalid type"
            )
        if resolved != expected:
            raise ValueError(
                "Hybrid impairment trace does not match the requested configuration"
            )
    if resolved is None:  # pragma: no cover - guarded by the nonempty check.
        raise ValueError("Hybrid impairment trace has no resolved configuration")
    return resolved
