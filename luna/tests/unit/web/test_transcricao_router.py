"""Testes unitários para POST /transcricao.

Cobre: sucesso, 401 (key ausente/inválida), 400 (formato/tamanho),
fallback em falha do Whisper, e conformidade LGPD (sem conteúdo/segredo em log).
"""
import io
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.services.transcricao_service import IWhisperGateway, TranscricaoError
from src.web.app import create_app
from src.web.dependencies import get_settings, get_whisper_gateway

_CHAVE_VALIDA = "chave-inbound-teste"


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
        OPENAI_API_KEY="sk-test",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def mock_whisper_gw() -> MagicMock:
    gw = MagicMock(spec=IWhisperGateway)
    gw.transcrever = AsyncMock(return_value="Paciente com febre, prescrevo antitérmico.")
    return gw


@pytest.fixture
def transcricao_client(mock_whisper_gw: MagicMock) -> TestClient:
    settings = _settings_com_chave()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_whisper_gateway] = lambda: mock_whisper_gw
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _audio_file(nome: str = "consulta.mp3", conteudo: bytes = b"fake-audio-bytes"):
    return {"audio": (nome, io.BytesIO(conteudo), "audio/mpeg")}


# ── Sucesso ───────────────────────────────────────────────────────────────────

def test_transcrever_sucesso_retorna_200_com_soap(
    transcricao_client: TestClient, mock_whisper_gw: MagicMock
) -> None:
    resp = transcricao_client.post(
        "/transcricao",
        files=_audio_file(),
        headers={"X-API-Key": _CHAVE_VALIDA},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["transcricao"] == "Paciente com febre, prescrevo antitérmico."
    assert data["soap"]["p"] != ""


def test_transcrever_chama_gateway_com_bytes_do_arquivo(
    transcricao_client: TestClient, mock_whisper_gw: MagicMock
) -> None:
    transcricao_client.post(
        "/transcricao",
        files=_audio_file(conteudo=b"conteudo-especifico"),
        headers={"X-API-Key": _CHAVE_VALIDA},
    )
    mock_whisper_gw.transcrever.assert_called_once()
    args, _kwargs = mock_whisper_gw.transcrever.call_args
    assert args[0] == b"conteudo-especifico"


def test_transcrever_formatos_permitidos_aceitos(transcricao_client: TestClient) -> None:
    for nome in ("consulta.mp3", "consulta.m4a", "consulta.wav"):
        resp = transcricao_client.post(
            "/transcricao",
            files=_audio_file(nome=nome),
            headers={"X-API-Key": _CHAVE_VALIDA},
        )
        assert resp.status_code == 200, nome


# ── Auth 401 ──────────────────────────────────────────────────────────────────

def test_transcrever_sem_api_key_retorna_401(transcricao_client: TestClient) -> None:
    resp = transcricao_client.post("/transcricao", files=_audio_file())
    assert resp.status_code == 401


def test_transcrever_api_key_invalida_retorna_401(transcricao_client: TestClient) -> None:
    resp = transcricao_client.post(
        "/transcricao", files=_audio_file(), headers={"X-API-Key": "chave-errada"}
    )
    assert resp.status_code == 401


# ── 400 formato/tamanho ───────────────────────────────────────────────────────

def test_transcrever_formato_nao_suportado_retorna_400(transcricao_client: TestClient) -> None:
    resp = transcricao_client.post(
        "/transcricao",
        files=_audio_file(nome="consulta.ogg"),
        headers={"X-API-Key": _CHAVE_VALIDA},
    )
    assert resp.status_code == 400


def test_transcrever_arquivo_acima_do_limite_retorna_400(transcricao_client: TestClient) -> None:
    conteudo_grande = b"0" * (25 * 1024 * 1024 + 1)
    resp = transcricao_client.post(
        "/transcricao",
        files=_audio_file(conteudo=conteudo_grande),
        headers={"X-API-Key": _CHAVE_VALIDA},
    )
    assert resp.status_code == 400


# ── Fallback quando Whisper falha ────────────────────────────────────────────

def test_transcrever_whisper_falha_retorna_200_com_nulos(mock_whisper_gw: MagicMock) -> None:
    mock_whisper_gw.transcrever.side_effect = TranscricaoError("Whisper indisponível")

    settings = _settings_com_chave()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_whisper_gateway] = lambda: mock_whisper_gw

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post("/transcricao", files=_audio_file(), headers={"X-API-Key": _CHAVE_VALIDA})

    assert resp.status_code == 200
    data = resp.json()
    assert data["transcricao"] is None
    assert data["soap"] is None


# ── LGPD — sem conteúdo clínico nem segredo em log ───────────────────────────

def test_transcrever_logs_sem_conteudo_transcrito(
    transcricao_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="src.web.routers.transcricao"):
        transcricao_client.post(
            "/transcricao",
            files=_audio_file(),
            headers={"X-API-Key": _CHAVE_VALIDA},
        )

    log_text = " ".join(caplog.messages)
    assert "febre" not in log_text, "LGPD: conteúdo transcrito não pode aparecer no log"
    assert "antitérmico" not in log_text


def test_transcrever_logs_sem_api_key_openai(
    transcricao_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        transcricao_client.post(
            "/transcricao",
            files=_audio_file(),
            headers={"X-API-Key": _CHAVE_VALIDA},
        )

    log_text = " ".join(caplog.messages)
    assert "sk-test" not in log_text, "OPENAI_API_KEY nunca deve aparecer em log"
