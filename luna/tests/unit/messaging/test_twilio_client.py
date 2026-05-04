"""Tests for TwilioGateway and templates."""
from unittest.mock import MagicMock, patch

import pytest

from src.messaging.twilio_client import ITwilioGateway, MessagingError, TwilioGateway
from src.messaging.templates import lembrete_vacina, sugestao_cuidados_raca


# ---------------------------------------------------------------------------
# TwilioGateway
# ---------------------------------------------------------------------------

@patch("src.messaging.twilio_client.Client")
def test_enviar_whatsapp_retorna_sid(mock_client_cls: MagicMock) -> None:
    mock_msg = MagicMock()
    mock_msg.sid = "SM123abc"
    mock_client_cls.return_value.messages.create.return_value = mock_msg

    gw = TwilioGateway(account_sid="AC1", auth_token="tok", from_number="+14155238886")
    sid = gw.enviar_whatsapp(para="11999999999", mensagem="Olá!")

    assert sid == "SM123abc"


@patch("src.messaging.twilio_client.Client")
def test_enviar_whatsapp_formato_to(mock_client_cls: MagicMock) -> None:
    mock_msg = MagicMock()
    mock_msg.sid = "SM999"
    mock_client_cls.return_value.messages.create.return_value = mock_msg

    gw = TwilioGateway(account_sid="AC1", auth_token="tok", from_number="+14155238886")
    gw.enviar_whatsapp(para="11988887777", mensagem="Teste")

    call_kwargs = mock_client_cls.return_value.messages.create.call_args[1]
    assert call_kwargs["to"] == "whatsapp:+5511988887777"
    assert call_kwargs["from_"].startswith("whatsapp:")


@patch("src.messaging.twilio_client.Client")
def test_enviar_whatsapp_numero_ja_com_prefixo(mock_client_cls: MagicMock) -> None:
    mock_msg = MagicMock()
    mock_msg.sid = "SM1"
    mock_client_cls.return_value.messages.create.return_value = mock_msg

    gw = TwilioGateway(account_sid="AC1", auth_token="tok", from_number="+14155238886")
    gw.enviar_whatsapp(para="whatsapp:+5511999990000", mensagem="msg")

    call_kwargs = mock_client_cls.return_value.messages.create.call_args[1]
    assert call_kwargs["to"] == "whatsapp:+5511999990000"


@patch("src.messaging.twilio_client.Client")
def test_enviar_whatsapp_twilio_rest_exception_vira_messaging_error(
    mock_client_cls: MagicMock,
) -> None:
    from twilio.base.exceptions import TwilioRestException

    mock_client_cls.return_value.messages.create.side_effect = TwilioRestException(
        status=401, uri="/Messages", msg="Unauthorized", code=20003
    )

    gw = TwilioGateway(account_sid="AC1", auth_token="tok", from_number="+14155238886")
    with pytest.raises(MessagingError, match="Twilio REST error"):
        gw.enviar_whatsapp(para="11999999999", mensagem="msg")


@patch("src.messaging.twilio_client.Client")
def test_enviar_whatsapp_excecao_generica_vira_messaging_error(
    mock_client_cls: MagicMock,
) -> None:
    mock_client_cls.return_value.messages.create.side_effect = ConnectionError("timeout")

    gw = TwilioGateway(account_sid="AC1", auth_token="tok", from_number="+14155238886")
    with pytest.raises(MessagingError, match="Falha ao enviar WhatsApp"):
        gw.enviar_whatsapp(para="11999999999", mensagem="msg")


def test_twilio_gateway_implementa_protocolo() -> None:
    with patch("src.messaging.twilio_client.Client"):
        gw = TwilioGateway(account_sid="AC1", auth_token="tok", from_number="+14155238886")
    assert isinstance(gw, ITwilioGateway)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def test_lembrete_vacina_hoje() -> None:
    msg = lembrete_vacina("João", "Rex", "V10", 0, "Clyvo Vet")
    assert "hoje" in msg
    assert "Rex" in msg
    assert "V10" in msg


def test_lembrete_vacina_amanha() -> None:
    msg = lembrete_vacina("Ana", "Mel", "Raiva", 1, "Clyvo Vet")
    assert "amanhã" in msg


def test_lembrete_vacina_dias() -> None:
    msg = lembrete_vacina("Pedro", "Bob", "Giárdia", 7, "Clyvo Vet")
    assert "em 7 dias" in msg


def test_sugestao_cuidados_raca_contem_campos() -> None:
    msg = sugestao_cuidados_raca("João", "Rex", "Labrador", "displasia coxofemoral")
    assert "Labrador" in msg
    assert "displasia coxofemoral" in msg
    assert "Rex" in msg
    assert "João" in msg
