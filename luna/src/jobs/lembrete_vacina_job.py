"""Entry point APScheduler — executa LembreteVacinaService em horário configurado."""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from src.services.notification_service import LembreteVacinaService

logger = logging.getLogger(__name__)


class LembreteVacinaJob:
    """Wraps LembreteVacinaService para execução agendada via APScheduler."""

    def __init__(self, service: LembreteVacinaService) -> None:
        self._service = service

    def executar(self) -> None:
        """Chamado pelo scheduler a cada tick agendado."""
        logger.info("LembreteVacinaJob: iniciando execução")
        resumo = self._service.executar()
        logger.info(
            "LembreteVacinaJob concluído — total=%d enviadas=%d falhas=%d ja_enviadas=%d",
            resumo.total,
            resumo.enviadas,
            resumo.falhas,
            resumo.ja_enviadas,
        )

    def iniciar_scheduler(self, hora: int = 8, minuto: int = 0) -> None:
        """Inicia o BlockingScheduler com execução diária no horário especificado (BRT)."""
        scheduler = BlockingScheduler(timezone="America/Sao_Paulo")
        scheduler.add_job(self.executar, "cron", hour=hora, minute=minuto)
        logger.info(
            "Scheduler iniciado — executa diariamente às %02d:%02d BRT", hora, minuto
        )
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler encerrado pelo usuário")
