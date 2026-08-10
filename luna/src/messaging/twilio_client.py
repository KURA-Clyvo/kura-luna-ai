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
            # LGPD (TASK-75): exc.msg é texto cru devolvido pela API do
            # Twilio e, para os códigos de número inválido/não-alcançável
            # (21211 "Invalid 'To' Phone Number", 21614 "'To' number is not
            # a valid mobile number", entre outros), embute o número de
            # telefone completo do destinatário na própria mensagem — ex.:
            # "Unable to create record: The 'To' number whatsapp:+55XXXXX
            # is not a valid phone number." (formato construído por
            # twilio.base.version.Version.exception, confirmado por
            # relatos reais equivalentes em outros SDKs oficiais do
            # Twilio, ex. twilio/twilio-php#399, twilio/twilio-node#528).
            # exc.msg NUNCA é repassado adiante — nem no MessagingError,
            # nem via `from exc` (que preservaria __cause__ e reimprimiria
            # a mensagem original em qualquer logger.exception/
            # traceback.format_exc() rio abaixo, mesmo problema já
            # corrigido na TASK-72 para o client da Luna).
            # exc.code/exc.status/exc.uri são seguros: o Twilio recebe o
            # destinatário no corpo do POST, não na URL (ver
            # twilio.http.http_client.TwilioHttpClient.request), então
            # exc.uri nunca carrega o telefone.
            raise MessagingError(
                f"Twilio REST error [{exc.code}] status={exc.status} uri={exc.uri}"
            ) from None
        except Exception as exc:
            raise MessagingError(f"Falha ao enviar WhatsApp: {exc}") from exc
