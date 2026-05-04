"""Tests for LembreteVacinaService."""
from datetime import date
from unittest.mock import MagicMock, call

import pytest

from src.db.models.vacina_vencendo import VacinaVencendo
from src.messaging.twilio_client import MessagingError
from src.services.notification_service import LembreteVacinaService, ResumoExecucao


def _vacina(
    id_pet: int = 1,
    nm_vacina: str = "V10",
    dias: int = 5,
    id_tutor: int = 10,
) -> VacinaVencendo:
    return VacinaVencendo(
        id_pet=id_pet,
        nm_pet="Rex",
        id_tutor=id_tutor,
        nm_tutor="João",
        ds_whatsapp="11999999999",
        nm_vacina=nm_vacina,
        dt_proxima_dose=date(2026, 6, 1),
        dias_restantes=dias,
        nm_clinica="Clyvo Vet",
    )


def _make_service(
    vacinas: list[VacinaVencendo] | None = None,
    ja_enviada: bool = False,
    twilio_side_effect: object = None,
    criar_side_effect: object = None,
) -> tuple[LembreteVacinaService, MagicMock, MagicMock, MagicMock, MagicMock]:
    if vacinas is None:
        vacinas = []
    vacina_repo = MagicMock()
    vacina_repo.listar_vencendo_em.return_value = vacinas

    notif_repo = MagicMock()
    notif_repo.existe_pendente_para_vacina.return_value = ja_enviada
    notif_repo.criar.return_value = 42
    if criar_side_effect:
        notif_repo.criar.side_effect = criar_side_effect

    twilio = MagicMock()
    if twilio_side_effect:
        twilio.enviar_whatsapp.side_effect = twilio_side_effect

    log_repo = MagicMock()

    svc = LembreteVacinaService(
        vacina_repo=vacina_repo,
        notificacao_repo=notif_repo,
        twilio_gateway=twilio,
        log_repo=log_repo,
    )
    return svc, vacina_repo, notif_repo, twilio, log_repo


def test_lote_vazio_retorna_resumo_zerado() -> None:
    svc, *_ = _make_service(vacinas=[])
    resumo = svc.executar()
    assert resumo == ResumoExecucao(total=0, enviadas=0, falhas=0, ja_enviadas=0)


def test_tres_vacinas_uma_ja_enviada() -> None:
    vacinas = [_vacina(id_pet=1), _vacina(id_pet=2), _vacina(id_pet=3)]
    svc, _, notif_repo, *_ = _make_service(vacinas=vacinas)
    # Só a primeira já foi enviada
    notif_repo.existe_pendente_para_vacina.side_effect = [True, False, False]

    resumo = svc.executar()

    assert resumo.total == 3
    assert resumo.ja_enviadas == 1
    assert resumo.enviadas == 2
    assert resumo.falhas == 0


def test_twilio_explode_no_segundo_item() -> None:
    vacinas = [_vacina(id_pet=1), _vacina(id_pet=2), _vacina(id_pet=3)]
    svc, _, notif_repo, twilio, log_repo = _make_service(vacinas=vacinas)
    notif_repo.existe_pendente_para_vacina.return_value = False
    twilio.enviar_whatsapp.side_effect = [
        "SM001",
        MessagingError("timeout"),
        "SM003",
    ]

    resumo = svc.executar()

    assert resumo.total == 3
    assert resumo.enviadas == 2
    assert resumo.falhas == 1
    assert resumo.ja_enviadas == 0
    notif_repo.marcar_falha.assert_called_once()
    notif_repo.marcar_enviada.call_count == 2


def test_oracle_explode_no_criar_registra_em_log_e_continua() -> None:
    vacinas = [_vacina(id_pet=1), _vacina(id_pet=2)]
    svc, _, notif_repo, twilio, log_repo = _make_service(vacinas=vacinas)
    notif_repo.existe_pendente_para_vacina.return_value = False
    notif_repo.criar.side_effect = [Exception("ORA-00001"), 99]

    resumo = svc.executar()

    assert resumo.total == 2
    assert resumo.falhas == 1
    assert resumo.enviadas == 1
    log_repo.registrar.assert_called()


def test_marcar_enviada_chamada_com_id_correto() -> None:
    svc, _, notif_repo, twilio, _ = _make_service(vacinas=[_vacina()])
    notif_repo.existe_pendente_para_vacina.return_value = False
    notif_repo.criar.return_value = 77
    twilio.enviar_whatsapp.return_value = "SM_OK"

    svc.executar()

    notif_repo.marcar_enviada.assert_called_once()
    args = notif_repo.marcar_enviada.call_args[1]
    assert args["id_notificacao"] == 77


def test_idempotencia_total_nao_chama_twilio() -> None:
    vacinas = [_vacina(id_pet=1), _vacina(id_pet=2)]
    svc, _, notif_repo, twilio, _ = _make_service(vacinas=vacinas, ja_enviada=True)

    resumo = svc.executar()

    twilio.enviar_whatsapp.assert_not_called()
    assert resumo.ja_enviadas == 2
    assert resumo.enviadas == 0
