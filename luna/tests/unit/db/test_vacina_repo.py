"""Tests for VacinaRepository."""
from datetime import date
from unittest.mock import MagicMock

import pytest

from src.db.repositories.vacina_repo import VacinaRepository, _SQL
from src.db.models.vacina_vencendo import VacinaVencendo


def _make_pool(rows: list) -> MagicMock:
    """Build a mock pool whose cursor().fetchall() returns rows."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
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


_SAMPLE_ROW = (1, "Rex", 10, "João", "11999999999", "V10", date(2026, 6, 1), 28, "Clyvo Vet")


def test_listar_vencendo_em_lista_vazia() -> None:
    repo = VacinaRepository(pool=_make_pool([]))
    result = repo.listar_vencendo_em(dias=7)
    assert result == []


def test_listar_vencendo_em_uma_linha() -> None:
    repo = VacinaRepository(pool=_make_pool([_SAMPLE_ROW]))
    result = repo.listar_vencendo_em(dias=30)
    assert len(result) == 1
    v = result[0]
    assert isinstance(v, VacinaVencendo)
    assert v.id_pet == 1
    assert v.nm_pet == "Rex"
    assert v.nm_vacina == "V10"
    assert v.dias_restantes == 28


def test_listar_vencendo_em_n_linhas() -> None:
    rows = [
        (1, "Rex", 10, "João", "11999999999", "V10", date(2026, 6, 1), 5, "C"),
        (2, "Mel", 11, "Ana", "11888888888", "Raiva", date(2026, 6, 3), 7, "C"),
        (3, "Bob", 12, "Pedro", "11777777777", "Giardíase", date(2026, 6, 5), 10, "C"),
    ]
    repo = VacinaRepository(pool=_make_pool(rows))
    result = repo.listar_vencendo_em(dias=10)
    assert len(result) == 3
    assert result[1].nm_pet == "Mel"


def test_listar_vencendo_em_usa_bind_variable() -> None:
    """Verifica que execute() recebe dict com :dias e não f-string."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.get_connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)

    repo = VacinaRepository(pool=mock_pool)
    repo.listar_vencendo_em(dias=7)

    mock_cursor.execute.assert_called_once_with(_SQL, {"dias": 7})


def test_listar_vencendo_em_propaga_excecao_oracle() -> None:
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.execute.side_effect = Exception("ORA-00942: table not found")

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.get_connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)

    repo = VacinaRepository(pool=mock_pool)
    with pytest.raises(Exception, match="ORA-00942"):
        repo.listar_vencendo_em(dias=30)
