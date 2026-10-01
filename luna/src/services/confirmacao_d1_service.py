"""Serviço de lembrete de confirmação D-1 (REC-16) — orquestra `.NET` + Twilio
ponta-a-ponta, espelhando `LembreteVacinaService` (LU-04)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.db.repositories.log_erro_repo import LogErroRepository
from src.integration.dtos import ConfirmacaoPendenteItemDTO
from src.integration.exceptions import KuraApiError, KuraTimeoutError
from src.integration.kura_client import IKuraClient
from src.messaging.templates import confirmacao_d1
from src.messaging.twilio_client import ITwilioGateway, MessagingError, StatusMensagem
from src.messaging.twilio_inbound import chave_telefone
from src.services.pendencia_confirmacao_store import (
    PendenciaConfirmacao,
    PendenciaConfirmacaoStore,
)

logger = logging.getLogger(__name__)

# A-5: fuso de São Paulo é a referência de "hoje"/"amanhã" para esta tela, mesma
# regra que o .NET aplica a DT_AGENDAMENTO via IRelogioClinica.
_FUSO_CLINICA = ZoneInfo("America/Sao_Paulo")

# G0 item 10 — polling síncrono logo após o envio: até 4 consultas de status,
# com intervalo crescente. Decisão registrada no diário (rec-16-report.md):
# webhook de StatusCallback foi descartado por escopo (exigiria endpoint novo +
# correlação assíncrona fora do tick do job).
_INTERVALOS_CONSULTA_STATUS = (0.5, 1.0, 1.0, 1.0)
_STATUS_SUCESSO = frozenset({"sent", "delivered", "read"})
_STATUS_FALHA = frozenset({"failed", "undelivered"})

# G0 item 11: validade da pendência registrada após um envio confirmado — cobre
# o resto do dia do envio mais folga, sem acumular pendência indefinidamente se
# o tutor nunca responder.
_VALIDADE_PENDENCIA_HORAS = 36


class _StatusNaoConfirmadoError(Exception):
    """Interno: status do Twilio não confirmou entrega (falha real ou
    inconclusivo após as tentativas) — contado como falha, não propagado."""


@dataclass(frozen=True, slots=True)
class ResumoExecucaoConfirmacaoD1:
    """Resultado do ciclo de envio de lembretes de confirmação D-1."""

    total: int
    enviadas: int
    falhas: int
    ja_processadas: int


def _data_alvo(agora: datetime | None = None) -> date:
    """Data de amanhã, hora local de São Paulo (A-5) — o lembrete D-1 é enviado
    no dia anterior ao agendamento."""
    referencia = agora or datetime.now(tz=_FUSO_CLINICA)
    if referencia.tzinfo is None:
        referencia = referencia.replace(tzinfo=_FUSO_CLINICA)
    return (referencia.astimezone(_FUSO_CLINICA) + timedelta(days=1)).date()


class ConfirmacaoD1Service:
    """Orquestra o ciclo completo de lembrete de confirmação D-1 via WhatsApp."""

    def __init__(
        self,
        kura_client: IKuraClient,
        twilio_gateway: ITwilioGateway,
        store: PendenciaConfirmacaoStore,
        log_repo: LogErroRepository,
    ) -> None:
        self._kura = kura_client
        self._twilio = twilio_gateway
        self._store = store
        self._log_repo = log_repo

    async def executar(self) -> ResumoExecucaoConfirmacaoD1:
        """Executa o ciclo de lembretes. Falha por item não derruba o lote."""
        data_alvo = _data_alvo()
        candidatos = await self._kura.buscar_confirmacao_pendente(data_alvo)

        enviadas = 0
        falhas = 0
        ja_processadas = 0

        for candidato in candidatos:
            if self._store.ja_processado_hoje(candidato.id_agendamento):
                # Defesa em profundidade (G0 item 11) — 2ª execução do job no
                # mesmo dia não reenvia um agendamento já confirmado como
                # enviado nesta execução anterior.
                ja_processadas += 1
                continue

            try:
                await self._processar_candidato(candidato)
                enviadas += 1
            except _StatusNaoConfirmadoError:
                falhas += 1
            except (MessagingError, KuraApiError, KuraTimeoutError) as exc:
                falhas += 1
                logger.error(
                    "confirmacao_d1: falha ao processar id_agendamento=%s tipo=%s",
                    candidato.id_agendamento,
                    type(exc).__name__,
                )
                LogErroRepository.from_exception(
                    self._log_repo,
                    nm_procedure="ConfirmacaoD1Service.executar",
                    exc=exc,
                    parametros=f"id_agendamento={candidato.id_agendamento}",
                )
            except Exception as exc:
                # LGPD (mesma disciplina da LembreteVacinaService): nunca
                # logger.exception aqui -- exc_info reimprimiria a cadeia de
                # causa completa, que pode carregar texto não sanitizado de um
                # chamador futuro.
                falhas += 1
                logger.error(
                    "confirmacao_d1: erro inesperado id_agendamento=%s tipo=%s",
                    candidato.id_agendamento,
                    type(exc).__name__,
                )
                LogErroRepository.from_exception(
                    self._log_repo,
                    nm_procedure="ConfirmacaoD1Service.executar",
                    exc=exc,
                    parametros=f"id_agendamento={candidato.id_agendamento}",
                )

        return ResumoExecucaoConfirmacaoD1(
            total=len(candidatos),
            enviadas=enviadas,
            falhas=falhas,
            ja_processadas=ja_processadas,
        )

    async def _processar_candidato(self, candidato: ConfirmacaoPendenteItemDTO) -> None:
        """Envia a mensagem, confirma o status real e só então marca enviado +
        registra a pendência. Levanta `_StatusNaoConfirmadoError` se o status
        não confirmar entrega -- contado como falha pelo chamador, sem marcar
        nada no `.NET` (próxima execução pode tentar de novo)."""
        mensagem = confirmacao_d1(
            nm_tutor=candidato.nm_tutor,
            nm_pet=candidato.nm_pet,
            dt_agendamento=candidato.dt_agendamento,
            ds_servico=candidato.ds_servico,
        )

        sid = await asyncio.to_thread(
            self._twilio.enviar_whatsapp, candidato.ds_whatsapp, mensagem
        )

        status = await self._consultar_status_com_retentativas(sid)

        if status is None or status.status not in _STATUS_SUCESSO:
            # G0 item 10: "201 queued" (ou qualquer status não-terminal de
            # sucesso) não é entrega -- nunca marca lembrete-enviado nem
            # registra pendência de um envio que pode não ter chegado.
            logger.warning(
                "confirmacao_d1: envio não confirmado id_agendamento=%s status=%s codigo=%s",
                candidato.id_agendamento,
                status.status if status else "desconhecido",
                status.error_code if status else None,
            )
            raise _StatusNaoConfirmadoError()

        await self._kura.marcar_lembrete_enviado(candidato.id_agendamento)

        telefone = chave_telefone(candidato.ds_whatsapp)
        self._store.registrar(
            telefone,
            PendenciaConfirmacao(
                id_agendamento=candidato.id_agendamento,
                id_tutor=candidato.id_tutor,
                expira_em=datetime.now(tz=UTC) + timedelta(hours=_VALIDADE_PENDENCIA_HORAS),
            ),
        )

    async def _consultar_status_com_retentativas(self, message_sid: str) -> StatusMensagem | None:
        """Até `len(_INTERVALOS_CONSULTA_STATUS)` consultas, espaçadas, até um
        status TERMINAL (sucesso ou falha). Devolve a última consulta mesmo que
        não-terminal (o chamador trata como não confirmado)."""
        status: StatusMensagem | None = None
        for intervalo in _INTERVALOS_CONSULTA_STATUS:
            await asyncio.sleep(intervalo)
            try:
                status = await asyncio.to_thread(self._twilio.consultar_status, message_sid)
            except MessagingError:
                return None
            if status.status in _STATUS_SUCESSO or status.status in _STATUS_FALHA:
                return status
        return status
