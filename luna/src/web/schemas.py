"""Pydantic schemas para requests/responses das rotas web da Luna."""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Resposta do endpoint /health."""

    status: str


class ReadyResponse(BaseModel):
    """Resposta do endpoint /ready com estado dos sistemas dependentes."""

    status: str
    kura_api: bool
    oracle: bool


class ResumoExecucaoResponse(BaseModel):
    """Resposta do gatilho manual do lembrete de vacina (LU-04) — espelha ``ResumoExecucao``."""

    total: int
    enviadas: int
    falhas: int
    ja_enviadas: int
    sem_consentimento: int
