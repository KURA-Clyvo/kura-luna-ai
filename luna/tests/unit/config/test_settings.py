"""Tests for Settings and logging_config."""
import logging

import pytest
from pydantic import ValidationError

from src.config.logging_config import setup_logging
from src.config.settings import Settings

_REQUIRED = {
    "ORACLE_DSN": "host:1521/ORCL",
    "ORACLE_USER": "luna",
    "ORACLE_PASSWORD": "pass",
    "TWILIO_SID": "AC123",
    "TWILIO_TOKEN": "tok",
    "TWILIO_FROM_NUMBER": "+14155238886",
    "YOLO_WEIGHTS_PATH": "src/ai/models/yolov8n.pt",
    "BREED_CLASSIFIER_WEIGHTS_PATH": "src/ai/models/breed.pth",
    "KURA_API_BASE_URL": "http://localhost:5000",
    "KURA_API_KEY": "test-key",
    "WEBHOOK_PUBLIC_URL": "https://test.ngrok.io/webhook/twilio/whatsapp",
}


def _make_settings(monkeypatch: pytest.MonkeyPatch, overrides: dict | None = None) -> Settings:
    env = dict(_REQUIRED)
    if overrides:
        env.update(overrides)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_missing_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    # Garante ambiente limpo — sem isso, env vars ambientais (ex.: as fake do
    # CI, necessárias para o import de src/web/app.py) mascarariam o teste.
    for key in _REQUIRED:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_missing_kura_api_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    env = dict(_REQUIRED)
    env.pop("KURA_API_BASE_URL")
    monkeypatch.delenv("KURA_API_BASE_URL", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_kura_url_without_http_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="http"):
        _make_settings(monkeypatch, {"KURA_API_BASE_URL": "localhost:5000"})


def test_settings_kura_url_https_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(monkeypatch, {"KURA_API_BASE_URL": "https://api.kura.com"})
    assert s.KURA_API_BASE_URL == "https://api.kura.com"


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(monkeypatch)
    assert s.KURA_API_TIMEOUT == 10
    assert s.LUNA_HTTP_PORT == 8000
    assert s.LOG_LEVEL == "INFO"


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(monkeypatch)
    assert s.ORACLE_DSN == "host:1521/ORCL"
    assert s.KURA_API_BASE_URL == "http://localhost:5000"
    assert s.KURA_API_KEY == "test-key"
    assert s.WEBHOOK_PUBLIC_URL == "https://test.ngrok.io/webhook/twilio/whatsapp"


def test_settings_custom_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(monkeypatch, {"LOG_LEVEL": "DEBUG"})
    assert s.LOG_LEVEL == "DEBUG"


def test_settings_custom_port(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(monkeypatch, {"LUNA_HTTP_PORT": "9000"})
    assert s.LUNA_HTTP_PORT == 9000


def test_setup_logging_sets_level() -> None:
    setup_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING


def test_setup_logging_default_level() -> None:
    setup_logging()
    assert logging.getLogger().level == logging.INFO
