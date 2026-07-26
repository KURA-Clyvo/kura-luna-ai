"""Pydantic Settings — reads from .env file."""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    ORACLE_DSN: str
    ORACLE_USER: str
    ORACLE_PASSWORD: str

    TWILIO_SID: str
    TWILIO_TOKEN: str
    TWILIO_FROM_NUMBER: str

    YOLO_WEIGHTS_PATH: str
    BREED_CLASSIFIER_WEIGHTS_PATH: str

    LOG_LEVEL: str = "INFO"

    # v2.0 — servidor HTTP e integração Kura .NET
    KURA_API_BASE_URL: str
    KURA_API_KEY: str
    KURA_API_TIMEOUT: int = 10
    WEBHOOK_PUBLIC_URL: str
    LUNA_HTTP_PORT: int = 8000
    # Chave de API inbound — protege POST /whatsapp/enviar de chamadas não autorizadas.
    # O mobile envia no header X-API-Key (EXPO_PUBLIC_LUNA_API_KEY).
    LUNA_INBOUND_API_KEY: str = ""
    # OpenAI Whisper — transcrição de áudio para draft SOAP (POST /transcricao).
    # Nunca logar nem retornar em response. Custo ~$0.006/min de áudio.
    OPENAI_API_KEY: str = ""

    @field_validator("KURA_API_BASE_URL")
    @classmethod
    def _validate_kura_url(cls, v: str) -> str:
        """Rejeita URLs que não iniciam com http."""
        if not v.startswith("http"):
            raise ValueError("KURA_API_BASE_URL deve iniciar com 'http'")
        return v
