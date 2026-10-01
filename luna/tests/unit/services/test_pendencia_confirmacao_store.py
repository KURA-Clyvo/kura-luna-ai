"""Testes do PendenciaConfirmacaoStore (REC-16, G0 item 11)."""
from datetime import datetime, timedelta, timezone

from src.services.pendencia_confirmacao_store import (
    PendenciaConfirmacao,
    PendenciaConfirmacaoStore,
)


def _pendencia(id_agendamento: int = 1, id_tutor: int = 7, horas_validade: int = 36) -> PendenciaConfirmacao:
    return PendenciaConfirmacao(
        id_agendamento=id_agendamento,
        id_tutor=id_tutor,
        expira_em=datetime.now(tz=timezone.utc) + timedelta(hours=horas_validade),
    )


def test_registrar_e_buscar() -> None:
    store = PendenciaConfirmacaoStore()
    store.registrar("5511999999999", _pendencia())

    pendencia = store.buscar("5511999999999")

    assert pendencia is not None
    assert pendencia.id_agendamento == 1
    assert pendencia.id_tutor == 7


def test_buscar_telefone_ausente_devolve_none() -> None:
    store = PendenciaConfirmacaoStore()
    assert store.buscar("5511000000000") is None


def test_buscar_pendencia_expirada_devolve_none_e_remove() -> None:
    store = PendenciaConfirmacaoStore()
    store.registrar("5511999999999", _pendencia(horas_validade=-1))

    assert store.buscar("5511999999999") is None
    # limpeza preguiçosa: uma 2ª busca não acha nada de novo (já foi removida,
    # não é uma leitura idempotente por acaso).
    assert "5511999999999" not in store._por_telefone  # noqa: SLF001


def test_remover() -> None:
    store = PendenciaConfirmacaoStore()
    store.registrar("5511999999999", _pendencia())

    store.remover("5511999999999")

    assert store.buscar("5511999999999") is None


def test_remover_telefone_ausente_nao_levanta() -> None:
    store = PendenciaConfirmacaoStore()
    store.remover("5511000000000")  # não deve levantar


def test_registrar_substitui_pendencia_existente() -> None:
    store = PendenciaConfirmacaoStore()
    store.registrar("5511999999999", _pendencia(id_agendamento=1))
    store.registrar("5511999999999", _pendencia(id_agendamento=2))

    pendencia = store.buscar("5511999999999")

    assert pendencia is not None
    assert pendencia.id_agendamento == 2


def test_ja_processado_hoje_true_para_pendencia_ativa() -> None:
    store = PendenciaConfirmacaoStore()
    store.registrar("5511999999999", _pendencia(id_agendamento=42))

    assert store.ja_processado_hoje(42) is True


def test_ja_processado_hoje_false_para_id_diferente() -> None:
    store = PendenciaConfirmacaoStore()
    store.registrar("5511999999999", _pendencia(id_agendamento=42))

    assert store.ja_processado_hoje(43) is False


def test_ja_processado_hoje_false_para_pendencia_expirada() -> None:
    store = PendenciaConfirmacaoStore()
    store.registrar("5511999999999", _pendencia(id_agendamento=42, horas_validade=-1))

    assert store.ja_processado_hoje(42) is False


def test_ja_processado_hoje_store_vazio() -> None:
    store = PendenciaConfirmacaoStore()
    assert store.ja_processado_hoje(1) is False
