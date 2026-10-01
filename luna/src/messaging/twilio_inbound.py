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


def chave_telefone(numero: str) -> str:
    """Remove o prefixo ``whatsapp:`` e o ``+`` do E.164, sem tocar nos dígitos.

    Extraído de `parse_inbound_payload` (REC-16, G0 item 11): o `From` que o
    Twilio entrega ao webhook SEMPRE vem em E.164 (``whatsapp:+55...``), então
    esta função sozinha já produz a chave certa para `InboundMessage.
    numero_origem`.

    ⚠️ NÃO é ponto único de verdade sozinha para o lado do JOB de confirmação
    D-1 (achado D da G2, corrigido): `TUTOR.DS_WHATSAPP` pode vir em formato
    NACIONAL (``"11999999999"``, sem DDI -- formato legado medido de verdade
    no Oracle, ver comentário no topo de `twilio_client.py`), e esta função
    **não acrescenta DDI**. Quem for gravar uma chave a partir de
    `DS_WHATSAPP` (não a partir do `From` do webhook) precisa normalizar
    PRIMEIRO com `normalizar_telefone_whatsapp` (que acrescenta o DDI quando
    falta) e só depois chamar esta função -- ver
    `confirmacao_d1_service.py::_processar_candidato`, que é o único chamador
    desse caminho hoje. Chamar esta função sozinha sobre um número nacional
    produz uma chave que o webhook nunca vai bater.
    """
    return numero.removeprefix("whatsapp:").removeprefix("+")


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

    numero = chave_telefone(str(raw_from))

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
