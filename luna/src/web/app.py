"""FastAPI application factory da Luna v2.0."""
from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.config.settings import Settings
from src.integration.exceptions import KuraApiError, KuraTimeoutError
from src.services.pendencia_confirmacao_store import PendenciaConfirmacaoStore
from src.web.routers import health as health_router
from src.web.routers import jobs as jobs_router
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

        # LU-04: lock compartilhado entre o tick do scheduler e o gatilho
        # manual (POST /jobs/lembrete-vacina/executar) — impede as duas
        # execuções ao mesmo tempo (duplicaria notificação/chamada Twilio).
        # Criado sempre, mesmo com o scheduler desligado: o gatilho manual
        # funciona independentemente da flag.
        app.state.lembrete_lock = asyncio.Lock()
        # REC-16 — lock PRÓPRIO do job de confirmação D-1 (ver docstring de
        # `executar_tick_confirmacao_d1` sobre por que não reaproveita
        # `lembrete_lock`).
        app.state.confirmacao_d1_lock = asyncio.Lock()
        # REC-16 (G0 item 11) — mapa em memória telefone -> pendência de
        # confirmação D-1, criado SEMPRE (independente da flag abaixo), mesmo
        # padrão de `lembrete_lock`: com a flag desligada o job nunca roda e o
        # mapa nunca é populado, então a interceptação em
        # `InboundMessageService` nunca encontra pendência nenhuma — não é
        # preciso um segundo `if` de flag no meio do fluxo de triagem.
        app.state.confirmacao_pendentes = PendenciaConfirmacaoStore()
        app.state.scheduler = None
        if settings.LUNA_SCHEDULER_ENABLED or settings.LEMBRETE_CONFIRMACAO_HABILITADO:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

            if settings.LUNA_SCHEDULER_ENABLED:
                from src.jobs.lembrete_vacina_job import executar_tick_lembrete_vacina

                scheduler.add_job(
                    executar_tick_lembrete_vacina,
                    "cron",
                    hour=settings.LUNA_SCHEDULER_HORA,
                    minute=0,
                    id="lembrete_vacina",
                    kwargs={"app": app},
                )
                logger.info(
                    "Scheduler de lembrete de vacina ligado — executa diariamente às %02d:00 BRT",
                    settings.LUNA_SCHEDULER_HORA,
                )

            if settings.LEMBRETE_CONFIRMACAO_HABILITADO:
                from src.jobs.confirmacao_d1_job import executar_tick_confirmacao_d1

                scheduler.add_job(
                    executar_tick_confirmacao_d1,
                    "cron",
                    hour=settings.LEMBRETE_CONFIRMACAO_HORA,
                    minute=0,
                    id="confirmacao_d1",
                    kwargs={"app": app},
                )
                logger.info(
                    "Scheduler de confirmação D-1 ligado — executa diariamente às %02d:00 BRT",
                    settings.LEMBRETE_CONFIRMACAO_HORA,
                )

            scheduler.start()
            app.state.scheduler = scheduler

        yield

        if app.state.scheduler is not None:
            app.state.scheduler.shutdown(wait=False)
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
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-API-Key"],
            expose_headers=["X-Request-ID"],
        )

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
    app.include_router(jobs_router.router)
    app.include_router(webhook_router.router)
    app.include_router(whatsapp_router.router)
    app.include_router(transcricao_router.router)

    return app


# Instância ASGI usada pelo uvicorn em produção (CMD do Dockerfile).
# Testes continuam chamando create_app(settings) diretamente.
app = create_app(Settings())
