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
