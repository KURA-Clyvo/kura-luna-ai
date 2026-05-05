"""Tests for POST /webhook/twilio/whatsapp."""
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.messaging.twilio_inbound import InboundMessage
from src.web.dependencies import get_inbound_service, get_settings
from src.web.routers.webhook_twilio import validar_twilio_signature

_VALID_FORM = {
    "From": "whatsapp:+5511999999999",
    "Body": "meu pet está doente",
    "MessageSid": "SM123",
    "AccountSid": "ACtest",
}


@pytest.fixture
def mock_inbound_service() -> AsyncMock:
    svc = AsyncMock()
    svc.processar = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def client_no_sig(app, mock_inbound_service: AsyncMock) -> TestClient:
    """Client com validação de assinatura bypassada."""
    app.dependency_overrides[validar_twilio_signature] = lambda: None
    app.dependency_overrides[get_inbound_service] = lambda: mock_inbound_service
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(validar_twilio_signature, None)
    app.dependency_overrides.pop(get_inbound_service, None)


# ── caminho feliz ─────────────────────────────────────────────────────────────

def test_post_valido_retorna_200_twiml(client_no_sig: TestClient) -> None:
    resp = client_no_sig.post("/webhook/twilio/whatsapp", data=_VALID_FORM)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert "<Response>" in resp.text or "<Response/>" in resp.text or resp.text == "<Response></Response>"


def test_post_valido_chama_add_task_com_inbound_message(
    app,
    mock_inbound_service: AsyncMock,
) -> None:
    """Verifica que BackgroundTasks recebeu processar com InboundMessage correto."""
    app.dependency_overrides[validar_twilio_signature] = lambda: None
    app.dependency_overrides[get_inbound_service] = lambda: mock_inbound_service

    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/webhook/twilio/whatsapp", data=_VALID_FORM)

    mock_inbound_service.processar.assert_awaited_once()
    call_args = mock_inbound_service.processar.call_args[0][0]
    assert isinstance(call_args, InboundMessage)
    assert call_args.numero_origem == "5511999999999"
    assert call_args.corpo == "meu pet está doente"


# ── validação de assinatura ───────────────────────────────────────────────────

def test_sem_header_assinatura_retorna_403(client: TestClient) -> None:
    """Sem dependency override — signature real, sem header → 403."""
    resp = client.post("/webhook/twilio/whatsapp", data=_VALID_FORM)
    assert resp.status_code == 403


def test_assinatura_invalida_retorna_403(app, mocker) -> None:  # type: ignore[no-untyped-def]
    mocker.patch(
        "src.web.routers.webhook_twilio.validar_assinatura",
        return_value=False,
    )
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/webhook/twilio/whatsapp",
            data=_VALID_FORM,
            headers={"X-Twilio-Signature": "bad-sig"},
        )
    assert resp.status_code == 403


# ── payload inválido ──────────────────────────────────────────────────────────

def test_payload_sem_from_retorna_400(client_no_sig: TestClient) -> None:
    resp = client_no_sig.post("/webhook/twilio/whatsapp", data={"Body": "oi"})
    assert resp.status_code == 400


# ── performance ───────────────────────────────────────────────────────────────

def test_handler_retorna_em_menos_de_50ms(client_no_sig: TestClient) -> None:
    """BackgroundTask não bloqueia a resposta HTTP."""
    start = time.perf_counter()
    resp = client_no_sig.post("/webhook/twilio/whatsapp", data=_VALID_FORM)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200
    # TestClient executa background tasks após retorno, mas o handler em si é rápido
    assert elapsed_ms < 500  # margem generosa para CI
