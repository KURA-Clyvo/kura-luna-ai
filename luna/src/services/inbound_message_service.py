"""Serviço de processamento de mensagens WhatsApp recebidas."""
import asyncio
import logging
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone

from src.ai.triage_engine import TriageEngine, TriageResult
from src.db.repositories.log_erro_repo import LogErroRepository
from src.integration.dtos import InteractionRequestDTO, TriageRequestDTO, TutorContextoDTO
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
# LU-07 item 4: tutor não identificado também é triado. Em ALTA, sem tutor
# não sabemos qual é a clínica (não há veterinário vinculado para notificar),
# então a resposta é genérica e orienta busca imediata — nunca cita nome de
# clínica.
_RESPOSTA_ALTA_TUTOR_DESCONHECIDO = (
    "Identificamos sintomas que podem ser urgentes. "
    "Procure atendimento veterinário imediato ou o pronto atendimento "
    "veterinário mais próximo."
)
# LU-07 fix wave 2, item 1: rede de segurança na resposta.
# Ruling do Felipe (15/09): o classificador decide só a PRIORIDADE NA FILA da
# clínica — nunca mais decide se o tutor recebe orientação de emergência.
# Vocabulário nunca vai cobrir o jeito de escrever de todo tutor, então toda
# resposta que NÃO é ALTA carrega esta linha fixa, curta, sem nome de
# clínica, sem diagnóstico, sem prometer atendimento — só o critério objetivo
# de quando procurar atendimento imediato por conta própria. ALTA não muda
# (já orienta atendimento imediato com texto próprio) e não deve duplicar
# esta linha (ver TestRedeDeSeguranca).
# Constante única (DRY) reaproveitada nas 3 respostas não-ALTA abaixo.
# 257 caracteres — dentro do limite de 320 do brief e muito abaixo do limite
# de corpo de mensagem do WhatsApp/Twilio (1600 caracteres, documentado pela
# Twilio, não presente em código deste repo — nenhuma constante correspondente
# existe aqui hoje). Mensagem final mais longa (BAIXA + prefixo de pet único)
# fica bem abaixo de 400 caracteres.
_ORIENTACAO_EMERGENCIA = (
    "Se o animal apresentar dificuldade para respirar, sangramento que não "
    "para, desmaio ou não responder, convulsão, tiver ingerido algo tóxico "
    "ou remédio humano, sofrido queda ou atropelamento, ou não conseguir "
    "urinar, procure atendimento veterinário imediato."
)

_RESPOSTA_MEDIA = f"Mensagem recebida. Nossa equipe retorna em até 2 horas. {_ORIENTACAO_EMERGENCIA}"
_RESPOSTA_BAIXA = f"Mensagem registrada. Respondemos em horário comercial. {_ORIENTACAO_EMERGENCIA}"
_RESPOSTA_FALLBACK = f"Recebemos sua mensagem e retornaremos em breve. {_ORIENTACAO_EMERGENCIA}"

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
        # LU-07 fix wave 1 (A6): `urgencia` fica FORA do try — classificamos
        # antes de qualquer chamada de rede (item 4 original) e guardamos o
        # resultado aqui em cima, para que o except abaixo saiba a urgência
        # mesmo quando o `.NET` falha (timeout em buscar_tutor_por_telefone
        # ou em registrar_interacao) DEPOIS da classificação. Sem isso, uma
        # ALTA já calculada era descartada e o tutor recebia o fallback
        # genérico — violação da regra 6 (§4 do backlog: em ALTA, sempre
        # orienta atendimento imediato).
        urgencia: str | None = None
        try:
            triage_result = self._triage.classificar(msg.corpo)
            urgencia = triage_result.urgencia
            return await self._processar_interno(msg, triage_result)
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
            return await self._enviar_fallback(msg, urgencia)

    async def _processar_interno(
        self, msg: InboundMessage, triage_result: TriageResult
    ) -> ProcessamentoResult:
        # LU-07 item 4: classifica ANTES de saber se o tutor está
        # identificado — tutor não cadastrado também é triado (auditoria §3
        # do backlog). A resposta e o registro variam conforme `tutor`
        # abaixo, mas a urgência em si nunca depende de tutor existir.
        # (classificação agora acontece em processar(), ver A6 acima)
        urgencia = triage_result.urgencia

        tutor = await self._kura.buscar_tutor_por_telefone(msg.numero_origem)

        id_interacao = await self._kura.registrar_interacao(
            InteractionRequestDTO(
                id_tutor=tutor.id_tutor if tutor else None,
                ds_canal="WHATSAPP",
                ds_direcao="INBOUND",
                ds_conteudo=msg.corpo,
                dt_recebimento=datetime.now(tz=timezone.utc),
                # Sem tutor não há FK válida para TRIAGEM_LUNA (id_tutor é
                # obrigatório lá) — registrar_triagem() nunca é chamado neste
                # caminho, então a urgência vai em ds_metadados da própria
                # interação para não se perder.
                ds_metadados=(
                    {"urgencia": urgencia, "regras_versao": triage_result.regras_versao}
                    if tutor is None
                    else None
                ),
            )
        )

        if tutor:
            # Regra 6: falha de telemetria não derruba a resposta
            try:
                await self._kura.registrar_triagem(
                    TriageRequestDTO(
                        id_interacao=id_interacao,
                        id_tutor=tutor.id_tutor,
                        sintomas=triage_result.sintomas_detectados,
                        ds_urgencia=triage_result.urgencia,
                        nr_score=triage_result.score,
                        ds_recomendacao=_RESPOSTAS.get(triage_result.urgencia, _RESPOSTA_FALLBACK),
                        regras_versao=triage_result.regras_versao,
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

        resposta = self._compor_resposta(urgencia, tutor)
        await asyncio.to_thread(self._twilio.enviar_whatsapp, msg.numero_origem, resposta)

        return ProcessamentoResult(
            id_interacao=id_interacao,
            urgencia=urgencia,
            resposta_enviada=resposta,
        )

    @staticmethod
    def _compor_resposta(urgencia: str, tutor: TutorContextoDTO | None) -> str:
        """Monta a resposta ao tutor a partir da urgência (LU-07 itens 4 e 5).

        ALTA sem tutor identificado usa uma resposta genérica sem nome de
        clínica (não sabemos qual é). Com tutor identificado e exatamente 1
        pet, prefixa contexto ("Recebemos a mensagem sobre o <pet>…") — com
        0 ou 2+ pets, texto neutro (não chutar qual pet).
        """
        if urgencia == "ALTA":
            base = _RESPOSTA_ALTA if tutor else _RESPOSTA_ALTA_TUTOR_DESCONHECIDO
        else:
            base = _RESPOSTAS.get(urgencia, _RESPOSTA_FALLBACK)

        if tutor and len(tutor.pets) == 1:
            pet_nome = tutor.pets[0].nm_pet
            return f"Recebemos a mensagem sobre o {pet_nome}. {base}"
        return base

    async def _enviar_fallback(
        self, msg: InboundMessage, urgencia: str | None = None
    ) -> ProcessamentoResult:
        """Envia resposta genérica ao tutor em caso de erro não recuperável.

        LU-07 fix wave 1 (A6): se a urgência já classificada (antes da falha
        de rede) for ALTA, o fallback genérico NÃO é enviado — vai a resposta
        de emergência sem nome de clínica (`_RESPOSTA_ALTA_TUTOR_DESCONHECIDO`,
        mesmo texto do caminho "tutor não identificado", porque não sabemos
        se o `.NET`/veterinário foi de fato notificado). Nunca omitimos
        orientação de atendimento imediato numa ALTA.
        """
        resposta = (
            _RESPOSTA_ALTA_TUTOR_DESCONHECIDO if urgencia == "ALTA" else _RESPOSTA_FALLBACK
        )
        try:
            await asyncio.to_thread(
                self._twilio.enviar_whatsapp, msg.numero_origem, resposta
            )
        except Exception as exc:
            # LGPD: nunca logar o telefone do tutor. O SID do Twilio é um
            # identificador não-PII já usado para correlação com o console
            # do Twilio (mesmo tratamento da TASK-35 em LOG_ERRO).
            logger.error("Falha ao enviar fallback message_sid=%s: %s", msg.message_sid, exc)
        return ProcessamentoResult(
            id_interacao=None,
            urgencia=urgencia,
            resposta_enviada=resposta,
        )
