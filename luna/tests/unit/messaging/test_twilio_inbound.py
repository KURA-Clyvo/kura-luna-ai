"""Tests for twilio_inbound — parse, validação e TwiML."""
import pytest

from src.messaging.twilio_inbound import (
    InboundMessage,
    montar_twiml_ack,
    parse_inbound_payload,
    validar_assinatura,
)


# ── parse_inbound_payload ─────────────────────────────────────────────────────

def test_parse_payload_valido() -> None:
    payload = {
        "From": "whatsapp:+5511999999999",
        "Body": "meu pet está doente",
        "MessageSid": "SMabc123",
        "AccountSid": "ACtest",
        "NumMedia": "0",
    }
    msg = parse_inbound_payload(payload)
    assert isinstance(msg, InboundMessage)
    assert msg.corpo == "meu pet está doente"
    assert msg.message_sid == "SMabc123"
    assert msg.num_media == 0


def test_parse_remove_prefixo_whatsapp() -> None:
    payload = {"From": "whatsapp:+5511988887777", "Body": "ok"}
    msg = parse_inbound_payload(payload)
    assert not msg.numero_origem.startswith("whatsapp:")
    assert not msg.numero_origem.startswith("+")
    assert msg.numero_origem == "5511988887777"


def test_parse_numero_sem_prefixo_whatsapp() -> None:
    payload = {"From": "+5511988887777", "Body": "ok"}
    msg = parse_inbound_payload(payload)
    assert msg.numero_origem == "5511988887777"


def test_parse_sem_from_levanta_value_error() -> None:
    with pytest.raises(ValueError, match="From"):
        parse_inbound_payload({"Body": "oi"})


def test_parse_sem_body_levanta_value_error() -> None:
    with pytest.raises(ValueError, match="Body"):
        parse_inbound_payload({"From": "whatsapp:+55"})


def test_parse_body_vazio_aceito() -> None:
    payload = {"From": "whatsapp:+5511", "Body": ""}
    msg = parse_inbound_payload(payload)
    assert msg.corpo == ""


def test_parse_num_media_default_zero() -> None:
    payload = {"From": "whatsapp:+5511", "Body": "teste"}
    msg = parse_inbound_payload(payload)
    assert msg.num_media == 0


def test_parse_num_media_presente() -> None:
    payload = {"From": "whatsapp:+5511", "Body": "foto", "NumMedia": "2"}
    msg = parse_inbound_payload(payload)
    assert msg.num_media == 2


def test_inbound_message_e_frozen() -> None:
    msg = InboundMessage(numero_origem="55", corpo="oi", message_sid="SM1", account_sid="AC1")
    with pytest.raises(Exception):
        msg.corpo = "alterado"  # type: ignore[misc]


# ── validar_assinatura ────────────────────────────────────────────────────────

def test_validar_assinatura_retorna_true(mocker) -> None:  # type: ignore[no-untyped-def]
    mock_validator = mocker.patch("src.messaging.twilio_inbound.RequestValidator")
    mock_validator.return_value.validate.return_value = True

    result = validar_assinatura("sig", "https://example.com/wh", {}, "token")
    assert result is True
    mock_validator.assert_called_once_with("token")


def test_validar_assinatura_retorna_false(mocker) -> None:  # type: ignore[no-untyped-def]
    mock_validator = mocker.patch("src.messaging.twilio_inbound.RequestValidator")
    mock_validator.return_value.validate.return_value = False

    result = validar_assinatura("bad-sig", "https://example.com/wh", {}, "token")
    assert result is False


def test_validar_assinatura_passa_params_corretos(mocker) -> None:  # type: ignore[no-untyped-def]
    mock_validator = mocker.patch("src.messaging.twilio_inbound.RequestValidator")
    mock_validator.return_value.validate.return_value = True

    params = {"From": "whatsapp:+55", "Body": "oi"}
    validar_assinatura("sig", "https://hooks.test/wh", params, "my-token")

    mock_validator.return_value.validate.assert_called_once_with(
        "https://hooks.test/wh", params, "sig"
    )


# ── montar_twiml_ack ──────────────────────────────────────────────────────────

def test_twiml_ack_conteudo() -> None:
    ack = montar_twiml_ack()
    assert ack == "<Response></Response>"


def test_twiml_ack_retorna_string() -> None:
    assert isinstance(montar_twiml_ack(), str)
