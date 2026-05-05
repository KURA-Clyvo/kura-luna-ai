"""Parse de payload inbound do Twilio, validação de assinatura e TwiML ack."""
from dataclasses import dataclass

from twilio.request_validator import RequestValidator


@dataclass(frozen=True)
class InboundMessage:
    """Mensagem WhatsApp recebida do Twilio."""

    numero_origem: str
    corpo: str
    message_sid: str
    account_sid: str
    num_media: int = 0


def parse_inbound_payload(form_data: dict) -> InboundMessage:  # type: ignore[type-arg]
    """Extrai os campos relevantes do payload form-encoded do Twilio.

    Raises:
        ValueError: se 'From' ou 'Body' estiverem ausentes.
    """
    raw_from = form_data.get("From")
    body = form_data.get("Body")

    if not raw_from:
        raise ValueError("Campo 'From' ausente no payload Twilio")
    if body is None:
        raise ValueError("Campo 'Body' ausente no payload Twilio")

    numero = str(raw_from).removeprefix("whatsapp:").removeprefix("+")

    return InboundMessage(
        numero_origem=numero,
        corpo=str(body),
        message_sid=str(form_data.get("MessageSid", "")),
        account_sid=str(form_data.get("AccountSid", "")),
        num_media=int(form_data.get("NumMedia", 0)),
    )


def validar_assinatura(signature: str, url: str, params: dict, auth_token: str) -> bool:  # type: ignore[type-arg]
    """Valida a assinatura X-Twilio-Signature usando RequestValidator do Twilio.

    Returns:
        True se a assinatura for válida; False caso contrário.
    """
    validator = RequestValidator(auth_token)
    return bool(validator.validate(url, params, signature))


def montar_twiml_ack() -> str:
    """Retorna TwiML vazio para acusar recebimento ao Twilio sem enviar resposta ao usuário."""
    return "<Response></Response>"
