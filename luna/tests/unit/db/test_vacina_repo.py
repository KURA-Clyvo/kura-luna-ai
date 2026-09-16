"""Tests for VacinaRepository."""
from datetime import date
from unittest.mock import MagicMock

import pytest

from src.db.repositories.vacina_repo import (
    _SQL_CONTAR_SEM_CONSENTIMENTO,
    _SQL_LISTAR_ELEGIVEIS,
    VacinaRepository,
)
from src.db.models.vacina_vencendo import VacinaVencendo

# Nomes de coluna na MESMA ordem de _SQL_LISTAR_ELEGIVEIS — o mock expõe
# cursor.description (como o driver real) em vez de depender de posição
# implícita: LU-03 trocou o mapeamento por nome, então o teste tem de provar
# isso construindo linhas por NOME, não por índice de tupla solta
# (`_SAMPLE_ROW` posicional foi removido — era a única prova antes, e
# escondia que a ordem das colunas importava).
_COLUNAS = [
    "ID_PET", "NM_PET", "ID_TUTOR", "NM_TUTOR", "DS_WHATSAPP", "NM_VACINA",
    "DT_PROXIMA_DOSE", "DIAS_RESTANTES", "NM_CLINICA", "ID_CLINICA",
]


def _row_por_nome(**kwargs) -> tuple:
    """Monta uma tupla de linha na ordem de _COLUNAS a partir de kwargs por nome."""
    valores = {
        "ID_PET": 1, "NM_PET": "Rex", "ID_TUTOR": 10, "NM_TUTOR": "João",
        "DS_WHATSAPP": "11999999999", "NM_VACINA": "V10",
        "DT_PROXIMA_DOSE": date(2026, 6, 1), "DIAS_RESTANTES": 28,
        "NM_CLINICA": "Clyvo Vet", "ID_CLINICA": 900,
    }
    valores.update(kwargs)
    return tuple(valores[c] for c in _COLUNAS)


def _make_pool_e_cursor(rows: list[tuple], colunas: list[str] = _COLUNAS) -> tuple[MagicMock, MagicMock]:
    """Build a mock pool whose cursor exposes .description (por nome) e .fetchall()."""
    mock_cursor = MagicMock()
    mock_cursor.description = [(nome,) for nome in colunas]
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

    return mock_pool, mock_cursor


def _make_pool(rows: list[tuple], colunas: list[str] = _COLUNAS) -> MagicMock:
    """Compat: só o pool, para os testes que não precisam inspecionar o cursor."""
    pool, _ = _make_pool_e_cursor(rows, colunas)
    return pool


def test_listar_vencendo_em_lista_vazia() -> None:
    repo = VacinaRepository(pool=_make_pool([]))
    result = repo.listar_vencendo_em(dias=7)
    assert result == []


def test_listar_vencendo_em_uma_linha() -> None:
    repo = VacinaRepository(pool=_make_pool([_row_por_nome()]))
    result = repo.listar_vencendo_em(dias=30)
    assert len(result) == 1
    v = result[0]
    assert isinstance(v, VacinaVencendo)
    assert v.id_pet == 1
    assert v.nm_pet == "Rex"
    assert v.nm_vacina == "V10"
    assert v.dias_restantes == 28
    assert v.id_clinica == 900


def test_listar_vencendo_em_n_linhas() -> None:
    rows = [
        _row_por_nome(ID_PET=1, NM_PET="Rex", ID_TUTOR=10, NM_TUTOR="João",
                      DS_WHATSAPP="11999999999", NM_VACINA="V10", DIAS_RESTANTES=5,
                      NM_CLINICA="C", ID_CLINICA=900),
        _row_por_nome(ID_PET=2, NM_PET="Mel", ID_TUTOR=11, NM_TUTOR="Ana",
                      DS_WHATSAPP="11888888888", NM_VACINA="Raiva", DIAS_RESTANTES=7,
                      DT_PROXIMA_DOSE=date(2026, 6, 3), NM_CLINICA="C", ID_CLINICA=900),
        _row_por_nome(ID_PET=3, NM_PET="Bob", ID_TUTOR=12, NM_TUTOR="Pedro",
                      DS_WHATSAPP="11777777777", NM_VACINA="Giardíase", DIAS_RESTANTES=10,
                      DT_PROXIMA_DOSE=date(2026, 6, 5), NM_CLINICA="C", ID_CLINICA=900),
    ]
    repo = VacinaRepository(pool=_make_pool(rows))
    result = repo.listar_vencendo_em(dias=10)
    assert len(result) == 3
    assert result[1].nm_pet == "Mel"


def test_listar_vencendo_em_usa_bind_variable() -> None:
    """Verifica que execute() recebe dict com :dias e não f-string."""
    pool, mock_cursor = _make_pool_e_cursor([])
    repo = VacinaRepository(pool=pool)
    repo.listar_vencendo_em(dias=7)

    mock_cursor.execute.assert_called_once_with(_SQL_LISTAR_ELEGIVEIS, {"dias": 7})


def test_listar_vencendo_em_filtra_st_consente_lembrete_no_sql() -> None:
    """O filtro de consentimento (D-L4) tem de estar no próprio SQL."""
    assert "ST_CONSENTE_LEMBRETE" in _SQL_LISTAR_ELEGIVEIS
    assert "= 'S'" in _SQL_LISTAR_ELEGIVEIS


def test_listar_vencendo_em_tutor_nulo_e_descartado_sem_crash() -> None:
    """Defesa em profundidade (achado LU-03): linha com ID_TUTOR nulo não pode
    derrubar o job com `int(None)` -- deve ser descartada, nunca propagar
    TypeError. Reproduz o cenário do ramo AGENDAMENTO sem tutor (que a view
    marca ST_CONSENTE_LEMBRETE='N' e o SQL já filtra fora -- este teste prova
    que, MESMO que uma linha destas escape do filtro, o código não quebra).
    """
    linha_tutor_nulo = _row_por_nome(ID_TUTOR=None, NM_TUTOR=None, DS_WHATSAPP=None)
    linha_valida = _row_por_nome(ID_PET=2, NM_TUTOR="Ana", ID_TUTOR=20)
    repo = VacinaRepository(pool=_make_pool([linha_tutor_nulo, linha_valida]))

    result = repo.listar_vencendo_em(dias=30)

    assert len(result) == 1
    assert result[0].id_pet == 2


def test_listar_vencendo_em_ds_whatsapp_nulo_preserva_none() -> None:
    """Tutor com consentimento mas sem WhatsApp cadastrado (coluna nullable
    em TUTOR) -- a linha é mantida (id_tutor válido), mas ds_whatsapp fica
    None em vez de virar a string "None"."""
    linha = _row_por_nome(DS_WHATSAPP=None)
    repo = VacinaRepository(pool=_make_pool([linha]))

    result = repo.listar_vencendo_em(dias=30)

    assert len(result) == 1
    assert result[0].ds_whatsapp is None


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


# --- contar_sem_consentimento ---

def _make_pool_contagem(valor: int) -> tuple[MagicMock, MagicMock]:
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (valor,)
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.get_connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)
    return mock_pool, mock_cursor


def test_contar_sem_consentimento_retorna_inteiro() -> None:
    pool, _ = _make_pool_contagem(2)
    repo = VacinaRepository(pool=pool)
    assert repo.contar_sem_consentimento(dias=7) == 2


def test_contar_sem_consentimento_usa_bind_variable() -> None:
    pool, mock_cursor = _make_pool_contagem(0)
    repo = VacinaRepository(pool=pool)
    repo.contar_sem_consentimento(dias=7)

    mock_cursor.execute.assert_called_once_with(_SQL_CONTAR_SEM_CONSENTIMENTO, {"dias": 7})


def test_contar_sem_consentimento_filtra_st_consente_lembrete_n_no_sql() -> None:
    assert "ST_CONSENTE_LEMBRETE" in _SQL_CONTAR_SEM_CONSENTIMENTO
    assert "= 'N'" in _SQL_CONTAR_SEM_CONSENTIMENTO
