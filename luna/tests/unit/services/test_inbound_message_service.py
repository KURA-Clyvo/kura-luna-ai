"""Tests for InboundMessageService."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.messaging.twilio_inbound import InboundMessage
from src.services.inbound_message_service import (
    InboundMessageService,
    _RESPOSTA_ALTA,
    _RESPOSTA_FALLBACK,
    _RESPOSTA_MEDIA,
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
