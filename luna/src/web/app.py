"""FastAPI application factory da Luna v2.0."""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.config.settings import Settings
from src.integration.exceptions import KuraApiError, KuraTimeoutError
from src.web.routers import health as health_router
from src.web.routers import transcricao as transcricao_router
from src.web.routers import webhook_twilio as webhook_router
from src.web.routers import whatsapp as whatsapp_router

logger = logging.getLogger(__name__)


class _RequestIDMiddleware(BaseHTTPMiddleware):
    """Adiciona X-Request-ID a cada resposta para rastreabilidade."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(uuid.uuid4())
        return response


def create_app(settings: Settings) -> FastAPI:
    """Factory que cria e configura a aplicação FastAPI.

    Separa construção de runtime: permite sobrescrever settings em testes.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        transport = httpx.AsyncHTTPTransport(retries=2)
        http_client = httpx.AsyncClient(
            transport=transport,
            timeout=settings.KURA_API_TIMEOUT,
        )
        app.state.http_client = http_client
        app.state.settings = settings

        try:
            from src.db.connection import OracleConnectionPool

            pool = OracleConnectionPool(
                dsn=settings.ORACLE_DSN,
                user=settings.ORACLE_USER,
                password=settings.ORACLE_PASSWORD,
            )
            app.state.pool = pool
        except Exception:
            logger.warning("Oracle indisponível — pool não inicializado")
            app.state.pool = None

        yield

        await http_client.aclose()
        active_pool = getattr(app.state, "pool", None)
        if active_pool is not None:
            active_pool.close()

    app = FastAPI(
        title="Luna",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    # ── middleware ────────────────────────────────────────────────────────────
    app.add_middleware(_RequestIDMiddleware)

    # ── exception handlers ────────────────────────────────────────────────────
    @app.exception_handler(KuraApiError)
    async def _kura_api_error(request: Request, exc: KuraApiError) -> JSONResponse:
        logger.error("KuraApiError status=%d", exc.status_code)
        return JSONResponse({"error": "upstream service error"}, status_code=502)

    @app.exception_handler(KuraTimeoutError)
    async def _kura_timeout_error(request: Request, exc: KuraTimeoutError) -> JSONResponse:
        logger.error("KuraTimeoutError")
        return JSONResponse({"error": "upstream service timeout"}, status_code=504)

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(Exception)
    async def _generic_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception")
        return JSONResponse({"error": "internal server error"}, status_code=500)

    # ── routers ───────────────────────────────────────────────────────────────
    app.include_router(health_router.router)
    app.include_router(webhook_router.router)
    app.include_router(whatsapp_router.router)
    app.include_router(transcricao_router.router)

    return app


# Instância ASGI usada pelo uvicorn em produção (CMD do Dockerfile).
# Testes continuam chamando create_app(settings) diretamente.
app = create_app(Settings())
