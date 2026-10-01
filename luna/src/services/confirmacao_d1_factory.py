"""Fábrica de composição do ConfirmacaoD1Service (REC-16).

Espelha `lembrete_vacina_factory.py` (LU-04): extraída para ser reutilizada
pelo tick do scheduler (`confirmacao_d1_job.py`) sem duplicar a montagem.
Não cria/fecha o `httpx.AsyncClient` nem o `OracleConnectionPool` -- reusa o
que já existe no `lifespan` da app, mesmo padrão de `get_kura_client`/
`get_lembrete_service` em `web/dependencies.py`.

`TwilioGateway.__init__` valida a credencial no construtor (SDK da Twilio) --
sem `TWILIO_SID`/`TWILIO_TOKEN`/`TWILIO_FROM_NUMBER` válidos, levanta
`twilio.base.exceptions.TwilioException` (mesmo achado F4-1 documentado em
`lembrete_vacina_factory.py`). Quem chama esta fábrica num contexto que não
pode derrubar o processo precisa capturar essa exceção.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from src.db.repositories.log_erro_repo import LogErroRepository
from src.integration.kura_client import KuraClient
from src.messaging.twilio_client import TwilioGateway
from src.services.confirmacao_d1_service import ConfirmacaoD1Service
from src.services.pendencia_confirmacao_store import PendenciaConfirmacaoStore

if TYPE_CHECKING:
    from src.config.settings import Settings
    from src.db.connection import OracleConnectionPool


def criar_confirmacao_d1_service(
    settings: "Settings",
    pool: "OracleConnectionPool",
    http_client: httpx.AsyncClient,
    store: PendenciaConfirmacaoStore,
) -> ConfirmacaoD1Service:
    """Compõe o ConfirmacaoD1Service com os repositórios, o KuraClient e o
    gateway Twilio.

    Pode levantar `twilio.base.exceptions.TwilioException` -- ver docstring do
    módulo.
    """
    log_repo = LogErroRepository(pool)
    kura_client = KuraClient(
        base_url=settings.KURA_API_BASE_URL,
        api_key=settings.KURA_API_KEY,
        timeout=settings.KURA_API_TIMEOUT,
        http_client=http_client,
    )
    twilio_gateway = TwilioGateway(
        account_sid=settings.TWILIO_SID,
        auth_token=settings.TWILIO_TOKEN,
        from_number=settings.TWILIO_FROM_NUMBER,
    )
    return ConfirmacaoD1Service(kura_client, twilio_gateway, store, log_repo)
