"""Rotas de liveness e readiness da Luna."""
import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from src.integration.kura_client import IKuraClient
from src.web.dependencies import get_kura_client
from src.web.schemas import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe — sempre retorna 200 se o processo está de pé."""
    return HealthResponse(status="ok")


@router.get("/ready")
async def ready(
    request: Request,
    kura: Annotated[IKuraClient, Depends(get_kura_client)],
) -> JSONResponse:
    """Readiness probe — verifica Oracle e API Kura. Retorna 503 se algum falhar."""
    kura_ok = await kura.verificar_saude()

    pool = getattr(request.app.state, "pool", None)
    # pool não-None só confirma que o objeto foi construído — oracledb (thin
    # mode) não valida conectividade na criação. ping() adquire uma conexão
    # de verdade; roda em thread pois é uma chamada síncrona/bloqueante.
    oracle_ok = await asyncio.to_thread(pool.ping) if pool is not None else False

    payload = ReadyResponse(
        status="ok" if (kura_ok and oracle_ok) else "degraded",
        kura_api=kura_ok,
        oracle=oracle_ok,
    )
    status_code = 200 if (kura_ok and oracle_ok) else 503
    return JSONResponse(content=payload.model_dump(), status_code=status_code)
