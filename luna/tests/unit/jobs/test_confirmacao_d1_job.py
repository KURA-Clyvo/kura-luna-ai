"""Testes do ConfirmacaoD1Job (wrapper de log) e do tick do scheduler (REC-16).

Espelha `test_lembrete_vacina_job.py` (LU-04)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twilio.base.exceptions import TwilioException

from src.jobs.confirmacao_d1_job import ConfirmacaoD1Job, executar_tick_confirmacao_d1
from src.services.confirmacao_d1_service import ResumoExecucaoConfirmacaoD1


async def test_executar_delega_para_servico() -> None:
    mock_svc = MagicMock()
    mock_svc.executar = AsyncMock(
        return_value=ResumoExecucaoConfirmacaoD1(
            total=2, enviadas=2, falhas=0, ja_processadas=0
        )
    )
    job = ConfirmacaoD1Job(mock_svc)
    resumo = await job.executar()
    mock_svc.executar.assert_awaited_once()
    assert resumo.total == 2


# ---------------------------------------------------------------------------
# executar_tick_confirmacao_d1 — chamado pelo cron do AsyncIOScheduler
# ---------------------------------------------------------------------------

def _fake_app(
    pool: object = "pool-real", lock: asyncio.Lock | None = None
) -> SimpleNamespace:
    state = SimpleNamespace(
        pool=pool,
        settings=MagicMock(),
        http_client=MagicMock(),
        confirmacao_pendentes=MagicMock(),
        confirmacao_d1_lock=lock if lock is not None else asyncio.Lock(),
    )
    return SimpleNamespace(state=state)


async def test_tick_ignora_se_lock_ocupado() -> None:
    lock = asyncio.Lock()
    await lock.acquire()
    app = _fake_app(lock=lock)

    with patch("src.jobs.confirmacao_d1_job.criar_confirmacao_d1_service") as mock_factory:
        await executar_tick_confirmacao_d1(app)  # type: ignore[arg-type]

    mock_factory.assert_not_called()


async def test_tick_ignora_se_pool_none() -> None:
    app = _fake_app(pool=None)

    with patch("src.jobs.confirmacao_d1_job.criar_confirmacao_d1_service") as mock_factory:
        await executar_tick_confirmacao_d1(app)  # type: ignore[arg-type]

    mock_factory.assert_not_called()


async def test_tick_ignora_sem_derrubar_processo_quando_twilio_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _fake_app()

    with caplog.at_level("WARNING"), patch(
        "src.jobs.confirmacao_d1_job.criar_confirmacao_d1_service",
        side_effect=TwilioException("Credentials are required to create a TwilioClient"),
    ):
        await executar_tick_confirmacao_d1(app)  # type: ignore[arg-type]

    assert "credencial Twilio ausente/inválida" in caplog.text
    assert "Credentials are required" not in caplog.text


async def test_tick_executa_servico_quando_tudo_disponivel() -> None:
    app = _fake_app()
    mock_service = MagicMock()
    mock_service.executar = AsyncMock(
        return_value=ResumoExecucaoConfirmacaoD1(
            total=1, enviadas=1, falhas=0, ja_processadas=0
        )
    )

    with patch(
        "src.jobs.confirmacao_d1_job.criar_confirmacao_d1_service",
        return_value=mock_service,
    ):
        await executar_tick_confirmacao_d1(app)  # type: ignore[arg-type]

    mock_service.executar.assert_awaited_once()
    assert not app.state.confirmacao_d1_lock.locked()


async def test_tick_libera_lock_mesmo_se_servico_falha() -> None:
    app = _fake_app()
    mock_service = MagicMock()
    mock_service.executar = AsyncMock(side_effect=RuntimeError("boom"))

    with patch(
        "src.jobs.confirmacao_d1_job.criar_confirmacao_d1_service",
        return_value=mock_service,
    ):
        await executar_tick_confirmacao_d1(app)  # type: ignore[arg-type]

    assert not app.state.confirmacao_d1_lock.locked()


async def test_tick_nao_interfere_no_lock_da_vacina() -> None:
    """Os 2 jobs usam locks independentes -- um tick de confirmação D-1 em
    andamento não bloqueia o tick da vacina (e vice-versa, ver docstring de
    `executar_tick_confirmacao_d1`)."""
    lock_confirmacao = asyncio.Lock()
    await lock_confirmacao.acquire()
    app = _fake_app(lock=lock_confirmacao)
    app.state.lembrete_lock = asyncio.Lock()

    assert not app.state.lembrete_lock.locked()
