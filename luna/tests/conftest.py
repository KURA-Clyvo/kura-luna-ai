"""Global pytest fixtures."""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from src.config.settings import Settings


@pytest.fixture
def mock_pool() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_twilio() -> MagicMock:
    return MagicMock()


# ── v2.0 E2E fixtures ─────────────────────────────────────────────────────────

def _e2e_settings() -> Settings:
    return Settings(
        ORACLE_DSN="test:1521/TEST",
        ORACLE_USER="test",
        ORACLE_PASSWORD="test",
        TWILIO_SID="ACtest",
        TWILIO_TOKEN="test_token",
        TWILIO_FROM_NUMBER="+14155238886",
        YOLO_WEIGHTS_PATH="test.pt",
        BREED_CLASSIFIER_WEIGHTS_PATH="test.pth",
        KURA_API_BASE_URL="http://kura-e2e.local",
        KURA_API_KEY="e2e-key",
        WEBHOOK_PUBLIC_URL="https://e2e.ngrok.io/webhook/twilio/whatsapp",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def e2e_settings() -> Settings:
    return _e2e_settings()


@pytest.fixture
def e2e_http_client() -> httpx.AsyncClient:
    """AsyncClient bare para KuraClient nos testes E2E (respx intercepta)."""
    return httpx.AsyncClient()


@pytest.fixture
def mock_twilio_gateway() -> MagicMock:
    gw = MagicMock()
    gw.enviar_whatsapp = MagicMock(return_value="SM_e2e_test")
    return gw


@pytest.fixture
def mock_log_repo_e2e() -> MagicMock:
    repo = MagicMock()
    repo.registrar = MagicMock()
    return repo


@pytest.fixture
def e2e_app(
    e2e_settings: Settings,
    e2e_http_client: httpx.AsyncClient,
    mock_twilio_gateway: MagicMock,
    mock_log_repo_e2e: MagicMock,
) -> "FastAPI":  # type: ignore[name-defined]
    from src.ai.triage_engine import TriageEngine
    from src.integration.kura_client import KuraClient
    from src.services.inbound_message_service import InboundMessageService
    from src.web.app import create_app
    from src.web.dependencies import (
        get_inbound_service,
        get_kura_client,
        get_settings,
    )
    from src.web.routers.webhook_twilio import validar_twilio_signature

    app = create_app(e2e_settings)

    kura_client = KuraClient(
        base_url=e2e_settings.KURA_API_BASE_URL,
        api_key=e2e_settings.KURA_API_KEY,
        timeout=e2e_settings.KURA_API_TIMEOUT,
        http_client=e2e_http_client,
    )
    triage = TriageEngine()

    def _inbound_service() -> InboundMessageService:
        return InboundMessageService(
            kura_client=kura_client,
            triage_engine=triage,
            twilio_gateway=mock_twilio_gateway,
            log_repo=mock_log_repo_e2e,
        )

    app.dependency_overrides[get_settings] = lambda: e2e_settings
    app.dependency_overrides[get_kura_client] = lambda: kura_client
    app.dependency_overrides[get_inbound_service] = _inbound_service
    app.dependency_overrides[validar_twilio_signature] = lambda: None  # bypass sig

    return app


@pytest.fixture
def e2e_client(e2e_app) -> TestClient:  # type: ignore[no-untyped-def]
    with TestClient(e2e_app, raise_server_exceptions=False) as c:
        yield c
