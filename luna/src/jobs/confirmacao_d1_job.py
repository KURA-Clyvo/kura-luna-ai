"""ConfirmacaoD1Job — wrapper síncrono de log; tick assíncrono do scheduler (REC-16).

Espelha `lembrete_vacina_job.py` (LU-04): o agendamento real vive no `lifespan`
do FastAPI, via `AsyncIOScheduler`, só quando `LEMBRETE_CONFIRMACAO_HABILITADO=
true` (ver `web/app.py`). `executar_tick_confirmacao_d1` abaixo é a função que
o cron chama a cada tick.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from twilio.base.exceptions import TwilioException

from src.services.confirmacao_d1_factory import criar_confirmacao_d1_service
from src.services.confirmacao_d1_service import ConfirmacaoD1Service, ResumoExecucaoConfirmacaoD1

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


class ConfirmacaoD1Job:
    """Wrapper assíncrono de log em torno de `ConfirmacaoD1Service.executar`."""

    def __init__(self, service: ConfirmacaoD1Service) -> None:
        self._service = service

    async def executar(self) -> ResumoExecucaoConfirmacaoD1:
        """Executa um ciclo de lembretes de confirmação D-1 e loga o resumo."""
        logger.info("ConfirmacaoD1Job: iniciando execução")
        resumo = await self._service.executar()
        logger.info(
            "ConfirmacaoD1Job concluído — total=%d enviadas=%d falhas=%d ja_processadas=%d",
            resumo.total,
            resumo.enviadas,
            resumo.falhas,
            resumo.ja_processadas,
        )
        return resumo


async def executar_tick_confirmacao_d1(app: FastAPI) -> None:
    """Tick do `AsyncIOScheduler` (REC-16) — chamado pelo cron diário do `lifespan`.

    Nunca deixa uma falha derrubar o scheduler nem o processo: cada
    pré-condição ausente (lock ocupado, Oracle indisponível, credencial Twilio
    ausente/inválida) é logada e o tick simplesmente retorna, para tentar de
    novo no próximo dia. Usa um lock PRÓPRIO (`confirmacao_d1_lock`), separado
    do `lembrete_lock` da vacina — são jobs independentes, sem recurso Twilio
    nem Oracle compartilhado de forma exclusiva (o pool Oracle suporta conexões
    concorrentes; a Twilio não tem limite de 1 chamada por vez), então não há
    necessidade real de serializar os dois jobs entre si.
    """
    lock: asyncio.Lock = app.state.confirmacao_d1_lock
    if lock.locked():
        logger.warning(
            "confirmacao_d1.scheduler tick ignorado — execução já em andamento"
        )
        return

    pool = getattr(app.state, "pool", None)
    if pool is None:
        logger.warning("confirmacao_d1.scheduler tick ignorado — Oracle indisponível")
        return

    settings = app.state.settings
    http_client = app.state.http_client
    store = app.state.confirmacao_pendentes
    try:
        service = criar_confirmacao_d1_service(settings, pool, http_client, store)
    except TwilioException:
        logger.warning(
            "confirmacao_d1.scheduler tick ignorado — credencial Twilio ausente/inválida"
        )
        return

    async with lock:
        try:
            job = ConfirmacaoD1Job(service)
            await job.executar()
        except Exception:
            logger.exception("confirmacao_d1.scheduler tick falhou inesperadamente")
