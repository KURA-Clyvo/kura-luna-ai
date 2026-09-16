"""Tests for TwilioGateway and templates."""
import traceback
from unittest.mock import MagicMock, patch

import pytest

from src.messaging.templates import lembrete_vacina, sugestao_cuidados_raca
from src.messaging.twilio_client import (
    ITwilioGateway,
    MessagingError,
    TwilioGateway,
    normalizar_telefone_whatsapp,
)

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
def test_enviar_whatsapp_twilio_rest_exception_numero_invalido_nao_vaza_telefone(
    mock_client_cls: MagicMock,
) -> None:
    """TASK-75: reproduz o formato REAL de erro que a API do Twilio devolve
    para o código 21211 ("Invalid 'To' Phone Number") — confirmado contra
    `twilio.base.version.Version.exception` (installed: twilio==9.3.2,
    "Unable to create record: {message}") e contra relatos reais
    equivalentes de outros SDKs oficiais do Twilio (twilio/twilio-php#399:
    "The 'To' number phone=+35193XXXXXXX is not a valid phone number";
    twilio/twilio-node#528: "Unable to create record: The From phone
    number +919710000000 is not a valid..."). Nenhum teste deste arquivo
    construía a exceção nesse formato antes — os anteriores usavam
    msg="Unauthorized" (sem PII), o que não provava nada sobre o
    vazamento real.

    Prova de mordida: falha contra twilio_client.py anterior à TASK-75
    (telefone aparecia em str(MessagingError) e na cadeia de causa —
    `from exc` reimprime a TwilioRestException original via
    traceback.format_exception), passa depois."""
    from twilio.base.exceptions import TwilioRestException

    numero = "5511988887777"
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

    gw = TwilioGateway(account_sid="AC1", auth_token="tok", from_number="+14155238886")

    with pytest.raises(MessagingError) as exc_info:
        gw.enviar_whatsapp(para=numero, mensagem="msg")

    raised = exc_info.value

    # 1) a mensagem sanitizada não contém o telefone.
    assert numero not in str(raised)
    assert "not a valid phone number" not in str(raised)

    # 2) `from None` foi usado — não `from exc` — então __cause__ está
    #    suprimido e nenhum logger.exception()/traceback.format_exc() rio
    #    abaixo consegue reimprimir a TwilioRestException original.
    assert raised.__cause__ is None
    assert raised.__suppress_context__ is True

    formatted = "".join(
        traceback.format_exception(type(raised), raised, raised.__traceback__)
    )
    assert numero not in formatted
    assert "not a valid phone number" not in formatted

    # 3) diagnóstico ainda disponível de forma segura: código/status/uri
    #    (uri nunca carrega o telefone — vai no corpo do POST, não na URL).
    assert "21211" in str(raised)
    assert "400" in str(raised)


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
# normalizar_telefone_whatsapp (G2-1, herdado da G2 do LU-09)
#
# Medido no Oracle do compose (lu-04-brief.md, 15/09): TUTOR.DS_TELEFONE tem
# os DOIS formatos coexistindo -- 7/10 tutores em nacional (11 dígitos,
# DDD9XXXXXXXX) e 3/10 já com DDI (13 dígitos, começando com 55). A versão
# anterior de `enviar_whatsapp` só acertava o primeiro formato.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        # nacional, 11 dígitos (sem DDI) -- formato real medido (7/10 tutores)
        ("11988887777", "whatsapp:+5511988887777"),
        # nacional, 10 dígitos (fixo, sem 9) -- também aceito
        ("1133334444", "whatsapp:+551133334444"),
        # já com DDI, 13 dígitos (formato real medido, 3/10 tutores) -- SEM "+"
        ("5511988887777", "whatsapp:+5511988887777"),
        # já com DDI e "+", 13 dígitos
        ("+5511988887777", "whatsapp:+5511988887777"),
        # já com DDI, 12 dígitos (fixo)
        ("551133334444", "whatsapp:+551133334444"),
        # já com prefixo whatsapp: -- devolvido sem alteração
        ("whatsapp:+5511999990000", "whatsapp:+5511999990000"),
    ],
)
def test_normalizar_telefone_whatsapp_formatos_validos(entrada: str, esperado: str) -> None:
    assert normalizar_telefone_whatsapp(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "123",  # curto demais
        "999999999999999",  # longo demais (15 dígitos)
        "",  # vazio
        "abc-nao-e-numero",  # não numérico
    ],
)
def test_normalizar_telefone_whatsapp_formato_invalido_levanta_sem_vazar_numero(
    entrada: str,
) -> None:
    with pytest.raises(MessagingError) as exc_info:
        normalizar_telefone_whatsapp(entrada)
    # LGPD: o número (quando não vazio) nunca aparece na mensagem da exceção.
    if entrada:
        assert entrada not in str(exc_info.value)


@patch("src.messaging.twilio_client.Client")
def test_enviar_whatsapp_numero_com_ddi_gera_to_correto_sem_duplicar_55(
    mock_client_cls: MagicMock,
) -> None:
    """Mordida do G2-1: reverter `enviar_whatsapp` para `f"whatsapp:+55{para}"`
    faz este caso falhar (produziria `whatsapp:+555511988887777`, com "55"
    duplicado) -- o formato real medido no Oracle do compose para 3/10
    tutores (`DS_TELEFONE` de 13 dígitos, já começando com "55")."""
    mock_msg = MagicMock()
    mock_msg.sid = "SM_DDI"
    mock_client_cls.return_value.messages.create.return_value = mock_msg

    gw = TwilioGateway(account_sid="AC1", auth_token="tok", from_number="+14155238886")
    gw.enviar_whatsapp(para="5511988887777", mensagem="Teste DDI")

    call_kwargs = mock_client_cls.return_value.messages.create.call_args[1]
    assert call_kwargs["to"] == "whatsapp:+5511988887777"


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
