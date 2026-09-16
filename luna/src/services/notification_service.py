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

# LU-04 fix wave 1 (ruling do Felipe, 15/09, sobre achado A3 da G2 da LU-04):
# "o tutor recebe UM lembrete por vacina". A trava de idempotencia do repo
# (`NotificacaoRepository.existe_pendente_para_vacina`) tinha default de 24h,
# enquanto a view avisa a vacina com `_DIAS_ANTECEDENCIA` (7) dias de
# antecedencia e o scheduler (LU-04) roda o cron 1x/dia -- medido no Oracle
# real (lu-04-revisao.md, sonda de A3): uma linha de 30h cai FORA de uma
# janela de 24h, entao no 3o dia o predicado deixa de achar a notificacao do
# 1o dia e o lote cria linha nova + chama o Twilio de novo -- 3 a 4
# lembretes iguais ao longo dos 7 dias de antecedencia.
#
# Forma escolhida: (a) do brief -- janela DERIVADA desta constante
# (`24 * _DIAS_ANTECEDENCIA` = 168h), nunca um `168` escrito a mao. A forma
# (b) (chave de negocio por `dt_proxima_dose`) foi descartada porque
# NOTIFICACAO nao tem coluna equivalente (ver `_SQL_INSERT` em
# `notificacao_repo.py` -- so ID_CLINICA/ID_TUTOR/ID_PET/DS_TITULO/
# DS_MENSAGEM/DS_CANAL/DS_TIPO/ST_ENVIO) e criar uma exigiria migration nova
# (V22+), fora do escopo desta fix wave.
_JANELA_IDEMPOTENCIA_HORAS = 24 * _DIAS_ANTECEDENCIA


@dataclass(frozen=True, slots=True)
class ResumoExecucao:
    """Resultado do ciclo de envio de lembretes.

    ``total`` = elegíveis processados (``enviadas + falhas + ja_enviadas``)
    + ``sem_consentimento``. ``sem_consentimento`` (LU-03/D-L4) conta linhas
    da janela cujo tutor não consente ``LEMBRETES`` — 0 linhas em
    NOTIFICACAO, 0 chamadas Twilio para elas.
    """

    total: int
    enviadas: int
    falhas: int
    ja_enviadas: int
    sem_consentimento: int = 0


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
        sem_consentimento = self._vacina_repo.contar_sem_consentimento(dias=_DIAS_ANTECEDENCIA)

        enviadas = 0
        falhas = 0
        ja_enviadas = 0

        for vacina in vacinas:
            try:
                if vacina.ds_whatsapp is None:
                    # Tutor consente LEMBRETES (linha já veio filtrada por
                    # ST_CONSENTE_LEMBRETE='S'), mas TUTOR.DS_WHATSAPP é
                    # nullable -- nunca enviar "None" como destino Twilio.
                    # Pulado e contado como falha (não há canal de envio).
                    falhas += 1
                    self._log_repo.registrar(
                        nm_procedure="LembreteVacinaService.executar",
                        codigo=-1,
                        mensagem="Tutor consente LEMBRETES mas nao tem WhatsApp cadastrado.",
                        parametros=f"id_pet={vacina.id_pet}",
                    )
                    continue

                if self._notificacao_repo.existe_pendente_para_vacina(
                    id_tutor=vacina.id_tutor,
                    id_pet=vacina.id_pet,
                    nm_vacina=vacina.nm_vacina,
                    janela_horas=_JANELA_IDEMPOTENCIA_HORAS,
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
                    id_clinica=vacina.id_clinica,
                    id_tutor=vacina.id_tutor,
                    id_pet=vacina.id_pet,
                    ds_canal="WHATSAPP",
                    ds_tipo="LEMBRETE_VACINA",
                    ds_titulo=f"Lembrete: {vacina.nm_vacina}",
                    ds_mensagem=mensagem,
                    st_envio="PENDENTE",
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
                    # LGPD (LU-03): DS_ERRO_ENVIO recebe só tipo + código do
                    # erro Twilio -- nunca `str(exc)` (que, para chamadores
                    # futuros do SDK, poderia um dia embutir texto livre).
                    codigo = exc.codigo
                    msg_erro = (
                        f"{type(exc).__name__}[{codigo}]"
                        if codigo is not None
                        else type(exc).__name__
                    )
                    self._notificacao_repo.marcar_falha(
                        id_notificacao=id_notif,
                        msg_erro=msg_erro,
                    )
                    LogErroRepository.from_exception(
                        self._log_repo,
                        nm_procedure="LembreteVacinaService.executar",
                        exc=exc,
                        parametros=f"id_pet={vacina.id_pet} nm_vacina={vacina.nm_vacina}",
                    )
                    falhas += 1

            except Exception as exc:
                # LGPD (LU-03): nunca `logger.exception` aqui -- ele anexa
                # `exc_info=True` e reimprime a cadeia de causa completa
                # (`__cause__`/`__context__`), que pode conter texto livre de
                # um erro não relacionado a Twilio (ex.: exceção do Oracle
                # cuja mensagem, em algum caminho futuro, embuta um valor de
                # bind). Loga só tipo + código, sem exc_info.
                logger.error(
                    "Erro inesperado ao processar vacina id_pet=%s nm_vacina=%s "
                    "tipo=%s codigo=%s",
                    vacina.id_pet,
                    vacina.nm_vacina,
                    type(exc).__name__,
                    getattr(exc, "errno", None),
                )
                LogErroRepository.from_exception(
                    self._log_repo,
                    nm_procedure="LembreteVacinaService.executar",
                    exc=exc,
                    parametros=f"id_pet={vacina.id_pet} nm_vacina={vacina.nm_vacina}",
                )
                falhas += 1

        return ResumoExecucao(
            total=len(vacinas) + sem_consentimento,
            enviadas=enviadas,
            falhas=falhas,
            ja_enviadas=ja_enviadas,
            sem_consentimento=sem_consentimento,
        )
