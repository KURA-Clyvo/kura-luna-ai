"""Testes unitários para POST /whatsapp/enviar.

Cobre: sucesso, 401 (key ausente / inválida), 502 (MessagingError),
e conformidade LGPD (sem PII nos logs).
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.messaging.twilio_client import ITwilioGateway, MessagingError
from src.web.app import create_app
from src.web.dependencies import get_settings, get_twilio_gateway

_CHAVE_VALIDA = "chave-inbound-teste"

_PAYLOAD = {"para": "11999999999", "mensagem": "Consulta confirmada para amanhã."}


def _settings_com_chave(chave: str = _CHAVE_VALIDA) -> Settings:
    return Settings(
        ORACLE_DSN="test:1521/TEST",
        ORACLE_USER="test",
        ORACLE_PASSWORD="test",
        TWILIO_SID="ACtest",
        TWILIO_TOKEN="test_token",
        TWILIO_FROM_NUMBER="+14155238886",
        YOLO_WEIGHTS_PATH="test.pt",
        BREED_CLASSIFIER_WEIGHTS_PATH="test.pth",
        KURA_API_BASE_URL="http://kura-test.local",
        KURA_API_KEY="test-key",
        WEBHOOK_PUBLIC_URL="https://test.ngrok.io/webhook/twilio/whatsapp",
        LUNA_INBOUND_API_KEY=chave,
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def mock_twilio_gw() -> MagicMock:
    gw = MagicMock(spec=ITwilioGateway)
    gw.enviar_whatsapp = MagicMock(return_value="SM_unit_test_001")
    return gw


@pytest.fixture
def whatsapp_client(mock_twilio_gw: MagicMock) -> TestClient:
    settings = _settings_com_chave()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_twilio_gateway] = lambda: mock_twilio_gw
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── Sucesso ───────────────────────────────────────────────────────────────────

def test_enviar_whatsapp_sucesso_retorna_200(
    whatsapp_client: TestClient, mock_twilio_gw: MagicMock
) -> None:
    resp = whatsapp_client.post(
        "/whatsapp/enviar",
        json=_PAYLOAD,
        headers={"X-API-Key": _CHAVE_VALIDA},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "enviado"
    assert data["sid"] == "SM_unit_test_001"


def test_enviar_whatsapp_chama_gateway_com_argumentos_corretos(
    whatsapp_client: TestClient, mock_twilio_gw: MagicMock
) -> None:
    whatsapp_client.post(
        "/whatsapp/enviar",
        json=_PAYLOAD,
        headers={"X-API-Key": _CHAVE_VALIDA},
    )
    mock_twilio_gw.enviar_whatsapp.assert_called_once_with(
        _PAYLOAD["para"], _PAYLOAD["mensagem"]
    )


# ── Auth 401 ──────────────────────────────────────────────────────────────────

def test_enviar_whatsapp_sem_api_key_retorna_401(
    whatsapp_client: TestClient,
) -> None:
    resp = whatsapp_client.post("/whatsapp/enviar", json=_PAYLOAD)
    assert resp.status_code == 401


def test_enviar_whatsapp_api_key_invalida_retorna_401(
    whatsapp_client: TestClient,
) -> None:
    resp = whatsapp_client.post(
        "/whatsapp/enviar",
        json=_PAYLOAD,
        headers={"X-API-Key": "chave-errada"},
    )
    assert resp.status_code == 401


def test_enviar_whatsapp_chave_vazia_retorna_401(
    whatsapp_client: TestClient,
) -> None:
    resp = whatsapp_client.post(
        "/whatsapp/enviar",
        json=_PAYLOAD,
        headers={"X-API-Key": ""},
    )
    assert resp.status_code == 401


# ── 502 MessagingError ────────────────────────────────────────────────────────

def test_enviar_whatsapp_twilio_falha_retorna_502(
    mock_twilio_gw: MagicMock,
) -> None:
    mock_twilio_gw.enviar_whatsapp.side_effect = MessagingError("Twilio REST error [20003]: auth")

    settings = _settings_com_chave()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_twilio_gateway] = lambda: mock_twilio_gw

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/whatsapp/enviar",
            json=_PAYLOAD,
            headers={"X-API-Key": _CHAVE_VALIDA},
        )

    assert resp.status_code == 502
    assert "Twilio" in resp.json()["detail"]


# ── 503 — credencial Twilio ausente/inválida (LU-16 G4, achado A3) ─────────────

def _settings_sem_twilio() -> Settings:
    return Settings(
        ORACLE_DSN="test:1521/TEST",
        ORACLE_USER="test",
        ORACLE_PASSWORD="test",
        TWILIO_SID="",
        TWILIO_TOKEN="",
        TWILIO_FROM_NUMBER="",
        YOLO_WEIGHTS_PATH="test.pt",
        BREED_CLASSIFIER_WEIGHTS_PATH="test.pth",
        KURA_API_BASE_URL="http://kura-test.local",
        KURA_API_KEY="test-key",
        WEBHOOK_PUBLIC_URL="https://test.ngrok.io/webhook/twilio/whatsapp",
        LUNA_INBOUND_API_KEY=_CHAVE_VALIDA,
        _env_file=None,  # type: ignore[call-arg]
    )


def test_enviar_whatsapp_credencial_ausente_retorna_503_nao_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LU-16 G4 (achado A3, Important): antes deste fix, `TwilioGateway.__init__`
    levantava `TwilioException` DENTRO da resolução de `get_twilio_gateway`
    (dependência REAL, não substituída neste teste) — antes do handler rodar, então
    o `try/except MessagingError` do próprio endpoint nunca via a exceção, e ela
    escapava como 500 cru (`{"error":"internal server error"}`, medido pelo G4).
    A dependência irmã `get_lembrete_service` (jobs router) já tratava a mesma
    exceção com 503 declarado — mesmo padrão aqui, medido lado a lado no G4."""
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)

    settings_sem_twilio = _settings_sem_twilio()
    app = create_app(settings_sem_twilio)
    app.dependency_overrides[get_settings] = lambda: settings_sem_twilio
    # get_twilio_gateway NÃO é substituído — é o código de produção de verdade.

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/whatsapp/enviar",
            json=_PAYLOAD,
            headers={"X-API-Key": _CHAVE_VALIDA},
        )

    assert resp.status_code == 503
    assert resp.status_code != 500
    detail = resp.json()["detail"].lower()
    assert "credencial" in detail or "mensageria" in detail


def test_enviar_whatsapp_credencial_ausente_logs_sem_pii(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """LGPD, mesmo caminho de falha: nem SID/token (que nem existem aqui — estão
    vazios) nem o telefone/mensagem do payload podem aparecer no log do 503."""
    import logging

    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)

    settings_sem_twilio = _settings_sem_twilio()
    app = create_app(settings_sem_twilio)
    app.dependency_overrides[get_settings] = lambda: settings_sem_twilio

    with caplog.at_level(logging.WARNING):
        with TestClient(app, raise_server_exceptions=False) as c:
            c.post(
                "/whatsapp/enviar",
                json=_PAYLOAD,
                headers={"X-API-Key": _CHAVE_VALIDA},
            )

    log_text = " ".join(caplog.messages)
    assert _PAYLOAD["mensagem"] not in log_text
    assert _PAYLOAD["para"] not in log_text


# ── LGPD — sem PII nos logs ───────────────────────────────────────────────────

def test_enviar_whatsapp_logs_sem_conteudo_mensagem(
    whatsapp_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    with caplog.at_level(logging.INFO, logger="src.web.routers.whatsapp"):
        whatsapp_client.post(
            "/whatsapp/enviar",
            json=_PAYLOAD,
            headers={"X-API-Key": _CHAVE_VALIDA},
        )

    log_text = " ".join(caplog.messages)
    assert _PAYLOAD["mensagem"] not in log_text, "LGPD: conteúdo da mensagem não pode aparecer no log"
    assert _PAYLOAD["para"] not in log_text, "LGPD: número de telefone não pode aparecer no log"


def test_enviar_whatsapp_logs_sem_pii_em_erro_502(
    mock_twilio_gw: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    mock_twilio_gw.enviar_whatsapp.side_effect = MessagingError("err")

    settings = _settings_com_chave()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_twilio_gateway] = lambda: mock_twilio_gw

    with caplog.at_level(logging.ERROR, logger="src.web.routers.whatsapp"):
        with TestClient(app, raise_server_exceptions=False) as c:
            c.post(
                "/whatsapp/enviar",
                json=_PAYLOAD,
                headers={"X-API-Key": _CHAVE_VALIDA},
            )

    log_text = " ".join(caplog.messages)
    assert _PAYLOAD["mensagem"] not in log_text, "LGPD: mensagem não pode aparecer em log de erro"
    assert _PAYLOAD["para"] not in log_text, "LGPD: telefone não pode aparecer em log de erro"


# ── Gateway via dependency_overrides (não instancia Client direto) ─────────────

def test_endpoint_usa_gateway_injetado_nao_instancia_client_direto(
    whatsapp_client: TestClient, mock_twilio_gw: MagicMock
) -> None:
    """O endpoint deve delegar ao ITwilioGateway injetado — nunca a twilio.rest.Client."""
    from unittest.mock import patch

    with patch("src.messaging.twilio_client.Client") as mock_client_cls:
        whatsapp_client.post(
            "/whatsapp/enviar",
            json=_PAYLOAD,
            headers={"X-API-Key": _CHAVE_VALIDA},
        )
        mock_client_cls.assert_not_called()

    mock_twilio_gw.enviar_whatsapp.assert_called_once()
