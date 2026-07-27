from dataclasses import dataclass
import json
import math


NETWORK_IMPAIRMENT_SCHEMA = "netem_v1"
NETWORK_IMPAIRMENT_INTERFACE = "eth0"
NETWORK_IMPAIRMENT_DISTRIBUTION = "normal"
NETWORK_IMPAIRMENT_SCOPE = "replica-pod-egress"


def _milliseconds(value):
    return f"{value:g}ms"


@dataclass(frozen=True)
class NetworkImpairment:
    enabled: bool = False
    delay_ms: float = 0.0
    jitter_ms: float = 0.0

    def __post_init__(self):
        if not isinstance(self.enabled, bool):
            raise ValueError("network impairment enabled value must be boolean")
        for name, value in (
            ("delay_ms", self.delay_ms),
            ("jitter_ms", self.jitter_ms),
        ):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"network impairment {name} must be numeric")
            if not math.isfinite(value) or value < 0:
                raise ValueError(
                    f"network impairment {name} must be finite and non-negative"
                )
        if not self.enabled and (self.delay_ms != 0 or self.jitter_ms != 0):
            raise ValueError(
                "disabled network impairment must have zero delay and jitter"
            )
        if self.enabled and self.delay_ms <= 0:
            raise ValueError(
                "enabled network impairment requires positive delay_ms"
            )
        if self.jitter_ms > self.delay_ms:
            raise ValueError(
                "network impairment jitter_ms cannot exceed delay_ms"
            )

    @classmethod
    def disabled(cls):
        return cls()

    @classmethod
    def enabled_with(cls, *, delay_ms, jitter_ms):
        return cls(
            enabled=True,
            delay_ms=float(delay_ms),
            jitter_ms=float(jitter_ms),
        )

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError("network impairment metadata must be an object")
        if value.get("schema") != NETWORK_IMPAIRMENT_SCHEMA:
            raise ValueError(
                "network impairment metadata has an unsupported schema"
            )
        expected = {
            "schema",
            "enabled",
            "delay_ms",
            "jitter_ms",
            "distribution",
            "interface",
            "scope",
        }
        if set(value) != expected:
            raise ValueError(
                "network impairment metadata has unexpected fields"
            )
        if value["distribution"] != NETWORK_IMPAIRMENT_DISTRIBUTION:
            raise ValueError(
                "network impairment metadata has an unsupported distribution"
            )
        if value["interface"] != NETWORK_IMPAIRMENT_INTERFACE:
            raise ValueError(
                "network impairment metadata has an unsupported interface"
            )
        if value["scope"] != NETWORK_IMPAIRMENT_SCOPE:
            raise ValueError(
                "network impairment metadata has an unsupported scope"
            )
        return cls(
            enabled=value["enabled"],
            delay_ms=value["delay_ms"],
            jitter_ms=value["jitter_ms"],
        )

    @classmethod
    def from_json(cls, value):
        try:
            document = json.loads(value)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError(
                "network impairment metadata must contain valid JSON"
            ) from error
        return cls.from_dict(document)

    def to_dict(self):
        return {
            "schema": NETWORK_IMPAIRMENT_SCHEMA,
            "enabled": self.enabled,
            "delay_ms": float(self.delay_ms),
            "jitter_ms": float(self.jitter_ms),
            "distribution": NETWORK_IMPAIRMENT_DISTRIBUTION,
            "interface": NETWORK_IMPAIRMENT_INTERFACE,
            "scope": NETWORK_IMPAIRMENT_SCOPE,
        }

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def tc_command(self):
        if not self.enabled:
            raise ValueError(
                "disabled network impairment has no tc command"
            )
        command = [
            "/usr/sbin/tc",
            "qdisc",
            "replace",
            "dev",
            NETWORK_IMPAIRMENT_INTERFACE,
            "root",
            "netem",
            "delay",
            _milliseconds(self.delay_ms),
        ]
        if self.jitter_ms > 0:
            command.extend(
                [
                    _milliseconds(self.jitter_ms),
                    "distribution",
                    NETWORK_IMPAIRMENT_DISTRIBUTION,
                ]
            )
        return command
