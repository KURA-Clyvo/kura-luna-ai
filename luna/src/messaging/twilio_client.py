"""Twilio WhatsApp gateway — Protocol + implementação concreta."""
from typing import Protocol, runtime_checkable

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client


class MessagingError(Exception):
    """Levantado quando o envio via Twilio falha."""


@runtime_checkable
class ITwilioGateway(Protocol):
    """Interface de envio de mensagens WhatsApp."""

    def enviar_whatsapp(self, para: str, mensagem: str) -> str:
        """Envia mensagem e retorna o SID da mensagem criada."""
        ...


class TwilioGateway:
    """Implementação concreta do ITwilioGateway usando twilio.rest.Client."""

    def __init__(self, account_sid: str, auth_token: str, from_number: str) -> None:
        self._client = Client(account_sid, auth_token)
        self._from = f"whatsapp:{from_number}"

    def enviar_whatsapp(self, para: str, mensagem: str) -> str:
        """Envia mensagem WhatsApp e retorna o SID.

        Args:
            para: número do destinatário no formato '55119XXXXXXXX' (sem whatsapp:).
            mensagem: corpo da mensagem.

        Raises:
            MessagingError: se o Twilio retornar erro ou houver falha de rede.
        """
        to = f"whatsapp:+55{para}" if not para.startswith("whatsapp:") else para
        try:
            message = self._client.messages.create(
                body=mensagem,
                from_=self._from,
                to=to,
            )
            return str(message.sid)
        except TwilioRestException as exc:
            raise MessagingError(f"Twilio REST error [{exc.code}]: {exc.msg}") from exc
        except Exception as exc:
            raise MessagingError(f"Falha ao enviar WhatsApp: {exc}") from exc
