"""Tests for TriageEngine — 100% coverage obrigatória."""
import pytest

from src.ai.triage_engine import TriageEngine, TriageResult, _normalize
from src.ai.triage_rules import TRIAGE_RULES_VERSION


@pytest.fixture
def engine() -> TriageEngine:
    return TriageEngine()


# ── normalização ──────────────────────────────────────────────────────────────

def test_normalize_remove_accents() -> None:
    assert _normalize("convulsão") == "convulsao"
    assert _normalize("dúvida") == "duvida"
    assert _normalize("náusea") == "nausea"
    assert _normalize("FEBRE") == "febre"


def test_normalize_acento_equivale_sem_acento(engine: TriageEngine) -> None:
    r_com = engine.classificar("meu cachorro teve convulsão")
    r_sem = engine.classificar("meu cachorro teve convulsao")
    assert r_com.urgencia == r_sem.urgencia == "ALTA"


# ── casos básicos ─────────────────────────────────────────────────────────────

def test_texto_vazio_retorna_baixa_score_zero(engine: TriageEngine) -> None:
    r = engine.classificar("")
    assert r.urgencia == "BAIXA"
    assert r.score == 0
    assert r.sintomas_detectados == []


def test_texto_espaco_retorna_baixa(engine: TriageEngine) -> None:
    r = engine.classificar("   ")
    assert r.urgencia == "BAIXA"
    assert r.score == 0


def test_texto_sem_sintomas_retorna_baixa(engine: TriageEngine) -> None:
    r = engine.classificar("olá boa tarde")
    assert r.urgencia == "BAIXA"
    assert r.score == 0


# ── ALTA urgência ─────────────────────────────────────────────────────────────

def test_convulsionando_retorna_alta(engine: TriageEngine) -> None:
    r = engine.classificar("meu cachorro está convulsionando")
    assert r.urgencia == "ALTA"
    assert r.score >= 10


def test_sangramento_retorna_alta(engine: TriageEngine) -> None:
    r = engine.classificar("ela está sangrando muito")
    assert r.urgencia == "ALTA"


def test_envenenamento_retorna_alta(engine: TriageEngine) -> None:
    r = engine.classificar("acho que meu gato foi envenenado")
    assert r.urgencia == "ALTA"


def test_atropelamento_retorna_alta(engine: TriageEngine) -> None:
    r = engine.classificar("meu pet foi atropelado")
    assert r.urgencia == "ALTA"


def test_dispneia_retorna_alta(engine: TriageEngine) -> None:
    r = engine.classificar("ela está ofegante e não respira bem")
    assert r.urgencia == "ALTA"


# ── MEDIA urgência ────────────────────────────────────────────────────────────

def test_vomitando_retorna_media(engine: TriageEngine) -> None:
    r = engine.classificar("meu cachorro está vomitando")
    assert r.urgencia == "MEDIA"
    assert r.score >= 3


def test_diarreia_retorna_media(engine: TriageEngine) -> None:
    r = engine.classificar("ele está com diarreia")
    assert r.urgencia == "MEDIA"


def test_sem_apetite_retorna_media(engine: TriageEngine) -> None:
    r = engine.classificar("meu pet não quer comer nada")
    assert r.urgencia == "MEDIA"


def test_febre_retorna_media(engine: TriageEngine) -> None:
    r = engine.classificar("acho que ele está com febre")
    assert r.urgencia == "MEDIA"


# ── BAIXA urgência ────────────────────────────────────────────────────────────

def test_duvida_retorna_baixa(engine: TriageEngine) -> None:
    r = engine.classificar("tenho uma dúvida sobre ração")
    assert r.urgencia == "BAIXA"
    assert r.score >= 1


def test_comportamento_retorna_baixa(engine: TriageEngine) -> None:
    r = engine.classificar("meu gato está latindo muito")
    assert r.urgencia == "BAIXA"


# ── hierarquia ────────────────────────────────────────────────────────────────

def test_alta_ganha_sobre_media_mesmo_texto(engine: TriageEngine) -> None:
    r = engine.classificar("está vomitando e convulsionando")
    assert r.urgencia == "ALTA"
    assert r.score >= 13  # 10 (ALTA) + 3 (MEDIA)


def test_media_ganha_sobre_baixa(engine: TriageEngine) -> None:
    r = engine.classificar("tenho uma dúvida mas ele está vomitando")
    assert r.urgencia == "MEDIA"


def test_score_acumula_todos_os_niveis(engine: TriageEngine) -> None:
    r = engine.classificar("convulsionando, vomitando e tenho dúvida")
    assert r.urgencia == "ALTA"
    assert r.score >= 14  # 10 + 3 + 1


# ── metadados do resultado ────────────────────────────────────────────────────

def test_result_contem_versao_regras(engine: TriageEngine) -> None:
    r = engine.classificar("convulsionando")
    assert r.regras_versao == TRIAGE_RULES_VERSION


def test_result_e_frozen(engine: TriageEngine) -> None:
    r = engine.classificar("vomitando")
    with pytest.raises(Exception):
        r.urgencia = "ALTA"  # type: ignore[misc]


def test_sintomas_detectados_nao_vazios_em_alta(engine: TriageEngine) -> None:
    r = engine.classificar("meu pet está sangrando")
    assert len(r.sintomas_detectados) > 0
