"""Rotas de liveness e readiness da Luna."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.integration.kura_client import IKuraClient
from src.web.dependencies import get_kura_client, get_settings
from src.web.schemas import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe — sempre retorna 200 se o processo está de pé."""
    return HealthResponse(status="ok")


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness probe — verifica Oracle e API Kura. Retorna 503 se algum falhar."""
    settings = get_settings()
    kura: IKuraClient = get_kura_client(request, settings)

    kura_ok = await kura.verificar_saude()
    oracle_ok = getattr(request.app.state, "pool", None) is not None

    payload = ReadyResponse(
        status="ok" if (kura_ok and oracle_ok) else "degraded",
        kura_api=kura_ok,
        oracle=oracle_ok,
    )
    status_code = 200 if (kura_ok and oracle_ok) else 503
    return JSONResponse(content=payload.model_dump(), status_code=status_code)
