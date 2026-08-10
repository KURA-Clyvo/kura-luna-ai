"""Tests for InboundMessageService."""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.messaging.twilio_inbound import InboundMessage
from src.services.inbound_message_service import (
    _RESPOSTA_ALTA,
    _RESPOSTA_FALLBACK,
    _RESPOSTA_MEDIA,
    InboundMessageService,
)


def _make_msg(corpo: str = "oi", numero: str = "5511999999999") -> InboundMessage:
    return InboundMessage(
        numero_origem=numero,
        corpo=corpo,
        message_sid="SMtest",
        account_sid="ACtest",
    )


def _make_tutor(id_tutor: int = 1) -> MagicMock:
    tutor = MagicMock()
    tutor.id_tutor = id_tutor
    return tutor


@pytest.fixture
def kura_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def triage_engine() -> MagicMock:
    return MagicMock()


@pytest.fixture
def twilio_gateway() -> MagicMock:
    return MagicMock()


@pytest.fixture
def log_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(
    kura_client: AsyncMock,
    triage_engine: MagicMock,
    twilio_gateway: MagicMock,
    log_repo: MagicMock,
) -> InboundMessageService:
    return InboundMessageService(kura_client, triage_engine, twilio_gateway, log_repo)


# ── caminho feliz — tutor encontrado, ALTA ────────────────────────────────────

async def test_tutor_encontrado_alta_envia_resposta_urgente(
    service: InboundMessageService,
    kura_client: AsyncMock,
    triage_engine: MagicMock,
    twilio_gateway: MagicMock,
) -> None:
    tutor = _make_tutor(7)
    kura_client.buscar_tutor_por_telefone.return_value = tutor
    kura_client.registrar_interacao.return_value = 42
    kura_client.registrar_triagem.return_value = 99

    triage_result = MagicMock()
    triage_result.urgencia = "ALTA"
    triage_result.sintomas_detectados = ["convulsão"]
    triage_result.score = 10
    triage_engine.classificar.return_value = triage_result

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()) as mock_thread:
        result = await service.processar(_make_msg("convulsionando"))

    assert result.urgencia == "ALTA"
    assert result.resposta_enviada == _RESPOSTA_ALTA
    assert result.id_interacao == 42
    kura_client.registrar_triagem.assert_awaited_once()
    mock_thread.assert_awaited_once()


async def test_tutor_encontrado_media_envia_resposta_media(
    service: InboundMessageService,
    kura_client: AsyncMock,
    triage_engine: MagicMock,
) -> None:
    kura_client.buscar_tutor_por_telefone.return_value = _make_tutor()
    kura_client.registrar_interacao.return_value = 1
    kura_client.registrar_triagem.return_value = 1

    triage_result = MagicMock()
    triage_result.urgencia = "MEDIA"
    triage_result.sintomas_detectados = ["vomitando"]
    triage_result.score = 3
    triage_engine.classificar.return_value = triage_result

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg("vomitando"))

    assert result.resposta_enviada == _RESPOSTA_MEDIA


# ── tutor desconhecido ────────────────────────────────────────────────────────

async def test_tutor_nao_encontrado_registra_interacao_sem_tutor(
    service: InboundMessageService,
    kura_client: AsyncMock,
    triage_engine: MagicMock,
) -> None:
    kura_client.buscar_tutor_por_telefone.return_value = None
    kura_client.registrar_interacao.return_value = 5

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg("oi"))

    call_args = kura_client.registrar_interacao.call_args[0][0]
    assert call_args.id_tutor is None
    triage_engine.classificar.assert_not_called()
    kura_client.registrar_triagem.assert_not_awaited()
    assert result.resposta_enviada == _RESPOSTA_FALLBACK


# ── falhas de rede ────────────────────────────────────────────────────────────

async def test_timeout_em_busca_envia_fallback(
    service: InboundMessageService,
    kura_client: AsyncMock,
    log_repo: MagicMock,
) -> None:
    from src.integration.exceptions import KuraTimeoutError

    kura_client.buscar_tutor_por_telefone.side_effect = KuraTimeoutError()

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg())

    assert result.resposta_enviada == _RESPOSTA_FALLBACK
    log_repo.registrar.assert_called()


# ── LGPD — telefone nunca chega ao LOG_ERRO ───────────────────────────────────

async def test_excecao_generica_nao_grava_telefone_em_log_erro(
    service: InboundMessageService,
    kura_client: AsyncMock,
    log_repo: MagicMock,
) -> None:
    """TASK-35: parametros=msg.numero_origem violava LGPD (telefone cru em
    LOG_ERRO.DS_PARAMETROS). Confirma que o telefone completo nunca é
    passado ao LogErroRepository — inspeciona os argumentos da chamada
    mockada, não apenas o texto de log."""
    numero = "5511988887777"
    kura_client.buscar_tutor_por_telefone.side_effect = RuntimeError("crash")

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        await service.processar(_make_msg(numero=numero))

    log_repo.registrar.assert_called_once()
    _, kwargs = log_repo.registrar.call_args
    parametros = kwargs.get("parametros")

    assert parametros is not None
    assert numero not in parametros
    assert parametros == "message_sid=SMtest"


async def test_falha_em_registrar_triagem_nao_impede_resposta(
    service: InboundMessageService,
    kura_client: AsyncMock,
    triage_engine: MagicMock,
) -> None:
    kura_client.buscar_tutor_por_telefone.return_value = _make_tutor()
    kura_client.registrar_interacao.return_value = 1
    kura_client.registrar_triagem.side_effect = Exception("DB error")

    triage_result = MagicMock()
    triage_result.urgencia = "MEDIA"
    triage_result.sintomas_detectados = []
    triage_result.score = 3
    triage_engine.classificar.return_value = triage_result

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg("vomitando"))

    assert result.urgencia == "MEDIA"
    assert result.resposta_enviada == _RESPOSTA_MEDIA


# ── fallback final ────────────────────────────────────────────────────────────

async def test_excecao_generica_retorna_fallback(
    service: InboundMessageService,
    kura_client: AsyncMock,
) -> None:
    kura_client.buscar_tutor_por_telefone.side_effect = RuntimeError("crash")

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg())

    assert result.resposta_enviada == _RESPOSTA_FALLBACK
    assert result.id_interacao is None


async def test_fallback_twilio_falha_nao_propaga(
    service: InboundMessageService,
    kura_client: AsyncMock,
) -> None:
    kura_client.buscar_tutor_por_telefone.side_effect = RuntimeError("crash")

    async def twilio_erro(*_a, **_kw) -> None:
        raise OSError("Twilio offline")

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock(side_effect=twilio_erro)):
        result = await service.processar(_make_msg())

    assert result.resposta_enviada == _RESPOSTA_FALLBACK


async def test_fallback_twilio_falha_nao_loga_telefone_cru(
    kura_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """TASK-46 (versão original, SUBSTITUÍDA na TASK-75): `_enviar_fallback`
    logava o telefone cru via logger.error do log padrão da aplicação
    (destino diferente do LOG_ERRO/Oracle já corrigido na TASK-35, mesmo
    problema de LGPD).

    A versão original deste teste injetava `OSError("Twilio offline")` —
    uma string sem telefone nenhum — então `numero not in
    record.getMessage()` era vacuamente verdadeiro e nunca exercitou o
    caminho real (achado da auditoria da TASK-75). Este teste substitui o
    double genérico por uma `TwilioGateway` DE VERDADE (só
    `twilio.rest.Client`, a camada HTTP, é mockada) disparando
    `TwilioRestException` no formato real da API do Twilio para o código
    21211 ("Invalid 'To' Phone Number"), que embute o telefone completo
    em `.msg` (ver `src/messaging/twilio_client.py:47-68` e
    `tests/unit/messaging/test_twilio_client.py` para a evidência do
    formato do SDK).

    `inbound_message_service.py:139` (`logger.error("Falha ao enviar
    fallback message_sid=%s: %s", msg.message_sid, exc)`) loga o objeto
    `exc` inteiro com `%s` — a defesa contra vazamento tem que vir de
    `TwilioGateway` nunca produzir um `exc` com o telefone dentro, não
    deste logger.error. Prova de mordida: falha contra o
    `twilio_client.py` anterior à TASK-75, passa depois."""
    from twilio.base.exceptions import TwilioRestException

    from src.messaging.twilio_client import TwilioGateway

    numero = "5511988887777"
    kura_client.buscar_tutor_por_telefone.side_effect = RuntimeError("crash")

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
        real_service = InboundMessageService(
            kura_client=kura_client,
            triage_engine=MagicMock(),
            twilio_gateway=gateway,
            log_repo=MagicMock(),
        )

        with caplog.at_level(logging.ERROR):
            result = await real_service.processar(_make_msg(numero=numero))

    assert result.resposta_enviada == _RESPOSTA_FALLBACK
    assert numero not in caplog.text
    assert "not a valid phone number" not in caplog.text
    fallback_records = [
        record for record in caplog.records if "Falha ao enviar fallback" in record.getMessage()
    ]
    assert fallback_records, "esperava um log de falha ao enviar fallback"
    assert "message_sid=SMtest" in fallback_records[0].getMessage()
