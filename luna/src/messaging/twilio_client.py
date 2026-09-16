"""Twilio WhatsApp gateway — Protocol + implementação concreta."""
import re
from typing import Protocol, runtime_checkable

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

# G2-1 (herdado da G2 do LU-09, ver lu-04-brief.md): a versão anterior desta
# função montava sempre `whatsapp:+55{para}` -- um número que já chegasse com
# DDI (`55...`, 12-13 dígitos, formato real medido em ~30% dos tutores no
# Oracle do compose) virava `+5555...`, que a Twilio recusa (502). Normalizado
# num único lugar (aqui), usado tanto por `/whatsapp/enviar` quanto pelo
# lembrete de vacina (LU-04) -- os dois únicos chamadores de `enviar_whatsapp`.
_APENAS_DIGITOS = re.compile(r"\D")


def normalizar_telefone_whatsapp(numero: str) -> str:
    """Normaliza um número de telefone brasileiro para o formato Twilio WhatsApp.

    Aceita, medidos como formatos reais coexistindo no Oracle do compose
    (`TUTOR.DS_TELEFONE`/`DS_WHATSAPP`, ver lu-04-brief.md):
      - já com prefixo ``whatsapp:`` -- devolvido sem alteração.
      - ``+55DDDNNNNNNNNN`` / ``55DDDNNNNNNNNN`` (12-13 dígitos, já com DDI).
      - nacional ``DDDNNNNNNNNN`` (10-11 dígitos, sem DDI) -- prefixado com 55.

    Qualquer outro formato levanta ``MessagingError`` **sem** o número na
    mensagem (LGPD) -- nunca deixa um número não reconhecido seguir para a
    Twilio silenciosamente malformado.
    """
    if numero.startswith("whatsapp:"):
        return numero

    digitos = _APENAS_DIGITOS.sub("", numero)

    if len(digitos) in (12, 13) and digitos.startswith("55"):
        return f"whatsapp:+{digitos}"
    if len(digitos) in (10, 11):
        return f"whatsapp:+55{digitos}"

    raise MessagingError(
        "Número de telefone em formato não reconhecido para envio WhatsApp",
        codigo="TELEFONE_FORMATO_INVALIDO",
    )


class MessagingError(Exception):
    """Levantado quando o envio via Twilio falha.

    ``codigo`` (LU-03) carrega só o código/tipo do erro — nunca texto livre —
    para que quem persiste a falha (``NOTIFICACAO.DS_ERRO_ENVIO``) monte
    "tipo + código" sem precisar reabrir ``str(exc)`` (que, na ausência
    completa deste atributo, seria a única fonte disponível e poderia um dia
    carregar texto não sanitizado de um chamador futuro).
    """

    def __init__(self, mensagem: str, codigo: str | int | None = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo


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
            para: número do destinatário -- aceita ``+55DDDNNNNNNNNN``,
                ``55DDDNNNNNNNNN``, nacional ``DDDNNNNNNNNN`` ou já com
                prefixo ``whatsapp:`` (ver `normalizar_telefone_whatsapp`).
            mensagem: corpo da mensagem.

        Raises:
            MessagingError: se o número estiver em formato não reconhecido,
                se o Twilio retornar erro ou se houver falha de rede.
        """
        to = normalizar_telefone_whatsapp(para)
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
                f"Twilio REST error [{exc.code}] status={exc.status} uri={exc.uri}",
                codigo=exc.code,
            ) from None
        except Exception as exc:
            raise MessagingError(
                f"Falha ao enviar WhatsApp: {exc}", codigo=type(exc).__name__
            ) from exc
