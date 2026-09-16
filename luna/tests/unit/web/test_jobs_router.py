"""Testes de POST /jobs/lembrete-vacina/executar (LU-04).

Cobre: sucesso (200), 401 (sem chave), 409 (concorrência com lock REAL —
não mock que retorna 409), 503 (Oracle indisponível / credencial Twilio
ausente-inválida, achado F4-1).
"""
import asyncio
import time
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.services.notification_service import ResumoExecucao
from src.web.app import create_app
from src.web.dependencies import get_lembrete_service, get_settings

_CHAVE_VALIDA = "chave-inbound-teste"


def _settings() -> Settings:
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
        LUNA_INBOUND_API_KEY=_CHAVE_VALIDA,
        _env_file=None,  # type: ignore[call-arg]
    )


def _fake_service(resumo: ResumoExecucao, delay: float = 0.0) -> MagicMock:
    svc = MagicMock()

    def _executar() -> ResumoExecucao:
        if delay:
            time.sleep(delay)
        return resumo

    svc.executar.side_effect = _executar
    return svc


# ── 401 ───────────────────────────────────────────────────────────────────

def test_sem_api_key_retorna_401() -> None:
    settings = _settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post("/jobs/lembrete-vacina/executar")
    assert resp.status_code == 401


def test_api_key_invalida_retorna_401() -> None:
    settings = _settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/jobs/lembrete-vacina/executar", headers={"X-API-Key": "chave-errada"}
        )
    assert resp.status_code == 401


# ── 200 sucesso ───────────────────────────────────────────────────────────

def test_sucesso_retorna_200_com_resumo() -> None:
    settings = _settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    resumo = ResumoExecucao(total=5, enviadas=3, falhas=1, ja_enviadas=1, sem_consentimento=0)
    app.dependency_overrides[get_lembrete_service] = lambda: _fake_service(resumo)

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/jobs/lembrete-vacina/executar", headers={"X-API-Key": _CHAVE_VALIDA}
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "total": 5,
        "enviadas": 3,
        "falhas": 1,
        "ja_enviadas": 1,
        "sem_consentimento": 0,
    }


# ── 503 — pool None / credencial Twilio (F4-1) ──────────────────────────────

def test_sem_pool_oracle_retorna_503() -> None:
    """Settings com DSN de teste -> lifespan não consegue construir o pool
    real -> app.state.pool fica None -> get_lembrete_service devolve 503
    (comportamento real do lifespan, sem override)."""
    settings = _settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/jobs/lembrete-vacina/executar", headers={"X-API-Key": _CHAVE_VALIDA}
        )

    assert resp.status_code == 503


def test_credencial_twilio_ausente_retorna_503_sem_derrubar_processo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F4-1: TwilioGateway.__init__ levanta TwilioException com credencial
    vazia -- get_lembrete_service (dependência REAL, não substituída) converte
    isso em 503 (nunca 500 cru, nunca crash do processo). Só o `get_pool` é
    trocado por um pool fake "disponível" -- o resto do caminho é o código
    de produção de verdade."""
    from src.web.dependencies import get_pool

    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)

    settings_sem_twilio = Settings(
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
    app = create_app(settings_sem_twilio)
    app.dependency_overrides[get_settings] = lambda: settings_sem_twilio
    app.dependency_overrides[get_pool] = lambda: MagicMock()  # pool "disponível"

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/jobs/lembrete-vacina/executar", headers={"X-API-Key": _CHAVE_VALIDA}
        )

    assert resp.status_code == 503
    detail = resp.json()["detail"].lower()
    assert "credencial" in detail or "mensageria" in detail


# ── 409 — concorrência com lock REAL ────────────────────────────────────────

async def test_execucao_concorrente_devolve_409_com_lock_real() -> None:
    """Duas chamadas concorrentes ao mesmo processo -- uma delas tem que
    devolver 409. Usa um lock REAL (asyncio.Lock do app.state), não um mock
    que retorna 409 -- a 2ª chamada só vê o lock ocupado porque a 1ª está de
    fato dentro do `async with lock` quando a 2ª chega.

    Mordida: remover o `if lock.locked(): raise HTTPException(409, ...)` do
    endpoint faz as duas chamadas devolverem 200 (falha nominal)."""
    settings = _settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    resumo = ResumoExecucao(total=1, enviadas=1, falhas=0, ja_enviadas=0)
    # delay real (thread, via asyncio.to_thread no endpoint) para garantir
    # que a 2ª requisição chegue enquanto a 1ª ainda segura o lock.
    app.dependency_overrides[get_lembrete_service] = lambda: _fake_service(resumo, delay=0.3)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # dispara a 1ª e dá um instante para ela realmente entrar no `async
        # with lock` antes de disparar a 2ª (concorrência real, não uma
        # corrida onde as duas poderiam chegar antes de qualquer uma travar).
        task1 = asyncio.create_task(
            client.post(
                "/jobs/lembrete-vacina/executar", headers={"X-API-Key": _CHAVE_VALIDA}
            )
        )
        await asyncio.sleep(0.05)
        resp2 = await client.post(
            "/jobs/lembrete-vacina/executar", headers={"X-API-Key": _CHAVE_VALIDA}
        )
        resp1 = await task1

    assert resp1.status_code == 200
    assert resp2.status_code == 409
