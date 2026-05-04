"""Tests for dataclass models."""
from dataclasses import FrozenInstanceError
from datetime import date, datetime

import pytest

from src.db.models.vacina_vencendo import VacinaVencendo
from src.db.models.notificacao import Notificacao
from src.db.models.raca import Raca


# --- VacinaVencendo ---

def test_vacina_vencendo_instantiation() -> None:
    v = VacinaVencendo(
        id_pet=1,
        nm_pet="Rex",
        id_tutor=10,
        nm_tutor="João",
        ds_whatsapp="11999999999",
        nm_vacina="V10",
        dt_proxima_dose=date(2026, 6, 1),
        dias_restantes=28,
        nm_clinica="Clyvo Vet",
    )
    assert v.id_pet == 1
    assert v.nm_vacina == "V10"
    assert v.dias_restantes == 28


def test_vacina_vencendo_is_frozen() -> None:
    v = VacinaVencendo(
        id_pet=1, nm_pet="Rex", id_tutor=10, nm_tutor="João",
        ds_whatsapp="11999999999", nm_vacina="V10",
        dt_proxima_dose=date(2026, 6, 1), dias_restantes=28, nm_clinica="C",
    )
    with pytest.raises(FrozenInstanceError):
        v.nm_pet = "Buddy"  # type: ignore[misc]


# --- Notificacao ---

def test_notificacao_instantiation_required_fields() -> None:
    n = Notificacao(
        id_tutor=5,
        ds_canal="WHATSAPP",
        ds_tipo="LEMBRETE_VACINA",
        ds_titulo="Lembrete",
        ds_mensagem="Sua vacina vence em breve.",
        dt_agendada=datetime(2026, 5, 10, 8, 0),
        st_status="PENDENTE",
    )
    assert n.id_notificacao is None
    assert n.id_pet is None
    assert n.ds_canal == "WHATSAPP"


def test_notificacao_optional_fields() -> None:
    n = Notificacao(
        id_tutor=5,
        ds_canal="WHATSAPP",
        ds_tipo="LEMBRETE_VACINA",
        ds_titulo="Lembrete",
        ds_mensagem="Msg",
        dt_agendada=datetime(2026, 5, 10),
        st_status="ENVIADA",
        id_notificacao=42,
        id_pet=7,
        dt_enviada=datetime(2026, 5, 10, 8, 1),
    )
    assert n.id_notificacao == 42
    assert n.id_pet == 7


def test_notificacao_is_frozen() -> None:
    n = Notificacao(
        id_tutor=1, ds_canal="WHATSAPP", ds_tipo="LEMBRETE_VACINA",
        ds_titulo="T", ds_mensagem="M",
        dt_agendada=datetime(2026, 5, 1), st_status="PENDENTE",
    )
    with pytest.raises(FrozenInstanceError):
        n.st_status = "ENVIADA"  # type: ignore[misc]


# --- Raca ---

def test_raca_instantiation_with_predisposicao() -> None:
    r = Raca(id_raca=1, nm_raca="Labrador", id_especie=1, ds_predisposicao="displasia coxofemoral")
    assert r.ds_predisposicao == "displasia coxofemoral"


def test_raca_instantiation_without_predisposicao() -> None:
    r = Raca(id_raca=2, nm_raca="SRD", id_especie=1)
    assert r.ds_predisposicao is None


def test_raca_is_frozen() -> None:
    r = Raca(id_raca=1, nm_raca="Labrador", id_especie=1)
    with pytest.raises(FrozenInstanceError):
        r.nm_raca = "Poodle"  # type: ignore[misc]
