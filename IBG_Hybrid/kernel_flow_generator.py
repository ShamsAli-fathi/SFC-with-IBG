"""Import-safe Hybrid-only HTTP wrapper for the Phase 1 route executor."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from IBG.datapath import KERNEL_DATAPATH_MODE

from .kernel_route_contracts import (
    HYBRID_KERNEL_ROUTE_CONTRACT_VERSION,
    HybridKernelRunSlotRequest,
    HybridKernelRunSlotResponse,
)
from .kernel_route_execution import (
    HybridKernelRouteExecutionError,
    HybridKernelRouteExecutor,
)


HYBRID_KERNEL_FLOW_GENERATOR_SERVICE_VERSION = (
    "ibg-hybrid-kernel-flow-generator-service-v1"
)


class HybridKernelGeneratorHealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    datapath_mode: str
    route_contract_version: str
    service_version: str


def create_app(executor: HybridKernelRouteExecutor | None = None) -> FastAPI:
    runtime = executor or HybridKernelRouteExecutor()
    application = FastAPI(title="IBG-Hybrid Flow Generator", version="0.1.0")
    application.state.executor = runtime

    @application.get(
        "/health",
        response_model=HybridKernelGeneratorHealthResponse,
    )
    async def health() -> HybridKernelGeneratorHealthResponse:
        return HybridKernelGeneratorHealthResponse(
            status="ok",
            datapath_mode=KERNEL_DATAPATH_MODE,
            route_contract_version=HYBRID_KERNEL_ROUTE_CONTRACT_VERSION,
            service_version=HYBRID_KERNEL_FLOW_GENERATOR_SERVICE_VERSION,
        )

    @application.post(
        "/run-slot",
        response_model=HybridKernelRunSlotResponse,
    )
    async def run_slot(
        request: HybridKernelRunSlotRequest,
    ) -> HybridKernelRunSlotResponse:
        try:
            return await runtime.run_slot(request)
        except HybridKernelRouteExecutionError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    return application


app = create_app()

