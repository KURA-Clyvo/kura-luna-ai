"""Tests for LembreteVacinaService."""
from datetime import date
from unittest.mock import MagicMock, call, patch

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


def test_twilio_rest_exception_real_nao_vaza_telefone_em_notificacao() -> None:
    """TASK-75: os testes acima usam `MessagingError("timeout")` como
    dublê genérico de falha do Twilio — uma string sem telefone nenhum,
    que não prova nada sobre LGPD (mesma lacuna do `OSError` em
    `test_inbound_message_service.py`, achado da auditoria da TASK-75).
    Nenhum teste deste arquivo construía a exceção no formato real da
    API antes.

    Este teste usa uma `TwilioGateway` DE VERDADE (só `twilio.rest.Client`
    é mockado) disparando `TwilioRestException` no formato real do código
    21211 ("Invalid 'To' Phone Number"), que embute o telefone completo em
    `.msg` (ver `src/messaging/twilio_client.py:47-68` e
    `tests/unit/messaging/test_twilio_client.py`). Confirma que
    `NOTIFICACAO.DS_ERRO_ENVIO` (o `msg_erro` passado a
    `notif_repo.marcar_falha`) e `LOG_ERRO` (mensagem e stack trace via
    `LogErroRepository.from_exception`) nunca recebem o telefone do tutor.

    Prova de mordida: falha contra o `twilio_client.py` anterior à
    TASK-75 (telefone aparecia em `msg_erro` e no stack trace gravado em
    LOG_ERRO — `from exc` reimprime a TwilioRestException original via
    `traceback.format_exc()`), passa depois."""
    from twilio.base.exceptions import TwilioRestException

    from src.messaging.twilio_client import TwilioGateway

    numero = "11999999999"  # mesmo ds_whatsapp default de _vacina()
    vacinas = [_vacina(id_pet=1)]

    vacina_repo = MagicMock()
    vacina_repo.listar_vencendo_em.return_value = vacinas

    notif_repo = MagicMock()
    notif_repo.existe_pendente_para_vacina.return_value = False
    notif_repo.criar.return_value = 42

    log_repo = MagicMock()

    with patch("src.messaging.twilio_client.Client") as mock_client_cls:
        mock_client_cls.return_value.messages.create.side_effect = TwilioRestException(
            status=400,
            uri="/2010-04-01/Accounts/ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/Messages.json",
            msg=(
                "Unable to create record: The 'To' number whatsapp:+55"
                f"{numero} is not a valid phone number."
            ),
            code=21211,
            method="POST",
        )
        gateway = TwilioGateway(account_sid="AC1", auth_token="tok", from_number="+14155238886")
        svc = LembreteVacinaService(
            vacina_repo=vacina_repo,
            notificacao_repo=notif_repo,
            twilio_gateway=gateway,
            log_repo=log_repo,
        )

        resumo = svc.executar()

    assert resumo.falhas == 1
    assert resumo.enviadas == 0

    # NOTIFICACAO.DS_ERRO_ENVIO
    notif_repo.marcar_falha.assert_called_once()
    msg_erro = notif_repo.marcar_falha.call_args[1]["msg_erro"]
    assert numero not in msg_erro
    assert "not a valid phone number" not in msg_erro

    # LOG_ERRO (mensagem e stack trace)
    log_repo.registrar.assert_called_once()
    log_kwargs = log_repo.registrar.call_args[1]
    assert numero not in log_kwargs["mensagem"]
    assert "not a valid phone number" not in log_kwargs["mensagem"]
    stack_trace = log_kwargs.get("stack_trace") or ""
    assert numero not in stack_trace
    assert "not a valid phone number" not in stack_trace
