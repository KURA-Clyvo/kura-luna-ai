"""Testes do LembreteVacinaJob (APScheduler wrapper)."""
from unittest.mock import MagicMock, patch

from src.jobs.lembrete_vacina_job import LembreteVacinaJob
from src.services.notification_service import ResumoExecucao


def test_executar_delega_para_servico() -> None:
    mock_svc = MagicMock()
    mock_svc.executar.return_value = ResumoExecucao(
        total=3, enviadas=3, falhas=0, ja_enviadas=0
    )
    job = LembreteVacinaJob(mock_svc)
    job.executar()
    mock_svc.executar.assert_called_once()


def test_iniciar_scheduler_adiciona_job_cron() -> None:
    mock_svc = MagicMock()
    job = LembreteVacinaJob(mock_svc)

    mock_scheduler = MagicMock()
    mock_scheduler.start.side_effect = KeyboardInterrupt

    with patch(
        "src.jobs.lembrete_vacina_job.BlockingScheduler", return_value=mock_scheduler
    ):
        job.iniciar_scheduler(hora=9, minuto=30)

    mock_scheduler.add_job.assert_called_once_with(
        job.executar, "cron", hour=9, minute=30
    )
    mock_scheduler.start.assert_called_once()


def test_iniciar_scheduler_trata_system_exit() -> None:
    """SystemExit deve ser absorvido sem propagar."""
    mock_svc = MagicMock()
    job = LembreteVacinaJob(mock_svc)

    mock_scheduler = MagicMock()
    mock_scheduler.start.side_effect = SystemExit(0)

    with patch(
        "src.jobs.lembrete_vacina_job.BlockingScheduler", return_value=mock_scheduler
    ):
        job.iniciar_scheduler()  # não deve levantar
