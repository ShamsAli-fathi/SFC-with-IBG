import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import os
import re
import time

from fastapi import FastAPI
import numpy as np
from pydantic import BaseModel, Field

from IBG.latency_model import (
    estimate_state,
    latency_likelihood,
    require_state_parameters,
    sample_latency_ms,
)
from testbed.profiles import load_profiles, require_profile


LatencySource = Callable[[int], float]


@dataclass(frozen=True)
class ReplicaConfig:
    stage: int = 1
    replica_id: int = 1
    pod_name: str = "stage-1-0"
    state: int = 4
    capacity: int = 2000
    base_delay_ms: float = 5.0
    congestion_delay_ms: float = 2.0
    observation_seed: int | None = None

    def __post_init__(self):
        if self.stage < 1:
            raise ValueError("stage must be at least 1")
        if self.replica_id < 1:
            raise ValueError("replica_id must be at least 1")
        if not self.pod_name:
            raise ValueError("pod_name must not be empty")
        if self.state not in (1, 2, 3, 4):
            raise ValueError("state must be one of 1, 2, 3, or 4")
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if self.base_delay_ms < 0:
            raise ValueError("base_delay_ms must not be negative")
        if self.congestion_delay_ms < 0:
            raise ValueError("congestion_delay_ms must not be negative")
        if self.observation_seed is not None and self.observation_seed < 0:
            raise ValueError("observation_seed must not be negative")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None):
        values = os.environ if environ is None else environ
        stage = int(values.get("STAGE", "1"))
        pod_name = values.get("POD_NAME", f"stage-{stage}-0")
        replica_value = values.get("REPLICA_ID")
        if replica_value is None:
            ordinal = re.search(r"-(\d+)$", pod_name)
            if ordinal is None:
                raise ValueError("POD_NAME must end in a StatefulSet ordinal")
            replica_id = int(ordinal.group(1)) + 1
        else:
            replica_id = int(replica_value)

        profile = None
        profile_path = values.get("REPLICA_PROFILES_PATH")
        if profile_path:
            profile = require_profile(load_profiles(profile_path), stage, replica_id)

        def configured(name, profile_name, default):
            if name in values:
                return values[name]
            if profile is not None:
                return getattr(profile, profile_name)
            return default

        observation_seed = configured(
            "OBSERVATION_SEED",
            "observation_seed",
            None,
        )

        return cls(
            stage=stage,
            replica_id=replica_id,
            pod_name=pod_name,
            state=int(configured("STATE", "state", 4)),
            capacity=int(configured("CAPACITY", "capacity", 2000)),
            base_delay_ms=float(
                configured("BASE_DELAY_MS", "base_delay_ms", 5)
            ),
            congestion_delay_ms=float(
                configured(
                    "CONGESTION_DELAY_MS",
                    "congestion_delay_ms",
                    2,
                )
            ),
            observation_seed=(
                None if observation_seed is None else int(observation_seed)
            ),
        )


class ProcessRequest(BaseModel):
    slot_id: int = Field(ge=1)
    flow_id: int = Field(ge=1)
    assigned_load: int | None = Field(default=None, ge=1)
    legacy_congestion: int | None = Field(default=None, ge=1)


class HealthResponse(BaseModel):
    status: str
    stage: int
    replica_id: int
    pod_name: str
    current_concurrency: int


class ProcessResponse(BaseModel):
    slot_id: int
    flow_id: int
    stage: int
    replica_id: int
    pod_name: str
    concurrency: int
    assigned_load: int
    modeled_processing_latency_ms: float
    legacy_congestion: int
    processing_latency_ms: float
    signal_latency_ms: float
    state_estimate: int
    state_likelihood: tuple[float, float, float, float]
    legacy_signal: int
    legacy_likelihood: tuple[float, float, float, float]


class LatencyObservationSource:
    """Sample the Phase 1 state/load-conditioned processing delay."""

    def __init__(self, config: ReplicaConfig):
        self.state = config.state

    def __call__(self, assigned_load: int) -> float:
        return sample_latency_ms(
            assigned_load,
            require_state_parameters(self.state),
        )


class SeededLatencyObservationSource(LatencyObservationSource):
    """Generate request-stable state/load-conditioned processing delay."""

    def __init__(self, config: ReplicaConfig):
        if config.observation_seed is None:
            raise ValueError("observation_seed is required for seeded observations")
        super().__init__(config)
        self.seed = config.observation_seed

    def __call__(
        self,
        assigned_load: int,
        slot_id: int,
        flow_id: int,
    ) -> float:
        generator = np.random.default_rng(
            np.random.SeedSequence(
                [self.seed, slot_id, flow_id, assigned_load]
            )
        )
        return sample_latency_ms(
            assigned_load,
            require_state_parameters(self.state),
            generator,
        )


# Compatibility names for callers migrating from the completed baseline.
LegacyObservationSource = LatencyObservationSource
SeededLegacyObservationSource = SeededLatencyObservationSource


class ReplicaRuntime:
    def __init__(
        self,
        config: ReplicaConfig,
        observation_source: LatencySource | None = None,
    ):
        self.config = config
        if observation_source is not None:
            self.observation_source = observation_source
            self._request_seeded_observation = False
        elif config.observation_seed is not None:
            self.observation_source = SeededLatencyObservationSource(config)
            self._request_seeded_observation = True
        else:
            self.observation_source = LatencyObservationSource(config)
            self._request_seeded_observation = False
        self._lock = asyncio.Lock()
        self._active_requests = 0
        self._peak_concurrency = 0

    @property
    def active_requests(self):
        return self._active_requests

    @property
    def peak_concurrency(self):
        return self._peak_concurrency

    async def health(self):
        async with self._lock:
            current_concurrency = self._active_requests
        return HealthResponse(
            status="ok",
            stage=self.config.stage,
            replica_id=self.config.replica_id,
            pod_name=self.config.pod_name,
            current_concurrency=current_concurrency,
        )

    async def process(self, request: ProcessRequest):
        started_at = time.perf_counter()
        async with self._lock:
            self._active_requests += 1
            concurrency = self._active_requests
            self._peak_concurrency = max(self._peak_concurrency, concurrency)

        try:
            assigned_load = (
                request.assigned_load
                or request.legacy_congestion
                or concurrency
            )
            if self._request_seeded_observation:
                modeled_delay_ms = self.observation_source(
                    assigned_load,
                    request.slot_id,
                    request.flow_id,
                )
            else:
                modeled_delay_ms = self.observation_source(assigned_load)
            await asyncio.sleep(modeled_delay_ms / 1000)
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            likelihood = latency_likelihood(elapsed_ms, assigned_load)
            state_estimate = estimate_state(likelihood)
            return ProcessResponse(
                slot_id=request.slot_id,
                flow_id=request.flow_id,
                stage=self.config.stage,
                replica_id=self.config.replica_id,
                pod_name=self.config.pod_name,
                concurrency=concurrency,
                assigned_load=assigned_load,
                modeled_processing_latency_ms=modeled_delay_ms,
                legacy_congestion=assigned_load,
                processing_latency_ms=elapsed_ms,
                signal_latency_ms=elapsed_ms,
                state_estimate=state_estimate,
                state_likelihood=likelihood,
                legacy_signal=state_estimate,
                legacy_likelihood=likelihood,
            )
        finally:
            async with self._lock:
                self._active_requests -= 1


def create_app(
    config: ReplicaConfig | None = None,
    observation_source: LatencySource | None = None,
):
    runtime = ReplicaRuntime(
        config or ReplicaConfig.from_env(),
        observation_source=observation_source,
    )
    application = FastAPI(title="IBG HTTP Replica", version="0.1.0")
    application.state.runtime = runtime

    @application.get("/health", response_model=HealthResponse)
    async def health():
        return await runtime.health()

    @application.post("/process", response_model=ProcessResponse)
    async def process(request: ProcessRequest):
        return await runtime.process(request)

    return application


app = create_app()


def main():
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
    )


if __name__ == "__main__":
    main()
