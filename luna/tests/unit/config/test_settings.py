"""Tests for Settings and logging_config."""
import logging
import os

import pytest
from pydantic import ValidationError

from src.config.settings import Settings
from src.config.logging_config import setup_logging


def test_settings_missing_required_fields() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "ORACLE_DSN": "host:1521/ORCL",
        "ORACLE_USER": "luna",
        "ORACLE_PASSWORD": "pass",
        "TWILIO_SID": "AC123",
        "TWILIO_TOKEN": "tok",
        "TWILIO_FROM_NUMBER": "+14155238886",
        "YOLO_WEIGHTS_PATH": "src/ai/models/yolov8n.pt",
        "BREED_CLASSIFIER_WEIGHTS_PATH": "src/ai/models/breed.pth",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.ORACLE_DSN == "host:1521/ORCL"
    assert s.LOG_LEVEL == "INFO"


def test_settings_custom_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "ORACLE_DSN": "h:1521/X",
        "ORACLE_USER": "u",
        "ORACLE_PASSWORD": "p",
        "TWILIO_SID": "AC1",
        "TWILIO_TOKEN": "t",
        "TWILIO_FROM_NUMBER": "+1",
        "YOLO_WEIGHTS_PATH": "a.pt",
        "BREED_CLASSIFIER_WEIGHTS_PATH": "b.pth",
        "LOG_LEVEL": "DEBUG",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.LOG_LEVEL == "DEBUG"


def test_setup_logging_sets_level() -> None:
    setup_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING


def test_setup_logging_default_level() -> None:
    setup_logging()
    assert logging.getLogger().level == logging.INFO
