"""LembreteVacinaJob — wrapper síncrono de log; tick assíncrono do scheduler (LU-04).

Até o LU-04, ``iniciar_scheduler`` (via ``apscheduler.schedulers.blocking.
BlockingScheduler``) não tinha nenhum chamador em produção — confirmado por
`grep` em `src/`: a CLI (`cli/main.py::run_job`) sempre chamou
`service.executar()` diretamente, e nenhum outro ponto do código instanciava
um `BlockingScheduler`. Um segundo processo bloqueante dentro do mesmo
container que já roda uvicorn (ver `docs/IA_DEFINICAO.md` §9.4: "O container
executa apenas o servidor FastAPI") também não faria sentido operacional.
Por isso o método foi **removido** em vez de mantido com docstring
"verdadeira" apontando para um caminho morto — a decisão que o brief permitia
("removido, se nada o usar").

O agendamento real passou a viver no ``lifespan`` do FastAPI, via
``AsyncIOScheduler`` (``apscheduler.schedulers.asyncio``), só quando
``LUNA_SCHEDULER_ENABLED=true`` (ver `web/app.py`). ``executar_tick_lembrete_
vacina`` abaixo é a função que o `cron` chama a cada tick.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from twilio.base.exceptions import TwilioException

from src.services.lembrete_vacina_factory import criar_lembrete_service
from src.services.notification_service import LembreteVacinaService, ResumoExecucao

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


class LembreteVacinaJob:
    """Wrapper síncrono de log em torno de ``LembreteVacinaService.executar``."""

    def __init__(self, service: LembreteVacinaService) -> None:
        self._service = service

    def executar(self) -> ResumoExecucao:
        """Executa um ciclo de lembretes e loga o resumo. Chamado pelo tick do scheduler."""
        logger.info("LembreteVacinaJob: iniciando execução")
        resumo = self._service.executar()
        logger.info(
            "LembreteVacinaJob concluído — total=%d enviadas=%d falhas=%d"
            " ja_enviadas=%d sem_consentimento=%d",
            resumo.total,
            resumo.enviadas,
            resumo.falhas,
            resumo.ja_enviadas,
            resumo.sem_consentimento,
        )
        return resumo


async def executar_tick_lembrete_vacina(app: "FastAPI") -> None:
    """Tick do ``AsyncIOScheduler`` (LU-04) — chamado pelo cron diário do `lifespan`.

    Nunca deixa uma falha derrubar o scheduler nem o processo: cada
    pré-condição ausente (lock ocupado, Oracle indisponível, credencial
    Twilio ausente/inválida — achado F4-1) é logada e o tick simplesmente
    retorna, para tentar de novo no próximo dia. Compartilha o mesmo
    ``asyncio.Lock`` do gatilho manual (`POST /jobs/lembrete-vacina/executar`)
    para nunca rodar os dois ao mesmo tempo.
    """
    lock: asyncio.Lock = app.state.lembrete_lock
    if lock.locked():
        logger.warning(
            "lembrete_vacina.scheduler tick ignorado — execução já em andamento"
            " (gatilho manual ou tick anterior)"
        )
        return

    pool = getattr(app.state, "pool", None)
    if pool is None:
        logger.warning("lembrete_vacina.scheduler tick ignorado — Oracle indisponível")
        return

    settings = app.state.settings
    try:
        service = criar_lembrete_service(settings, pool)
    except TwilioException:
        logger.warning(
            "lembrete_vacina.scheduler tick ignorado — credencial Twilio ausente/inválida"
        )
        return

    async with lock:
        try:
            job = LembreteVacinaJob(service)
            await asyncio.to_thread(job.executar)
        except Exception:
            logger.exception("lembrete_vacina.scheduler tick falhou inesperadamente")
