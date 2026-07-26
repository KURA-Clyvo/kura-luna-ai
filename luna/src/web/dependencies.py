"""Providers de dependência para injeção via FastAPI Depends."""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated, TYPE_CHECKING

import httpx
from fastapi import Depends, Request

from src.ai.triage_engine import TriageEngine
from src.config.settings import Settings
from src.db.repositories.log_erro_repo import LogErroRepository
from src.integration.kura_client import KuraClient
from src.messaging.twilio_client import TwilioGateway
from src.services.transcricao_service import WhisperGateway

if TYPE_CHECKING:
    from src.db.connection import OracleConnectionPool
    from src.services.inbound_message_service import InboundMessageService


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton de Settings lido do .env."""
    return Settings()


@lru_cache(maxsize=1)
def get_triage_engine() -> TriageEngine:
    """Singleton do TriageEngine (stateless)."""
    return TriageEngine()


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Retorna o AsyncClient criado no lifespan da app."""
    return request.app.state.http_client  # type: ignore[no-any-return]


def get_pool(request: Request) -> OracleConnectionPool | None:
    """Retorna o pool Oracle criado no lifespan (pode ser None se Oracle indisponível)."""
    return getattr(request.app.state, "pool", None)  # type: ignore[no-any-return]


def get_kura_client(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> KuraClient:
    """Constrói KuraClient com client HTTP do lifespan."""
    return KuraClient(
        base_url=settings.KURA_API_BASE_URL,
        api_key=settings.KURA_API_KEY,
        timeout=settings.KURA_API_TIMEOUT,
        http_client=get_http_client(request),
    )


def get_twilio_gateway(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TwilioGateway:
    """Constrói TwilioGateway com credenciais do Settings."""
    return TwilioGateway(
        account_sid=settings.TWILIO_SID,
        auth_token=settings.TWILIO_TOKEN,
        from_number=settings.TWILIO_FROM_NUMBER,
    )


def get_whisper_gateway(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> WhisperGateway:
    """Constrói WhisperGateway com a API key do Settings e o AsyncClient do lifespan."""
    return WhisperGateway(
        api_key=settings.OPENAI_API_KEY,
        http_client=get_http_client(request),
    )


def get_log_repo(request: Request) -> LogErroRepository:
    """Constrói LogErroRepository com pool do lifespan (fail-safe se pool for None)."""
    pool = get_pool(request)
    return LogErroRepository(pool)  # type: ignore[arg-type]


def get_inbound_service(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> InboundMessageService:
    """Compõe InboundMessageService com todas as dependências."""
    from src.services.inbound_message_service import InboundMessageService

    return InboundMessageService(
        kura_client=get_kura_client(request, settings),
        triage_engine=get_triage_engine(),
        twilio_gateway=get_twilio_gateway(settings),
        log_repo=get_log_repo(request),
    )
