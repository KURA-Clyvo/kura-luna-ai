"""Tests for RacaRepository."""
from unittest.mock import MagicMock

import pytest

from src.db.models.raca import Raca
from src.db.repositories.raca_repo import RacaRepository, _SQL


def _make_pool(fetchone_return: object) -> MagicMock:
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fetchone_return
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.get_connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)
    return mock_pool


def test_buscar_por_nome_retorna_raca() -> None:
    pool = _make_pool((1, "Labrador", "displasia coxofemoral", 1))
    repo = RacaRepository(pool=pool)
    raca = repo.buscar_por_nome("Labrador")

    assert isinstance(raca, Raca)
    assert raca.id_raca == 1
    assert raca.nm_raca == "Labrador"
    assert raca.ds_predisposicao == "displasia coxofemoral"
    assert raca.id_especie == 1


def test_buscar_por_nome_retorna_none_quando_nao_encontrada() -> None:
    pool = _make_pool(None)
    repo = RacaRepository(pool=pool)
    result = repo.buscar_por_nome("Raça Inexistente")
    assert result is None


def test_buscar_por_nome_sem_predisposicao() -> None:
    pool = _make_pool((2, "SRD", None, 1))
    repo = RacaRepository(pool=pool)
    raca = repo.buscar_por_nome("SRD")
    assert raca is not None
    assert raca.ds_predisposicao is None


def test_buscar_por_nome_usa_upper_bind_variable() -> None:
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.get_connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)

    repo = RacaRepository(pool=mock_pool)
    repo.buscar_por_nome("golden retriever")

    mock_cursor.execute.assert_called_once_with(_SQL, {"nm": "golden retriever"})


def test_buscar_por_nome_case_insensitive_via_sql() -> None:
    """SQL usa UPPER() — o Python passa o nome como está, o Oracle faz a normalização."""
    pool = _make_pool((3, "Golden Retriever", None, 1))
    repo = RacaRepository(pool=pool)
    raca = repo.buscar_por_nome("golden retriever")
    assert raca is not None
    assert raca.nm_raca == "Golden Retriever"
