"""Pydantic Settings — reads from .env file."""
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
