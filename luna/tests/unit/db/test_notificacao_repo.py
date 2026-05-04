"""Tests for NotificacaoRepository."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.db.models.notificacao import Notificacao
from src.db.repositories.notificacao_repo import NotificacaoRepository


def _make_pool(cursor_mock: MagicMock) -> MagicMock:
    cursor_mock.__enter__ = lambda s: s
    cursor_mock.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = cursor_mock
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.get_connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)
    return mock_pool


def _sample_notif(**kwargs) -> Notificacao:  # type: ignore[no-untyped-def]
    defaults = dict(
        id_tutor=1,
        ds_canal="WHATSAPP",
        ds_tipo="LEMBRETE_VACINA",
        ds_titulo="Lembrete V10",
        ds_mensagem="Vacina vencendo",
        dt_agendada=datetime(2026, 5, 10, 8, 0),
        st_status="PENDENTE",
        id_pet=2,
    )
    defaults.update(kwargs)
    return Notificacao(**defaults)


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_criar_retorna_id_gerado(mock_oracledb: MagicMock) -> None:
    out_var = MagicMock()
    out_var.getvalue.return_value = 99.0
    mock_oracledb.NUMBER = MagicMock()

    mock_cursor = MagicMock()
    mock_cursor.var.return_value = out_var

    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)
    result = repo.criar(_sample_notif())

    assert result == 99
    mock_cursor.execute.assert_called_once()


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_marcar_enviada_atualiza_status(mock_oracledb: MagicMock) -> None:
    mock_cursor = MagicMock()
    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)

    dt = datetime(2026, 5, 10, 8, 1)
    repo.marcar_enviada(id_notificacao=42, dt_enviada=dt)

    args = mock_cursor.execute.call_args
    assert args[0][1]["id_notificacao"] == 42
    assert args[0][1]["dt_enviada"] == dt


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_marcar_falha_trunca_erro(mock_oracledb: MagicMock) -> None:
    mock_cursor = MagicMock()
    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)

    repo.marcar_falha(id_notificacao=7, msg_erro="x" * 600)

    args = mock_cursor.execute.call_args
    assert len(args[0][1]["ds_erro"]) == 500


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_existe_pendente_retorna_true_quando_existe(mock_oracledb: MagicMock) -> None:
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)
    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)

    result = repo.existe_pendente_para_vacina(id_tutor=1, id_pet=2, nm_vacina="V10")
    assert result is True


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_existe_pendente_retorna_false_quando_nao_existe(mock_oracledb: MagicMock) -> None:
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0,)
    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)

    result = repo.existe_pendente_para_vacina(id_tutor=1, id_pet=2, nm_vacina="V10")
    assert result is False


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_existe_pendente_bind_variable_titulo(mock_oracledb: MagicMock) -> None:
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0,)
    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)

    repo.existe_pendente_para_vacina(id_tutor=1, id_pet=2, nm_vacina="Raiva", janela_horas=48)

    args = mock_cursor.execute.call_args
    assert args[0][1]["titulo_like"] == "%Raiva%"
    assert args[0][1]["horas"] == 48
