"""FastAPI app. Run: uvicorn connectome_app.api:app --reload (from backend/)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from connectome_app.schemas import (
    CircuitData,
    CircuitSummary,
    LesionRequest,
    LesionResponse,
    NeuronDetail,
    PathRequest,
    PathResponse,
    ScreenRequest,
    ScreenStatus,
    SimulateRequest,
    SimulateResponse,
)
from connectome_app.service import Service

DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app(service: Service | None = None) -> FastAPI:
    """Build the app; tests pass their own Service."""
    if service is None:
        service = Service()
    app = FastAPI(title="Connectome Circuit Explorer", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["*"], allow_headers=["*"])
    app.state.service = service

    @app.exception_handler(FileNotFoundError)
    async def not_found(_: Request, error: FileNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(KeyError)
    async def unknown_key(_: Request, error: KeyError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error).strip("'\"")})

    @app.exception_handler(ValueError)
    async def bad_value(_: Request, error: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/circuits", response_model=list[CircuitSummary])
    def circuits() -> list[CircuitSummary]:
        return service.list_circuits()

    @app.get("/api/circuits/{name}", response_model=CircuitData)
    def circuit(name: str) -> CircuitData:
        return service.circuit_data(name)

    @app.get("/api/circuits/{name}/neurons/{body_id}", response_model=NeuronDetail)
    def neuron(name: str, body_id: int) -> NeuronDetail:
        return service.neuron_detail(name, body_id)

    @app.post("/api/simulate", response_model=SimulateResponse)
    def simulate(request: SimulateRequest) -> SimulateResponse:
        return service.simulate(request)

    @app.post("/api/paths", response_model=PathResponse)
    def paths(request: PathRequest) -> PathResponse:
        return service.paths(request)

    @app.post("/api/lesion", response_model=LesionResponse)
    def lesion(request: LesionRequest) -> LesionResponse:
        return service.lesion(request)

    @app.post("/api/screen", response_model=ScreenStatus)
    def screen(request: ScreenRequest) -> ScreenStatus:
        return service.start_screen(request)

    @app.get("/api/screen/{job_id}", response_model=ScreenStatus)
    def screen_status(job_id: str) -> ScreenStatus:
        return service.screen_status(job_id)

    @app.delete("/api/screen/{job_id}", response_model=ScreenStatus)
    def screen_cancel(job_id: str) -> ScreenStatus:
        return service.cancel_screen(job_id)

    @app.get("/api/circuits/{name}/types")
    def types(name: str) -> list[str]:
        circuit_obj = service.circuit(name)
        return sorted(circuit_obj.neurons["type"].unique().tolist())

    return app


app = create_app()
