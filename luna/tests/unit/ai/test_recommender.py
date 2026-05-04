"""Tests for RecomendacaoCuidados."""
from unittest.mock import MagicMock

from src.ai.recommender import RecomendacaoCuidados
from src.db.models.raca import Raca


def _make_repo(raca: Raca | None) -> MagicMock:
    repo = MagicMock()
    repo.buscar_por_nome.return_value = raca
    return repo


def test_gerar_labrador_com_predisposicao() -> None:
    raca = Raca(id_raca=1, nm_raca="Labrador Retriever", id_especie=1,
                ds_predisposicao="displasia coxofemoral, obesidade")
    rec = RecomendacaoCuidados(raca_repo=_make_repo(raca))

    resultado = rec.gerar("Labrador Retriever")

    assert resultado is not None
    assert "Labrador Retriever" in resultado
    assert "displasia coxofemoral" in resultado
    assert "avaliação preventiva" in resultado


def test_gerar_raca_sem_predisposicao_retorna_none() -> None:
    raca = Raca(id_raca=2, nm_raca="SRD", id_especie=1, ds_predisposicao=None)
    rec = RecomendacaoCuidados(raca_repo=_make_repo(raca))

    resultado = rec.gerar("SRD")

    assert resultado is None


def test_gerar_raca_inexistente_retorna_none() -> None:
    rec = RecomendacaoCuidados(raca_repo=_make_repo(None))

    resultado = rec.gerar("Raça Fictícia")

    assert resultado is None


def test_gerar_golden_com_predisposicao() -> None:
    raca = Raca(id_raca=3, nm_raca="Golden Retriever", id_especie=1,
                ds_predisposicao="displasia de quadril, câncer")
    rec = RecomendacaoCuidados(raca_repo=_make_repo(raca))

    resultado = rec.gerar("Golden Retriever")

    assert resultado is not None
    assert "Golden Retriever" in resultado
    assert "câncer" in resultado


def test_gerar_repassa_nome_correto_ao_repo() -> None:
    repo = _make_repo(None)
    rec = RecomendacaoCuidados(raca_repo=repo)

    rec.gerar("Bulldog Francês")

    repo.buscar_por_nome.assert_called_once_with("Bulldog Francês")


def test_gerar_predisposicao_string_vazia_retorna_none() -> None:
    raca = Raca(id_raca=4, nm_raca="Vira-Lata", id_especie=1, ds_predisposicao="")
    rec = RecomendacaoCuidados(raca_repo=_make_repo(raca))

    resultado = rec.gerar("Vira-Lata")

    assert resultado is None
