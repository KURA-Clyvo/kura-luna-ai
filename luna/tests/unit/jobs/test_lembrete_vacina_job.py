"""Testes do LembreteVacinaJob (wrapper de log) e do tick do scheduler (LU-04).

`iniciar_scheduler` (BlockingScheduler) foi removido nesta task: `grep` em
`src/` confirmou 0 chamadores em produção (a CLI sempre chamou
`service.executar()` direto). O agendamento real agora vive no `lifespan` via
`AsyncIOScheduler` (ver `src/web/app.py` e `executar_tick_lembrete_vacina`
abaixo)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from twilio.base.exceptions import TwilioException

from src.jobs.lembrete_vacina_job import LembreteVacinaJob, executar_tick_lembrete_vacina
from src.services.notification_service import ResumoExecucao


def test_executar_delega_para_servico() -> None:
    mock_svc = MagicMock()
    mock_svc.executar.return_value = ResumoExecucao(
        total=3, enviadas=3, falhas=0, ja_enviadas=0
    )
    job = LembreteVacinaJob(mock_svc)
    resumo = job.executar()
    mock_svc.executar.assert_called_once()
    assert resumo.total == 3


def test_job_nao_tem_mais_iniciar_scheduler() -> None:
    """0 chamadores confirmados por grep -- método removido, não só descontinuado."""
    assert not hasattr(LembreteVacinaJob, "iniciar_scheduler")


# ---------------------------------------------------------------------------
# executar_tick_lembrete_vacina — chamado pelo cron do AsyncIOScheduler
# ---------------------------------------------------------------------------

def _fake_app(pool: object = "pool-real", lock: asyncio.Lock | None = None) -> SimpleNamespace:
    state = SimpleNamespace(
        pool=pool,
        settings=MagicMock(),
        lembrete_lock=lock if lock is not None else asyncio.Lock(),
    )
    return SimpleNamespace(state=state)


async def test_tick_ignora_se_lock_ocupado() -> None:
    lock = asyncio.Lock()
    await lock.acquire()
    app = _fake_app(lock=lock)

    with patch("src.jobs.lembrete_vacina_job.criar_lembrete_service") as mock_factory:
        await executar_tick_lembrete_vacina(app)  # type: ignore[arg-type]

    mock_factory.assert_not_called()


async def test_tick_ignora_se_pool_none() -> None:
    app = _fake_app(pool=None)

    with patch("src.jobs.lembrete_vacina_job.criar_lembrete_service") as mock_factory:
        await executar_tick_lembrete_vacina(app)  # type: ignore[arg-type]

    mock_factory.assert_not_called()


async def test_tick_ignora_sem_derrubar_processo_quando_twilio_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """F4-1: sem credencial Twilio, a fábrica levanta TwilioException -- o
    tick deve capturar, logar e retornar (nunca propagar).

    A6 (achado MENOR da G2, lu-04-revisao.md): a versão anterior deste teste
    só provava o "segue" (não levantou) -- um tick que engolisse a falha em
    total silêncio também passaria. Agora também prova o "loga": a linha de
    warning tem que existir, e sem telefone/conteúdo (LGPD)."""
    app = _fake_app()

    with caplog.at_level("WARNING"):
        with patch(
            "src.jobs.lembrete_vacina_job.criar_lembrete_service",
            side_effect=TwilioException("Credentials are required to create a TwilioClient"),
        ):
            await executar_tick_lembrete_vacina(app)  # type: ignore[arg-type]
    # não levantou -- se chegou aqui, passou.
    assert "credencial Twilio ausente/inválida" in caplog.text
    assert "Credentials are required" not in caplog.text  # nunca o texto cru da exceção


async def test_tick_executa_servico_quando_tudo_disponivel() -> None:
    app = _fake_app()
    mock_service = MagicMock()
    mock_service.executar.return_value = ResumoExecucao(
        total=1, enviadas=1, falhas=0, ja_enviadas=0
    )

    with patch(
        "src.jobs.lembrete_vacina_job.criar_lembrete_service", return_value=mock_service
    ):
        await executar_tick_lembrete_vacina(app)  # type: ignore[arg-type]

    mock_service.executar.assert_called_once()
    assert not app.state.lembrete_lock.locked(), "lock deve ser liberado ao final do tick"


async def test_tick_libera_lock_mesmo_se_servico_falha() -> None:
    app = _fake_app()
    mock_service = MagicMock()
    mock_service.executar.side_effect = RuntimeError("boom")

    with patch(
        "src.jobs.lembrete_vacina_job.criar_lembrete_service", return_value=mock_service
    ):
        await executar_tick_lembrete_vacina(app)  # type: ignore[arg-type]

    assert not app.state.lembrete_lock.locked()
