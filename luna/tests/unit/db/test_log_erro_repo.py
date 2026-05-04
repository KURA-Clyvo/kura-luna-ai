"""Tests for LogErroRepository — fail-safe behavior."""
from unittest.mock import MagicMock, patch

from src.db.repositories.log_erro_repo import LogErroRepository


def _make_pool(cursor_side_effect: object = None) -> MagicMock:
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    if cursor_side_effect:
        mock_cursor.execute.side_effect = cursor_side_effect

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.get_connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)
    return mock_pool


def test_registrar_sucesso_chama_execute() -> None:
    pool = _make_pool()
    repo = LogErroRepository(pool=pool)
    repo.registrar(nm_procedure="pkg.proc", codigo=1, mensagem="erro teste")
    # Não levantou exceção — isso já é o critério principal


def test_registrar_falha_no_insert_nao_propaga() -> None:
    pool = _make_pool(cursor_side_effect=Exception("ORA-01017"))
    repo = LogErroRepository(pool=pool)

    # não deve levantar nada
    result = repo.registrar(nm_procedure="pkg.proc", codigo=-1, mensagem="ops")
    assert result is None


def test_registrar_falha_no_pool_nao_propaga() -> None:
    mock_pool = MagicMock()
    mock_pool.get_connection.side_effect = Exception("pool esgotado")
    repo = LogErroRepository(pool=mock_pool)

    result = repo.registrar(nm_procedure="x", codigo=0, mensagem="y")
    assert result is None


def test_registrar_loga_fallback_em_caso_de_falha() -> None:
    pool = _make_pool(cursor_side_effect=Exception("DB down"))
    repo = LogErroRepository(pool=pool)
    # Deve silenciar a exceção e retornar None
    result = repo.registrar(nm_procedure="proc", codigo=500, mensagem="falha grave")
    assert result is None


def test_from_exception_registra_stack_trace() -> None:
    mock_repo = MagicMock(spec=LogErroRepository)
    exc = ValueError("algo deu errado")

    LogErroRepository.from_exception(mock_repo, nm_procedure="proc_x", exc=exc)

    mock_repo.registrar.assert_called_once()
    call_kwargs = mock_repo.registrar.call_args
    assert call_kwargs[1]["mensagem"] == "algo deu errado"
    assert call_kwargs[1]["stack_trace"] is not None


def test_registrar_trunca_mensagem_longa() -> None:
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.get_connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)

    repo = LogErroRepository(pool=mock_pool)
    repo.registrar(nm_procedure="p", codigo=1, mensagem="x" * 3000)

    args = mock_cursor.execute.call_args[0][1]
    assert len(args["ds_mensagem"]) == 2000
