"""Fixtures compartilhadas para testes do módulo web."""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.web.app import create_app
from src.web.dependencies import get_kura_client, get_settings


def _test_settings() -> Settings:
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
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def test_settings() -> Settings:
    return _test_settings()


@pytest.fixture
def mock_kura_client() -> AsyncMock:
    client = AsyncMock()
    client.verificar_saude = AsyncMock(return_value=True)
    return client


@pytest.fixture
def app(test_settings: Settings, mock_kura_client: AsyncMock):  # type: ignore[no-untyped-def]
    _app = create_app(test_settings)
    _app.dependency_overrides[get_settings] = lambda: test_settings
    _app.dependency_overrides[get_kura_client] = lambda: mock_kura_client
    return _app


@pytest.fixture
def client(app) -> TestClient:  # type: ignore[no-untyped-def]
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
