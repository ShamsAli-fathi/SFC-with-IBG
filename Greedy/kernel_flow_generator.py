"""Import-safe Greedy HTTP wrapper for the persistent route executor."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from IBG.datapath import KERNEL_DATAPATH_MODE

from .kernel_route_contracts import (
    GREEDY_KERNEL_ROUTE_CONTRACT_VERSION,
    GreedyKernelRunSlotRequest,
    GreedyKernelRunSlotResponse,
)
from .kernel_route_execution import (
    GreedyKernelRouteExecutionError,
    GreedyKernelRouteExecutor,
)


GREEDY_KERNEL_FLOW_GENERATOR_SERVICE_VERSION = (
    "greedy-kernel-flow-generator-service-v1"
)


class GreedyKernelGeneratorHealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    datapath_mode: str
    route_contract_version: str
    service_version: str


def create_app(executor: GreedyKernelRouteExecutor | None = None) -> FastAPI:
    runtime = executor or GreedyKernelRouteExecutor()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        del application
        start = getattr(runtime, "start", None)
        close = getattr(runtime, "aclose", None)
        try:
            if callable(start):
                await start()
            yield
        finally:
            if callable(close):
                await close()

    application = FastAPI(
        title="Greedy Flow Generator",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.executor = runtime

    @application.get("/health", response_model=GreedyKernelGeneratorHealthResponse)
    async def health() -> GreedyKernelGeneratorHealthResponse:
        return GreedyKernelGeneratorHealthResponse(
            status="ok",
            datapath_mode=KERNEL_DATAPATH_MODE,
            route_contract_version=GREEDY_KERNEL_ROUTE_CONTRACT_VERSION,
            service_version=GREEDY_KERNEL_FLOW_GENERATOR_SERVICE_VERSION,
        )

    @application.post("/run-slot", response_model=GreedyKernelRunSlotResponse)
    async def run_slot(
        request: GreedyKernelRunSlotRequest,
    ) -> GreedyKernelRunSlotResponse:
        try:
            return await runtime.run_slot(request)
        except GreedyKernelRouteExecutionError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    return application


app = create_app()
