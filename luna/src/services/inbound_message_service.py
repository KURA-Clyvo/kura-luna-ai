"""Serviço de processamento de mensagens WhatsApp recebidas."""
import asyncio
import logging
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone

from src.ai.triage_engine import TriageEngine
from src.db.repositories.log_erro_repo import LogErroRepository
from src.integration.dtos import InteractionRequestDTO, TriageRequestDTO
from src.integration.exceptions import KuraTimeoutError
from src.integration.kura_client import IKuraClient
from src.messaging.twilio_client import ITwilioGateway
from src.messaging.twilio_inbound import InboundMessage

logger = logging.getLogger(__name__)

_RESPOSTA_ALTA = (
    "Identificamos sintomas que requerem atenção urgente. "
    "Estamos notificando seu veterinário. "
    "Para emergências imediatas, ligue para a clínica."
)
_RESPOSTA_MEDIA = "Mensagem recebida. Nossa equipe retorna em até 2 horas."
_RESPOSTA_BAIXA = "Mensagem registrada. Respondemos em horário comercial."
_RESPOSTA_FALLBACK = "Recebemos sua mensagem e retornaremos em breve."

_RESPOSTAS: dict[str, str] = {
    "ALTA": _RESPOSTA_ALTA,
    "MEDIA": _RESPOSTA_MEDIA,
    "BAIXA": _RESPOSTA_BAIXA,
}


@dataclass(frozen=True)
class ProcessamentoResult:
    """Resultado do processamento de uma mensagem inbound."""

    id_interacao: int | None
    urgencia: str | None
    resposta_enviada: str


class InboundMessageService:
    """Orquestra recebimento → triagem → registro → resposta ao tutor.

    Todas as etapas de telemetria (.NET) são resilientes: falhas não bloqueiam
    a resposta ao tutor. Apenas a falta de envio final é tratada como crítica,
    e mesmo assim apenas logada (nunca propagada).
    """

    def __init__(
        self,
        kura_client: IKuraClient,
        triage_engine: TriageEngine,
        twilio_gateway: ITwilioGateway,
        log_repo: LogErroRepository,
    ) -> None:
        self._kura = kura_client
        self._triage = triage_engine
        self._twilio = twilio_gateway
        self._log = log_repo

    async def processar(self, msg: InboundMessage) -> ProcessamentoResult:
        """Processa mensagem inbound com fluxo resiliente completo."""
        try:
            return await self._processar_interno(msg)
        except Exception as exc:
            logger.exception("Erro inesperado em InboundMessageService.processar")
            LogErroRepository.from_exception(
                self._log,
                nm_procedure="InboundMessageService.processar",
                exc=exc,
                # LGPD: nunca logar o telefone do tutor. O SID do Twilio é um
                # identificador não-PII já usado para correlação com o
                # console do Twilio (ver src/web/routers/whatsapp.py).
                parametros=f"message_sid={msg.message_sid}",
            )
            return await self._enviar_fallback(msg)

    async def _processar_interno(self, msg: InboundMessage) -> ProcessamentoResult:
        tutor = await self._kura.buscar_tutor_por_telefone(msg.numero_origem)

        id_interacao = await self._kura.registrar_interacao(
            InteractionRequestDTO(
                id_tutor=tutor.id_tutor if tutor else None,
                ds_canal="WHATSAPP",
                ds_direcao="INBOUND",
                ds_conteudo=msg.corpo,
                dt_recebimento=datetime.now(tz=timezone.utc),
            )
        )

        urgencia: str | None = None

        if tutor:
            triage_result = self._triage.classificar(msg.corpo)
            urgencia = triage_result.urgencia

            # Regra 6: falha de telemetria não derruba a resposta
            try:
                await self._kura.registrar_triagem(
                    TriageRequestDTO(
                        id_interacao=id_interacao,
                        id_tutor=tutor.id_tutor,
                        sintomas=triage_result.sintomas_detectados,
                        ds_urgencia=triage_result.urgencia,  # type: ignore[arg-type]
                        nr_score=triage_result.score,
                        ds_recomendacao=_RESPOSTAS.get(triage_result.urgencia, _RESPOSTA_FALLBACK),
                    )
                )
            except Exception as exc:
                logger.warning("Falha ao registrar triagem (não crítico): %s", exc)
                LogErroRepository.from_exception(
                    self._log,
                    nm_procedure="InboundMessageService._registrar_triagem",
                    exc=exc,
                    parametros=str(id_interacao),
                )

        resposta = _RESPOSTAS.get(urgencia or "", _RESPOSTA_FALLBACK)
        await asyncio.to_thread(self._twilio.enviar_whatsapp, msg.numero_origem, resposta)

        return ProcessamentoResult(
            id_interacao=id_interacao,
            urgencia=urgencia,
            resposta_enviada=resposta,
        )

    async def _enviar_fallback(self, msg: InboundMessage) -> ProcessamentoResult:
        """Envia resposta genérica ao tutor em caso de erro não recuperável."""
        try:
            await asyncio.to_thread(
                self._twilio.enviar_whatsapp, msg.numero_origem, _RESPOSTA_FALLBACK
            )
        except Exception as exc:
            # LGPD: nunca logar o telefone do tutor. O SID do Twilio é um
            # identificador não-PII já usado para correlação com o console
            # do Twilio (mesmo tratamento da TASK-35 em LOG_ERRO).
            logger.error("Falha ao enviar fallback message_sid=%s: %s", msg.message_sid, exc)
        return ProcessamentoResult(
            id_interacao=None,
            urgencia=None,
            resposta_enviada=_RESPOSTA_FALLBACK,
        )
