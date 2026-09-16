"""Gatilho manual de jobs administrativos (LU-04).

Endpoint: POST /jobs/lembrete-vacina/executar
Auth: header X-API-Key validado contra LUNA_INBOUND_API_KEY (mesma dependência
de /whatsapp/enviar e /transcricao).
Concorrência: compartilha o `asyncio.Lock` (`app.state.lembrete_lock`) com o
tick do scheduler do `lifespan` — uma execução em andamento faz a outra
devolver 409 em vez de rodar em paralelo (duplicaria notificação/chamada
Twilio, achado F4-2).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.jobs.lembrete_vacina_job import LembreteVacinaJob
from src.services.notification_service import LembreteVacinaService
from src.web.dependencies import get_lembrete_service, validar_api_key
from src.web.schemas import ResumoExecucaoResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Jobs"])


@router.post(
    "/jobs/lembrete-vacina/executar",
    response_model=ResumoExecucaoResponse,
    summary="Executa um ciclo de lembretes de vacina imediatamente",
    description=(
        "Gatilho manual para demonstração/operação — dispara o mesmo ciclo que o "
        "scheduler diário executaria. Requer header `X-API-Key` válido. "
        "Devolve 409 se já houver uma execução em andamento (scheduler ou outro gatilho)."
    ),
)
async def executar_lembrete_vacina(
    request: Request,
    _: Annotated[None, Depends(validar_api_key)],
    service: Annotated[LembreteVacinaService, Depends(get_lembrete_service)],
) -> ResumoExecucaoResponse:
    lock: asyncio.Lock = request.app.state.lembrete_lock
    if lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Execução de lembretes já em andamento",
        )

    async with lock:
        job = LembreteVacinaJob(service)
        resumo = await asyncio.to_thread(job.executar)

    return ResumoExecucaoResponse(
        total=resumo.total,
        enviadas=resumo.enviadas,
        falhas=resumo.falhas,
        ja_enviadas=resumo.ja_enviadas,
        sem_consentimento=resumo.sem_consentimento,
    )
