"""CORS para o mobile-clinica-rn rodando no navegador."""
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.web.app import create_app

_ORIGEM = "http://localhost:8082"


def _preflight(c: TestClient):  # type: ignore[no-untyped-def]
    return c.options(
        "/whatsapp/enviar",
        headers={
            "Origin": _ORIGEM,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key",
        },
    )


def test_origem_configurada_recebe_preflight(test_settings: Settings) -> None:
    settings = test_settings.model_copy(
        update={"CORS_ALLOWED_ORIGINS": f"{_ORIGEM}, https://clinica.example"}
    )
    with TestClient(create_app(settings)) as c:
        resp = _preflight(c)
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == _ORIGEM
    assert "x-api-key" in resp.headers["access-control-allow-headers"].lower()


def test_origem_fora_da_lista_nao_recebe_cabecalho(test_settings: Settings) -> None:
    settings = test_settings.model_copy(update={"CORS_ALLOWED_ORIGINS": "https://outra.example"})
    with TestClient(create_app(settings)) as c:
        resp = _preflight(c)
    assert "access-control-allow-origin" not in resp.headers


def test_sem_configuracao_nao_ha_cors(client: TestClient) -> None:
    resp = client.get("/health", headers={"Origin": _ORIGEM})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers
