"""Serviço de lembrete de vacinas — orquestra repo + Twilio ponta-a-ponta."""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.db.models.notificacao import Notificacao
from src.db.repositories.log_erro_repo import LogErroRepository
from src.db.repositories.notificacao_repo import NotificacaoRepository
from src.db.repositories.vacina_repo import VacinaRepository
from src.messaging.templates import lembrete_vacina
from src.messaging.twilio_client import ITwilioGateway, MessagingError

logger = logging.getLogger(__name__)

_DIAS_ANTECEDENCIA = 7


@dataclass(frozen=True, slots=True)
class ResumoExecucao:
    """Resultado do ciclo de envio de lembretes."""

    total: int
    enviadas: int
    falhas: int
    ja_enviadas: int


class LembreteVacinaService:
    """Orquestra o ciclo completo de lembrete de vacinas via WhatsApp."""

    def __init__(
        self,
        vacina_repo: VacinaRepository,
        notificacao_repo: NotificacaoRepository,
        twilio_gateway: ITwilioGateway,
        log_repo: LogErroRepository,
    ) -> None:
        self._vacina_repo = vacina_repo
        self._notificacao_repo = notificacao_repo
        self._twilio = twilio_gateway
        self._log_repo = log_repo

    def executar(self) -> ResumoExecucao:
        """Executa o ciclo de lembretes. Falha por item não derruba o lote."""
        vacinas = self._vacina_repo.listar_vencendo_em(dias=_DIAS_ANTECEDENCIA)

        enviadas = 0
        falhas = 0
        ja_enviadas = 0

        for vacina in vacinas:
            try:
                if self._notificacao_repo.existe_pendente_para_vacina(
                    id_tutor=vacina.id_tutor,
                    id_pet=vacina.id_pet,
                    nm_vacina=vacina.nm_vacina,
                ):
                    ja_enviadas += 1
                    continue

                mensagem = lembrete_vacina(
                    nm_tutor=vacina.nm_tutor,
                    nm_pet=vacina.nm_pet,
                    nm_vacina=vacina.nm_vacina,
                    dias_restantes=vacina.dias_restantes,
                    nm_clinica=vacina.nm_clinica,
                )

                notif = Notificacao(
                    id_tutor=vacina.id_tutor,
                    id_pet=vacina.id_pet,
                    ds_canal="WHATSAPP",
                    ds_tipo="LEMBRETE_VACINA",
                    ds_titulo=f"Lembrete: {vacina.nm_vacina}",
                    ds_mensagem=mensagem,
                    dt_agendada=datetime.now(tz=timezone.utc),
                    st_status="PENDENTE",
                )

                id_notif = self._notificacao_repo.criar(notif)

                try:
                    self._twilio.enviar_whatsapp(
                        para=vacina.ds_whatsapp,
                        mensagem=mensagem,
                    )
                    self._notificacao_repo.marcar_enviada(
                        id_notificacao=id_notif,
                        dt_enviada=datetime.now(tz=timezone.utc),
                    )
                    enviadas += 1
                except MessagingError as exc:
                    self._notificacao_repo.marcar_falha(
                        id_notificacao=id_notif,
                        msg_erro=str(exc),
                    )
                    LogErroRepository.from_exception(
                        self._log_repo,
                        nm_procedure="LembreteVacinaService.executar",
                        exc=exc,
                        parametros=f"id_pet={vacina.id_pet} nm_vacina={vacina.nm_vacina}",
                    )
                    falhas += 1

            except Exception as exc:
                logger.exception(
                    "Erro inesperado ao processar vacina id_pet=%s nm_vacina=%s",
                    vacina.id_pet,
                    vacina.nm_vacina,
                )
                LogErroRepository.from_exception(
                    self._log_repo,
                    nm_procedure="LembreteVacinaService.executar",
                    exc=exc,
                    parametros=f"id_pet={vacina.id_pet} nm_vacina={vacina.nm_vacina}",
                )
                falhas += 1

        return ResumoExecucao(
            total=len(vacinas),
            enviadas=enviadas,
            falhas=falhas,
            ja_enviadas=ja_enviadas,
        )
