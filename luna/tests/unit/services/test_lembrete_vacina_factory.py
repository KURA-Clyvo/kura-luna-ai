"""Testes da fábrica de composição do LembreteVacinaService (LU-04).

Extraída de `cli/main.py::_create_lembrete_service` para ser reusada pelo
scheduler e pelo endpoint HTTP sem duplicar a montagem."""
from unittest.mock import MagicMock, patch

import pytest
from twilio.base.exceptions import TwilioException

from src.services.lembrete_vacina_factory import criar_lembrete_service
from src.services.notification_service import LembreteVacinaService


def _settings() -> MagicMock:
    settings = MagicMock()
    settings.TWILIO_SID = "ACtest"
    settings.TWILIO_TOKEN = "test_token"
    settings.TWILIO_FROM_NUMBER = "+14155238886"
    return settings


@patch("src.services.lembrete_vacina_factory.TwilioGateway")
def test_criar_lembrete_service_compoe_service_valido(mock_gateway_cls: MagicMock) -> None:
    pool = MagicMock()
    service = criar_lembrete_service(_settings(), pool)
    assert isinstance(service, LembreteVacinaService)
    mock_gateway_cls.assert_called_once_with(
        account_sid="ACtest", auth_token="test_token", from_number="+14155238886"
    )


def test_criar_lembrete_service_propaga_twilio_exception_sem_credencial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F4-1: TwilioGateway.__init__ valida a credencial no construtor do SDK
    real -- sem mockar o Client, credencial vazia levanta TwilioException.
    Quem chama esta fábrica em um contexto que não pode crashar (endpoint,
    tick do scheduler) precisa capturar isto -- ver `dependencies.py::
    get_lembrete_service` e `jobs/lembrete_vacina_job.py::
    executar_tick_lembrete_vacina`.

    O SDK 9.3.2 cai para TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN do ambiente
    quando o argumento vem vazio (client_base.py) -- removidas aqui para o
    teste ser determinístico independente do que o host tiver setado."""
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    settings = MagicMock()
    settings.TWILIO_SID = ""
    settings.TWILIO_TOKEN = ""
    settings.TWILIO_FROM_NUMBER = ""
    pool = MagicMock()

    with pytest.raises(TwilioException):
        criar_lembrete_service(settings, pool)
