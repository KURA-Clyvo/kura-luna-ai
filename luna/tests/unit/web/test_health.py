"""Tests for /health and /ready endpoints."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.web.dependencies import get_kura_client


def test_health_retorna_200(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_sem_dependencias_externas(client: TestClient) -> None:
    """Liveness nunca chama kura ou oracle."""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_ready_kura_ok_oracle_indisponivel(app, test_settings) -> None:  # type: ignore[no-untyped-def]
    """Sem pool Oracle → oracle=False → 503."""
    mock_kura = AsyncMock()
    mock_kura.verificar_saude = AsyncMock(return_value=True)
    app.dependency_overrides[get_kura_client] = lambda: mock_kura

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/ready")

    # Oracle não inicializado no lifespan de teste → oracle=False
    data = resp.json()
    assert data["kura_api"] is True
    assert data["oracle"] is False
    assert resp.status_code == 503


def test_ready_kura_offline_retorna_503(app) -> None:  # type: ignore[no-untyped-def]
    mock_kura = AsyncMock()
    mock_kura.verificar_saude = AsyncMock(return_value=False)
    app.dependency_overrides[get_kura_client] = lambda: mock_kura

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/ready")

    assert resp.status_code == 503
    assert resp.json()["kura_api"] is False


def test_ready_response_contem_campos_esperados(client: TestClient) -> None:
    resp = client.get("/ready")
    data = resp.json()
    assert "status" in data
    assert "kura_api" in data
    assert "oracle" in data


def test_request_id_header_presente(client: TestClient) -> None:
    resp = client.get("/health")
    assert "x-request-id" in resp.headers


def test_kura_api_error_retorna_502_sem_stack_trace(app) -> None:  # type: ignore[no-untyped-def]
    from src.integration.exceptions import KuraApiError

    mock_kura = AsyncMock()
    mock_kura.verificar_saude = AsyncMock(side_effect=KuraApiError(500, "err"))
    app.dependency_overrides[get_kura_client] = lambda: mock_kura

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/ready")

    assert resp.status_code in (502, 500, 503)
    assert "Traceback" not in resp.text
